"""Tests for PgvectorRetriever (Phase 3 Plan 04 / RAG-01).

Asserts:
  1. retrieve returns RetrievedChunk rows ordered by descending score.
  2. Score values are clamped/asserted into [0, 1] (Pydantic validates).
  3. Query string includes the cosine ``<=>`` operator and ``LIMIT $2``.
  4. ``SET LOCAL hnsw.ef_search = 40`` is issued before the SELECT.
  5. PgvectorRetriever is structurally typed as the Retriever Protocol.
  6. ``top_k <= 0`` raises ValueError before any pool acquire.

Mocks the asyncpg pool via the FakePool pattern from tests/test_healthz.py:17-44.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from tracer_ai.rag.protocols import Retriever
from tracer_ai.rag.retriever import PgvectorRetriever
from tracer_ai.rag.types import RetrievedChunk

# --- Test infrastructure (FakePool pattern from tests/test_healthz.py) -----


class _FakeRow(dict):  # type: ignore[type-arg]
    """asyncpg.Record duck-type: dict with __getitem__."""

    def __getitem__(self, k: str) -> Any:  # type: ignore[override]
        return super().__getitem__(k)


class _FakeTx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeConn:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows
        self.executed: list[str] = []
        self.fetch_args: list[tuple[Any, ...]] = []

    def transaction(self) -> _FakeTx:
        return _FakeTx()

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append(query)
        return "SET"

    async def fetch(self, query: str, *args: Any) -> list[_FakeRow]:
        self.executed.append(query)
        self.fetch_args.append(args)
        return self._rows


class _FakeAcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self.conn = _FakeConn(rows)

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.conn)


# --- Test 1: retrieve returns chunks ordered by descending score -----------


@pytest.mark.asyncio
async def test_retrieve_returns_chunks_ordered() -> None:
    rows = [
        _FakeRow(
            id=uuid4(),
            doc_id=f"d{i}",
            doc_section="auth",
            content=f"chunk {i}",
            metadata={},
            score=0.9 - 0.1 * i,
        )
        for i in range(5)
    ]
    pool = _FakePool(rows)
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    out = await r.retrieve([0.1] * 1024, top_k=5)
    assert len(out) == 5
    assert all(isinstance(c, RetrievedChunk) for c in out)
    # The fake returns rows in pre-sorted order; assert preserved-ordering by score desc.
    scores = [c.score for c in out]
    assert scores == sorted(scores, reverse=True)


# --- Test 2: score values clamped into [0, 1] ------------------------------


@pytest.mark.asyncio
async def test_retrieve_clamps_score_into_unit_interval() -> None:
    """HNSW cosine distance can produce tiny negative drift on identical vectors;
    the retriever clamps into [0, 1] so RetrievedChunk validation succeeds."""
    rows = [
        _FakeRow(
            id=uuid4(),
            doc_id="d",
            doc_section="auth",
            content="x",
            metadata={},
            score=-0.0001,  # tiny negative drift -- must be clamped to 0.0
        ),
        _FakeRow(
            id=uuid4(),
            doc_id="d",
            doc_section="auth",
            content="y",
            metadata={},
            score=1.0001,  # tiny positive overshoot -- must be clamped to 1.0
        ),
    ]
    pool = _FakePool(rows)
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    out = await r.retrieve([0.1] * 1024, top_k=2)
    assert len(out) == 2
    for c in out:
        assert 0.0 <= c.score <= 1.0


# --- Test 3: query uses cosine <=> operator and LIMIT $2 -------------------


@pytest.mark.asyncio
async def test_retrieve_uses_cosine_operator_and_limit() -> None:
    pool = _FakePool([])
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    await r.retrieve([0.1] * 1024, top_k=5)
    sel = next(q for q in pool.conn.executed if "FROM chunks" in q)
    assert "<=>" in sel
    assert "ORDER BY embedding <=>" in sel
    assert "LIMIT $2" in sel


# --- Test 4: SET LOCAL hnsw.ef_search = 40 issued before the SELECT --------


@pytest.mark.asyncio
async def test_retrieve_sets_ef_search_before_select() -> None:
    pool = _FakePool([])
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    await r.retrieve([0.1] * 1024, top_k=5)
    executed = pool.conn.executed
    ef_idx = next(i for i, q in enumerate(executed) if "ef_search = 40" in q)
    sel_idx = next(i for i, q in enumerate(executed) if "FROM chunks" in q)
    assert ef_idx < sel_idx, "SET LOCAL hnsw.ef_search must run BEFORE the SELECT"


# --- Test 5: Protocol structural typing ------------------------------------


def test_pgvector_retriever_is_a_retriever() -> None:
    """PgvectorRetriever must be structurally typed as the Retriever Protocol."""

    def _accepts(_r: Retriever) -> None:
        return None

    # We need an instance, not the class, for the runtime_checkable Protocol check.
    pool = _FakePool([])
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    _accepts(r)
    assert isinstance(r, Retriever)


# --- Test 6: top_k <= 0 raises ValueError ----------------------------------


@pytest.mark.asyncio
async def test_retrieve_top_k_zero_raises() -> None:
    pool = _FakePool([])
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="top_k"):
        await r.retrieve([0.1] * 1024, top_k=0)


@pytest.mark.asyncio
async def test_retrieve_top_k_negative_raises() -> None:
    pool = _FakePool([])
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="top_k"):
        await r.retrieve([0.1] * 1024, top_k=-3)


# --- Test 7: metadata as JSON string is decoded ----------------------------


@pytest.mark.asyncio
async def test_retrieve_decodes_jsonb_metadata_str() -> None:
    """asyncpg may return JSONB as either str (no codec) or dict (codec set).
    Accept both shapes."""
    rows = [
        _FakeRow(
            id=uuid4(),
            doc_id="d",
            doc_section="auth",
            content="x",
            metadata=json.dumps({"section_title": "Auth"}),
            score=0.5,
        ),
    ]
    pool = _FakePool(rows)
    r = PgvectorRetriever(pool)  # type: ignore[arg-type]
    out = await r.retrieve([0.1] * 1024, top_k=1)
    assert out[0].metadata == {"section_title": "Auth"}
