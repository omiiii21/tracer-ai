"""Tests for tracer_ai/corpus/ingest.py + tracer_ai/cli/__main__.py.

(Phase 3 Plan 05 / CORP-01 + CORP-02 surface)

Asserts:
  1. run_ingest against fixtures/claude-docs-sample/ writes 2 docs' worth
     of chunks; IngestResult.docs_processed == 2 and chunks_written > 0.
  2. Re-running run_ingest produces the same chunk IDs (UUIDv5 idempotency).
  3. embedder errors abort the pipeline AND skip delete_stale (T-03-05-06
     -- the corpus must never reach an inconsistent state on partial
     failure).
  4. CLI: main(["ingest", "--source", <fixtures>]) returns 0 with mocked
     embedder/pool.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.corpus.ingest", None)


# --- Test infrastructure ---------------------------------------------------


class _FakeTx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _RecordingConn:
    """asyncpg.Connection stub recording every (query, args)."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def transaction(self) -> _FakeTx:
        return _FakeTx()

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        if "DELETE" in query.upper():
            return "DELETE 0"
        return "INSERT 0 1"


class _AcquireCtx:
    def __init__(self, conn: _RecordingConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _RecordingConn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(self) -> None:
        self.conn = _RecordingConn()
        self.closed = False

    def acquire(self, timeout: float = 5.0) -> _AcquireCtx:
        return _AcquireCtx(self.conn)

    async def close(self) -> None:
        self.closed = True


class _FakeEmbedder:
    name = "voyage-code-3"
    version = "voyage-code-3@2025-09"
    dim = 1024

    def __init__(self, *, raise_on_call: int | None = None) -> None:
        self._calls = 0
        self._raise_on_call = raise_on_call

    async def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]:
        self._calls += 1
        if self._raise_on_call is not None and self._calls >= self._raise_on_call:
            raise RuntimeError("simulated embed failure")
        return [[0.0] * 1024 for _ in texts]


def _fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures" / "claude-docs-sample"


# --- Test 1: run_ingest writes 2 docs' worth of chunks --------------------


@pytest.mark.asyncio
async def test_run_ingest_writes_two_docs_chunks() -> None:
    from tracer_ai.corpus.chunker import MarkdownHeaderChunker
    from tracer_ai.corpus.ingest import run_ingest

    pool = _FakePool()
    embedder = _FakeEmbedder()
    chunker = MarkdownHeaderChunker(chunk_size=900, overlap=100)

    result = await run_ingest(
        source=_fixtures_dir(),
        embedder=embedder,
        chunker=chunker,
        pool=pool,  # type: ignore[arg-type]
        batch_size=64,
    )

    assert result.docs_processed == 2
    assert result.chunks_written > 0
    assert result.errors == []
    # Some INSERT statements must have hit the pool.
    inserts = [q for q, _ in pool.conn.executed if "INSERT INTO chunks" in q]
    assert len(inserts) >= result.chunks_written


# --- Test 2: deterministic UUIDv5 idempotency -----------------------------


@pytest.mark.asyncio
async def test_run_ingest_is_idempotent_on_chunk_ids() -> None:
    """Re-running ingest on the same fixture must produce identical chunk IDs."""
    from tracer_ai.corpus.chunker import MarkdownHeaderChunker
    from tracer_ai.corpus.loader import discover, load

    chunker = MarkdownHeaderChunker(chunk_size=900, overlap=100)

    paths = await discover(_fixtures_dir())
    ids_first: list[str] = []
    ids_second: list[str] = []
    for p in paths:
        doc1 = await load(p)
        doc2 = await load(p)
        ids_first.extend(str(c.id) for c in chunker.split(doc1))
        ids_second.extend(str(c.id) for c in chunker.split(doc2))

    assert ids_first == ids_second
    assert len(ids_first) > 0


# --- Test 3: embed error aborts AND skips delete_stale --------------------


