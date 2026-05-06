"""Tests for tracer_ai/rag/pipeline.py (Phase 3 Plan 05 / RAG-04).

Asserts (all six are CI-enforced witnesses for the load-bearing properties):
  1. ``run_stream`` emits exactly 4 spans named
     {rag.request, rag.retrieve, rag.prompt_assemble, rag.llm_call}.
  2. All 4 spans share the same ``trace_id``; the 3 children carry
     ``parent_span_id == root.span_id``; the root has parent_span_id None.
  3. ``rag.request`` span attrs include GEN_AI_PROVIDER_NAME='anthropic'
     and GEN_AI_REQUEST_MODEL set to settings.llm_bot_model.
  4. When the retriever raises mid-flight, the rag.retrieve AND rag.request
     spans are STILL emitted (try/finally per stage / Pitfall 7.8 mitigation),
     and the exception propagates to the caller.
  5. The output stream contains both TextDelta and Final events.
  6. Source file does NOT contain ``from opentelemetry`` (ADR 005 / D-2.40).
"""

from __future__ import annotations

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
    sys.modules.pop("tracer_ai.rag.pipeline", None)


# --- Test infrastructure ---------------------------------------------------


class _CapturingWriter:
    """TraceWriter Protocol consumer that records every emitted span."""

    def __init__(self) -> None:
        from tracer_ai.tracer.writer import Span

        self.spans: list[Span] = []

    async def emit(self, span: Any) -> None:
        self.spans.append(span)


class _FakeEmbedder:
    name = "voyage-code-3"
    version = "voyage-code-3@2025-09"
    dim = 1024

    async def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]


def _make_chunk(idx: int) -> Any:
    from tracer_ai.rag.types import RetrievedChunk

    return RetrievedChunk(
        id=uuid4(),
        doc_id=f"claude-docs/doc-{idx}",
        doc_section="auth",
        content=f"chunk {idx} content",
        metadata={"section_title": "Authentication"},
        score=0.85 - idx * 0.05,
    )


class _FakeRetriever:
    def __init__(self, *, n_chunks: int = 3, raise_exc: Exception | None = None) -> None:
        self._n = n_chunks
        self._raise = raise_exc

    async def retrieve(self, query_embedding: list[float], top_k: int) -> list[Any]:
        if self._raise is not None:
            raise self._raise
        return [_make_chunk(i) for i in range(self._n)]


class _FakeLLM:
    """Yields TextDelta events then a Final(LLMResult)."""

    name = "claude-sonnet-4-5-20250929"

    def __init__(self, *, deltas: list[str] | None = None) -> None:
        self._deltas = deltas or ["Hello", " ", "world"]

    async def stream(self, messages: list[Any], *, max_tokens: int = 1024) -> Any:
        from tracer_ai.rag.types import Final, LLMResult, TextDelta

        for d in self._deltas:
            yield TextDelta(text=d)
        yield Final(
            result=LLMResult(
                answer="".join(self._deltas),
                input_tokens=120,
                output_tokens=8,
                estimated_cost_usd=0.000_48,
            )
        )


def _build_pipeline(
    *,
    n_chunks: int = 3,
    retriever_raise: Exception | None = None,
    deltas: list[str] | None = None,
    db_pool: Any = None,
) -> tuple[Any, _CapturingWriter]:
    from tracer_ai.rag.pipeline import Pipeline

    writer = _CapturingWriter()
    pipeline = Pipeline(
        embedder=_FakeEmbedder(),
        retriever=_FakeRetriever(n_chunks=n_chunks, raise_exc=retriever_raise),
        llm=_FakeLLM(deltas=deltas),
        writer=writer,
        top_k=5,
        db_pool=db_pool,
    )
    return pipeline, writer


# --- Phase 4 Plan 1 Task 3: FakePool recorder for db_pool integration -----


class _FakeConn:
    def __init__(self, recorder: list[tuple[str, str, tuple[Any, ...]]]) -> None:
        self._recorder = recorder

    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append(("execute", query, args))


