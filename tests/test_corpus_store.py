"""Tests for corpus/store.py (Phase 3 Plan 04 / CORP-03).

Asserts:
  1. upsert_chunks issues INSERT ... ON CONFLICT (id) DO UPDATE.
  2. The UPSERT statement includes the CORP-03 metadata triple
     (embedding_model + embedding_model_version + indexed_at).
  3. Mismatched chunks/embeddings lengths raises ValueError BEFORE pool acquire.
  4. delete_stale with empty current_doc_ids returns 0 and does NOT issue DELETE
     (safety guard against wiping the entire corpus).
  5. delete_stale with a populated set issues the parameterized DELETE.
  6. list_corpus returns the nested shape consumed by GET /admin/corpus.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from tracer_ai.corpus.store import delete_stale, list_corpus, upsert_chunks
from tracer_ai.corpus.types import Chunk

# --- Test infrastructure (recording FakePool) -----------------------------


class _FakeRow(dict):  # type: ignore[type-arg]
    def __getitem__(self, k: str) -> Any:  # type: ignore[override]
        return super().__getitem__(k)


class _FakeTx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeConn:
    """Records every query passed to execute / fetchrow / fetch."""

    def __init__(
        self,
        *,
        delete_result: str = "DELETE 0",
        fetchrow_row: _FakeRow | None = None,
        fetch_rows: list[_FakeRow] | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self._delete_result = delete_result
        self._fetchrow_row = fetchrow_row
        self._fetch_rows = fetch_rows or []

    def transaction(self) -> _FakeTx:
        return _FakeTx()

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return self._delete_result if "DELETE" in query.upper() else "INSERT 0 1"

    async def fetchrow(self, query: str, *args: Any) -> _FakeRow | None:
        self.executed.append((query, args))
        return self._fetchrow_row

    async def fetch(self, query: str, *args: Any) -> list[_FakeRow]:
        self.executed.append((query, args))
        return self._fetch_rows


class _FakeAcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(
        self,
        *,
        delete_result: str = "DELETE 0",
        fetchrow_row: _FakeRow | None = None,
        fetch_rows: list[_FakeRow] | None = None,
    ) -> None:
        self.conn = _FakeConn(
            delete_result=delete_result,
            fetchrow_row=fetchrow_row,
            fetch_rows=fetch_rows,
        )

    def acquire(self, timeout: float = 5.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.conn)


def _make_chunks(n: int) -> list[Chunk]:
    return [
        Chunk(
            id=uuid4(),
            doc_id=f"d{i}",
            chunk_index=i,
            doc_section="auth",
            content=f"chunk {i}",
            metadata={"section_title": f"Section {i}"},
        )
        for i in range(n)
    ]


# --- Test 1: upsert_chunks issues INSERT ... ON CONFLICT (id) DO UPDATE ----


@pytest.mark.asyncio
async def test_upsert_chunks_issues_on_conflict_update() -> None:
    chunks = _make_chunks(3)
    embeddings = [[0.1] * 1024 for _ in chunks]
    pool = _FakePool()
    n = await upsert_chunks(
        pool,  # type: ignore[arg-type]
        chunks,
        embeddings,
        embedding_model="voyage-code-3",
        embedding_model_version="voyage-code-3@2025-09",
    )
    assert n == 3
    # Every executed query should be an INSERT with ON CONFLICT (id) DO UPDATE.
    insert_queries = [q for q, _ in pool.conn.executed if "INSERT INTO chunks" in q]
    assert len(insert_queries) == 3
    for q in insert_queries:
        assert "ON CONFLICT (id) DO UPDATE" in q


# --- Test 2: UPSERT writes the CORP-03 metadata triple --------------------


@pytest.mark.asyncio
async def test_upsert_chunks_writes_metadata_triple() -> None:
    chunks = _make_chunks(1)
    embeddings = [[0.1] * 1024]
    pool = _FakePool()
    await upsert_chunks(
        pool,  # type: ignore[arg-type]
        chunks,
        embeddings,
        embedding_model="voyage-code-3",
        embedding_model_version="voyage-code-3@2025-09",
    )
    insert_q = next(q for q, _ in pool.conn.executed if "INSERT INTO chunks" in q)
    # The three CORP-03 columns must be projected by the INSERT statement.
    assert "embedding_model" in insert_q
    assert "embedding_model_version" in insert_q
    assert "indexed_at" in insert_q
    # And the ON CONFLICT branch must update them too (re-ingest must update,
    # not just preserve, the metadata triple).
    update_branch = insert_q.split("ON CONFLICT")[1]
    assert "embedding_model = EXCLUDED.embedding_model" in update_branch
    assert "embedding_model_version = EXCLUDED.embedding_model_version" in update_branch
    assert "indexed_at = now()" in update_branch


# --- Test 3: mismatched lengths raises ValueError before pool acquire -----


@pytest.mark.asyncio
async def test_upsert_chunks_length_mismatch_raises() -> None:
    chunks = _make_chunks(3)
    embeddings = [[0.1] * 1024 for _ in range(2)]  # one short
    pool = _FakePool()
    with pytest.raises(ValueError, match=r"chunks .* embeddings"):
        await upsert_chunks(
            pool,  # type: ignore[arg-type]
            chunks,
            embeddings,
            embedding_model="voyage-code-3",
            embedding_model_version="voyage-code-3@2025-09",
        )
    # Pool was never touched -- error fires before any acquire.
    assert pool.conn.executed == []


@pytest.mark.asyncio
async def test_upsert_chunks_empty_returns_zero() -> None:
    pool = _FakePool()
    n = await upsert_chunks(
        pool,  # type: ignore[arg-type]
        [],
        [],
        embedding_model="voyage-code-3",
        embedding_model_version="voyage-code-3@2025-09",
    )
    assert n == 0
    assert pool.conn.executed == []


# --- Test 4: delete_stale empty set returns 0 and issues NO DELETE --------


@pytest.mark.asyncio
async def test_delete_stale_empty_set_does_not_delete() -> None:
    """T-03-04-05: empty current_doc_ids must NOT issue DELETE FROM chunks.

    The SQL ``WHERE doc_id <> ALL('{}')`` is vacuously true for every row and
    would wipe the corpus -- the safety guard short-circuits and warns.
    """
    pool = _FakePool(delete_result="DELETE 0")
    n = await delete_stale(pool, set())  # type: ignore[arg-type]
    assert n == 0
    assert pool.conn.executed == []


# --- Test 5: delete_stale with populated set issues DELETE ----------------


@pytest.mark.asyncio
async def test_delete_stale_issues_parameterized_delete() -> None:
    pool = _FakePool(delete_result="DELETE 7")
    n = await delete_stale(pool, {"d1", "d2", "d3"})  # type: ignore[arg-type]
    assert n == 7
    delete_queries = [q for q, _ in pool.conn.executed if "DELETE FROM chunks" in q]
    assert len(delete_queries) == 1
    q = delete_queries[0]
    # Must be parameterized: WHERE doc_id <> ALL($1::text[])
    assert "WHERE doc_id <> ALL($1::text[])" in q
    # And the doc_ids must arrive as the $1 binding (a list, not interpolated).
    args = pool.conn.executed[0][1]
    assert isinstance(args[0], list)
    assert set(args[0]) == {"d1", "d2", "d3"}


@pytest.mark.asyncio
async def test_delete_stale_parses_zero_when_result_unparseable() -> None:
    pool = _FakePool(delete_result="UNKNOWN")
    n = await delete_stale(pool, {"d1"})  # type: ignore[arg-type]
    assert n == 0


# --- Test 6: list_corpus returns the expected nested shape ----------------


@pytest.mark.asyncio
async def test_list_corpus_returns_expected_shape() -> None:
    last_indexed = datetime(2026, 5, 5, 8, 0, tzinfo=UTC)
    fetchrow_row = _FakeRow(
        doc_count=12,
        chunk_count=347,
        last_indexed_at=last_indexed,
        embedding_model="voyage-code-3",
        embedding_model_version="voyage-code-3@2025-09",
    )
    fetch_rows = [
        _FakeRow(
            id="claude-docs/auth",
            doc_section="auth",
            source_url="https://docs.anthropic.com/auth",
            chunk_count=18,
            ingested_at=last_indexed,
        ),
        _FakeRow(
            id="claude-docs/messages",
            doc_section="messages",
            source_url=None,
            chunk_count=42,
            ingested_at=last_indexed,
        ),
    ]
    pool = _FakePool(fetchrow_row=fetchrow_row, fetch_rows=fetch_rows)
    out = await list_corpus(pool)  # type: ignore[arg-type]
    assert out["doc_count"] == 12
    assert out["chunk_count"] == 347
    assert out["embedding_model"] == "voyage-code-3"
    assert out["embedding_model_version"] == "voyage-code-3@2025-09"
    assert out["last_indexed_at"] == last_indexed
    assert len(out["docs"]) == 2
    d0 = out["docs"][0]
    assert d0["id"] == "claude-docs/auth"
    assert d0["doc_section"] == "auth"
    assert d0["source_url"] == "https://docs.anthropic.com/auth"
    assert d0["chunk_count"] == 18
    # source_url=None at the SQL layer must surface as empty string in the
    # admin API shape (so the frontend can string-handle it without null
    # checks).
    assert out["docs"][1]["source_url"] == ""


@pytest.mark.asyncio
async def test_list_corpus_empty_corpus_returns_zeros() -> None:
    """Empty corpus: aggregate row may have None counts; list_corpus must coerce to 0."""
    fetchrow_row = _FakeRow(
        doc_count=None,
        chunk_count=None,
        last_indexed_at=None,
        embedding_model=None,
        embedding_model_version=None,
    )
    pool = _FakePool(fetchrow_row=fetchrow_row, fetch_rows=[])
    out = await list_corpus(pool)  # type: ignore[arg-type]
    assert out["doc_count"] == 0
    assert out["chunk_count"] == 0
    assert out["embedding_model"] == ""
    assert out["embedding_model_version"] == ""
    assert out["last_indexed_at"] is None
    assert out["docs"] == []
