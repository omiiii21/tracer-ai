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
) -> tuple[Any, _CapturingWriter]:
    from tracer_ai.rag.pipeline import Pipeline

    writer = _CapturingWriter()
    pipeline = Pipeline(
        embedder=_FakeEmbedder(),
        retriever=_FakeRetriever(n_chunks=n_chunks, raise_exc=retriever_raise),
        llm=_FakeLLM(deltas=deltas),
        writer=writer,
        top_k=5,
    )
    return pipeline, writer


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