class _FakeAcquireCtx:
    def __init__(self, recorder: list[tuple[str, str, tuple[Any, ...]]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._recorder)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    """Mirrors test_feedback_route.py FakePool pattern; records execute() calls."""

    def __init__(self) -> None:
        self.recorder: list[tuple[str, str, tuple[Any, ...]]] = []

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.recorder)


# --- Test 1: 4 spans emitted ------------------------------------------------


@pytest.mark.asyncio
async def test_emits_four_spans() -> None:
    pipeline, writer = _build_pipeline()
    async for _ in pipeline.run_stream("How do I authenticate?"):
        pass
    names = sorted(s.name for s in writer.spans)
    assert names == [
        "rag.llm_call",
        "rag.prompt_assemble",
        "rag.request",
        "rag.retrieve",
    ]


# --- Test 2: trace_id consistency + parent_span_id graph -------------------


@pytest.mark.asyncio
async def test_trace_id_consistent_and_parent_span_ids_correct() -> None:
    pipeline, writer = _build_pipeline()
    async for _ in pipeline.run_stream("q"):
        pass
    trace_ids = {s.trace_id for s in writer.spans}
    assert len(trace_ids) == 1, f"All spans must share one trace_id, got {trace_ids}"

    root = next(s for s in writer.spans if s.name == "rag.request")
    assert root.parent_span_id is None
    children = [s for s in writer.spans if s.name != "rag.request"]
    assert len(children) == 3
    for child in children:
        assert child.parent_span_id == root.span_id, f"{child.name}.parent_span_id != root.span_id"


# --- Test 3: rag.request attrs include provider + model --------------------


@pytest.mark.asyncio
async def test_root_attrs_include_provider_and_model() -> None:
    from tracer_ai.config import settings
    from tracer_ai.tracer.span import GEN_AI_PROVIDER_NAME, GEN_AI_REQUEST_MODEL

    pipeline, writer = _build_pipeline()
    async for _ in pipeline.run_stream("q"):
        pass
    root = next(s for s in writer.spans if s.name == "rag.request")
    assert root.attrs.get(GEN_AI_PROVIDER_NAME) == "anthropic"
    assert root.attrs.get(GEN_AI_REQUEST_MODEL) == settings.llm_bot_model


# --- Test 4: retriever failure still emits rag.retrieve + rag.request -----