@pytest.mark.asyncio
async def test_run_ingest_aborts_on_embed_error_and_skips_delete_stale() -> None:
    """T-03-05-06: a failed embed batch must NOT cascade into a corpus wipe."""
    from tracer_ai.corpus.chunker import MarkdownHeaderChunker
    from tracer_ai.corpus.ingest import run_ingest

    pool = _FakePool()
    # Fail on the very first embed call.
    embedder = _FakeEmbedder(raise_on_call=1)
    chunker = MarkdownHeaderChunker(chunk_size=900, overlap=100)

    result = await run_ingest(
        source=_fixtures_dir(),
        embedder=embedder,
        chunker=chunker,
        pool=pool,  # type: ignore[arg-type]
        batch_size=64,
    )

    assert result.errors, "errors list must contain the embed failure"
    assert any("embed_or_upsert_failed" in e for e in result.errors)
    # CRITICAL: no DELETE FROM chunks must have been issued.
    deletes = [q for q, _ in pool.conn.executed if "DELETE FROM chunks" in q]
    assert deletes == [], f"delete_stale must NOT run after embed failure; got: {deletes}"


# --- Test 4: CLI returns 0 on success -------------------------------------


def test_cli_main_ingest_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """main(["ingest", "--source", <fixtures>]) returns 0 with mocked deps."""
    import tracer_ai.cli.__main__ as cli_mod
    from tracer_ai.cli import __main__ as cli_main

    # Replace the heavy/external bits with no-ops.
    fake_pool = _FakePool()

    async def _fake_create_pool(*args: Any, **kwargs: Any) -> _FakePool:
        return fake_pool

    class _FakeEmbedderCtor(_FakeEmbedder):
        def __init__(self, *_a: Any, **_k: Any) -> None:
            super().__init__()

    monkeypatch.setattr(cli_mod, "VoyageEmbedder", _FakeEmbedderCtor)
    monkeypatch.setattr(cli_mod.asyncpg, "create_pool", _fake_create_pool)

    # The MarkdownHeaderChunker constructor is fine -- it's pure-CPU.
    # `run_ingest` itself stays untouched so we exercise the real glue code.

    rc = cli_main.main(["ingest", "--source", str(_fixtures_dir())])
    assert rc == 0


# --- Test 5: CLI prints valid IngestResult JSON ---------------------------


def test_cli_main_prints_ingest_result_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit code 0 + stdout is JSON parseable + has the expected fields."""
    import tracer_ai.cli.__main__ as cli_mod
    from tracer_ai.cli import __main__ as cli_main

    fake_pool = _FakePool()

    async def _fake_create_pool(*args: Any, **kwargs: Any) -> _FakePool:
        return fake_pool

    class _FakeEmbedderCtor(_FakeEmbedder):
        def __init__(self, *_a: Any, **_k: Any) -> None:
            super().__init__()

    monkeypatch.setattr(cli_mod, "VoyageEmbedder", _FakeEmbedderCtor)
    monkeypatch.setattr(cli_mod.asyncpg, "create_pool", _fake_create_pool)

    rc = cli_main.main(["ingest", "--source", str(_fixtures_dir())])
    assert rc == 0
    # stdout will contain structlog dev-format INFO lines AND the final JSON
    # blob from print(IngestResult.model_dump_json(indent=2)). Extract the
    # JSON object by finding the last balanced ``{ ... }`` span.
    out = capsys.readouterr().out
    last_brace_open = out.rfind("{\n")
    assert last_brace_open >= 0, f"no JSON object in stdout: {out!r}"
    payload = json.loads(out[last_brace_open:].strip())
    assert "docs_processed" in payload
    assert "chunks_written" in payload
    assert "errors" in payload


# --- Test 6: ValueError on missing source AND urls ------------------------


@pytest.mark.asyncio
async def test_run_ingest_raises_when_neither_source_nor_urls() -> None:
    from tracer_ai.corpus.chunker import MarkdownHeaderChunker
    from tracer_ai.corpus.ingest import run_ingest

    pool = _FakePool()
    embedder = _FakeEmbedder()
    chunker = MarkdownHeaderChunker()

    with pytest.raises(ValueError, match="source or urls"):
        await run_ingest(
            source=None,
            urls=None,
            embedder=embedder,
            chunker=chunker,
            pool=pool,  # type: ignore[arg-type]
        )


# Suppress unused-import noise on uuid4 (kept for future test extension).
_ = uuid4