@pytest.mark.asyncio
async def test_retriever_failure_still_emits_spans() -> None:
    """Pitfall 7.8 / T-03-05-04: per-stage try/finally guarantees observability."""
    pipeline, writer = _build_pipeline(retriever_raise=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        async for _ in pipeline.run_stream("q"):
            pass

    names = {s.name for s in writer.spans}
    assert "rag.retrieve" in names, "retrieve span must emit even when stage raised"
    assert "rag.request" in names, "root span must emit even when stage raised"


# --- Test 5: stream contains TextDelta + Final ------------------------------


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_and_final() -> None:
    from tracer_ai.rag.types import Final, TextDelta

    pipeline, _writer = _build_pipeline(deltas=["aa", "bb"])
    events = []
    async for ev in pipeline.run_stream("q"):
        events.append(ev)

    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    finals = [e for e in events if isinstance(e, Final)]
    assert len(text_deltas) == 2
    assert len(finals) == 1
    assert finals[0].result.input_tokens == 120


# --- Test 6: ADR 005 -- no opentelemetry import in pipeline.py -------------


def test_no_opentelemetry_import_in_pipeline() -> None:
    """ADR 005 / D-2.40: scan only real-import lines (skip docstring mentions)."""
    src_path = Path(__file__).resolve().parent.parent / "tracer_ai" / "rag" / "pipeline.py"
    text = src_path.read_text(encoding="utf-8")
    real_violators: list[str] = []
    in_docstring = False
    for ln in text.splitlines():
        stripped = ln.strip()
        # Toggle on triple-quote boundaries (single-line docstrings handled too).
        triple_count = stripped.count('"""')
        if triple_count % 2 == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith("#"):
            continue
        if stripped.startswith(("from opentelemetry", "import opentelemetry")):
            real_violators.append(stripped)
    assert not real_violators, (
        "ADR 005 / D-2.40: pipeline.py must not import opentelemetry; " f"found: {real_violators}"
    )


# --- Test 7: Phase 4 D-4.01/D-4.03 — db_pool INSERT + two UPDATEs ----------


@pytest.mark.asyncio
async def test_pipeline_with_db_pool_inserts_traces_row() -> None:
    """D-4.01/D-4.03 + closure-capture verification.

    Asserts ALL THREE SQL ops fire on a complete cycle (INSERT INTO traces,
    UPDATE traces SET latency_ms, UPDATE traces SET estimated_cost_usd) AND
    the trace_id argument is consistent across all three. Failure of any one
    indicates broken closure capture (e.g., trace_id not in scope inside
    _llm_text_iter or _emit_root).
    """
    pool = _FakePool()
    pipeline, _writer = _build_pipeline(db_pool=pool)
    async for _ev in pipeline.run_chat_stream("test"):
        pass  # drain to completion

    queries = [(kind, q) for kind, q, _args in pool.recorder if kind == "execute"]
    # The integration must fire ALL THREE — failure of any one indicates a
    # broken closure capture (e.g., trace_id not in scope inside _llm_text_iter)
    assert any(
        "INSERT INTO traces" in q for _kind, q in queries
    ), f"Missing INSERT INTO traces — _orchestrate up-front INSERT failed: {queries}"
    assert any(
        "UPDATE traces SET latency_ms" in q for _kind, q in queries
    ), f"Missing UPDATE traces SET latency_ms — _emit_root closure broken: {queries}"
    assert any("UPDATE traces SET estimated_cost_usd" in q for _kind, q in queries), (
        f"Missing UPDATE traces SET estimated_cost_usd — _llm_text_iter closure "
        f"broken (trace_id not captured? self._db_pool not captured?): {queries}"
    )

    # Verify the trace_id argument is consistent across all 3 SQL operations
    # (same UUID string) — guards against accidental re-uuid4() in different scopes.
    insert_args = next(
        args for kind, q, args in pool.recorder if kind == "execute" and "INSERT INTO traces" in q
    )
    update_lat_args = next(
        args
        for kind, q, args in pool.recorder
        if kind == "execute" and "UPDATE traces SET latency_ms" in q
    )
    update_cost_args = next(
        args
        for kind, q, args in pool.recorder
        if kind == "execute" and "UPDATE traces SET estimated_cost_usd" in q
    )
    insert_trace_id = insert_args[0]  # 1st positional arg of INSERT
    update_lat_trace_id = update_lat_args[2]  # 3rd positional arg of latency UPDATE
    update_cost_trace_id = update_cost_args[1]  # 2nd positional arg of cost UPDATE
    assert insert_trace_id == update_lat_trace_id == update_cost_trace_id, (
        f"trace_id mismatch across SQL ops — closure capture broken: "
        f"INSERT={insert_trace_id} UPDATE_LAT={update_lat_trace_id} "
        f"UPDATE_COST={update_cost_trace_id}"
    )


# --- Test 8: Phase 4 D-4.11/D-4.12 — payload contents per child span -------


@pytest.mark.asyncio
async def test_pipeline_emits_payload_on_child_spans() -> None:
    """D-4.11/D-4.12: each child span carries the documented payload shape.

    Root rag.request span carries payload=None (D-4.11 explicit).
    """
    pipeline, writer = _build_pipeline()
    async for _ev in pipeline.run_chat_stream("how do I authenticate?"):
        pass

    by_name = {s.name: s for s in writer.spans}

    retrieve = by_name["rag.retrieve"]
    assert retrieve.payload is not None
    assert "retrieved_chunks" in retrieve.payload
    assert isinstance(retrieve.payload["retrieved_chunks"], list)

    prompt = by_name["rag.prompt_assemble"]
    assert prompt.payload is not None
    assert "messages" in prompt.payload
    assert "prompt_template_id" in prompt.payload

    llm = by_name["rag.llm_call"]
    assert llm.payload is not None
    assert "response" in llm.payload

    request_root = by_name["rag.request"]
    assert request_root.payload is None, "D-4.11: root rag.request span must have payload=None"
