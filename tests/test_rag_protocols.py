"""Tests for tracer_ai.rag.protocols + tracer_ai.rag.types (Phase 3 Plan 01).

Three behavioral assertions:
  1. The three Protocols (Embedder, Retriever, LLM) are runtime_checkable
     and accept structurally-conforming stub instances (mypy --strict + isinstance).
  2. RetrievedChunk(score=...) enforces the [0.0, 1.0] bound via pydantic.ValidationError.
  3. Pydantic models in rag/types.py reject extra fields (extra='forbid').

Mirrors the strict-mode contract pattern from tracer_ai/api/health.py:27-33.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from tracer_ai.rag.protocols import LLM, Embedder, Retriever
from tracer_ai.rag.types import (
    Final,
    LLMResult,
    Message,
    PipelineResult,
    RetrievedChunk,
    StreamEvent,
    TextDelta,
)

# ---------------------------------------------------------------------------
# Test 1: structural Protocol acceptance (runtime_checkable + mypy --strict)
# ---------------------------------------------------------------------------


class _StubEmbedder:
    name = "stub-embedder"
    version = "0.0.1"
    dim = 1024

    async def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


class _StubRetriever:
    async def retrieve(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        return []


class _StubLLM:
    name = "stub-llm"

    async def stream(
        self, messages: list[Message], *, max_tokens: int = 1024
    ) -> AsyncIterator[StreamEvent]:
        async def _gen() -> AsyncIterator[StreamEvent]:
            yield TextDelta(text="hi")
            yield Final(
                result=LLMResult(
                    answer="hi",
                    input_tokens=1,
                    output_tokens=1,
                    estimated_cost_usd=0.0,
                )
            )

        return _gen()


def _accepts_embedder(e: Embedder) -> None:
    """Mypy --strict structural typing shim (PATTERNS.md §Backend Subsystem 2)."""
    _ = e.name
    _ = e.version
    _ = e.dim


def _accepts_retriever(r: Retriever) -> None:
    """Mypy --strict structural typing shim."""
    _ = r.retrieve


def _accepts_llm(model: LLM) -> None:
    """Mypy --strict structural typing shim."""
    _ = model.name


def test_stub_embedder_is_structurally_an_embedder() -> None:
    stub = _StubEmbedder()
    _accepts_embedder(stub)  # mypy --strict assertion at type-check time
    assert isinstance(stub, Embedder)  # runtime_checkable assertion


def test_stub_retriever_is_structurally_a_retriever() -> None:
    stub = _StubRetriever()
    _accepts_retriever(stub)
    assert isinstance(stub, Retriever)


def test_stub_llm_is_structurally_an_llm() -> None:
    stub = _StubLLM()
    _accepts_llm(stub)
    assert isinstance(stub, LLM)


# ---------------------------------------------------------------------------
# Test 2: RetrievedChunk score must be in [0.0, 1.0]
# ---------------------------------------------------------------------------


def _valid_chunk_kwargs() -> dict[str, object]:
    return {
        "id": uuid4(),
        "doc_id": "claude-docs/auth",
        "doc_section": "auth",
        "content": "Authenticate via x-api-key header.",
        "metadata": {"source_url": "https://example/auth"},
        "score": 0.5,
    }


def test_retrieved_chunk_score_above_one_raises() -> None:
    kwargs = _valid_chunk_kwargs()
    kwargs["score"] = 1.5
    with pytest.raises(ValidationError):
        RetrievedChunk(**kwargs)  # type: ignore[arg-type]


def test_retrieved_chunk_score_below_zero_raises() -> None:
    kwargs = _valid_chunk_kwargs()
    kwargs["score"] = -0.01
    with pytest.raises(ValidationError):
        RetrievedChunk(**kwargs)  # type: ignore[arg-type]


def test_retrieved_chunk_score_at_bounds_accepts() -> None:
    """Inclusive bounds: 0.0 and 1.0 must be valid."""
    for s in (0.0, 1.0):
        kwargs = _valid_chunk_kwargs()
        kwargs["score"] = s
        chunk = RetrievedChunk(**kwargs)  # type: ignore[arg-type]
        assert chunk.score == s


# ---------------------------------------------------------------------------
# Test 3: extra='forbid' on every Pydantic model
# ---------------------------------------------------------------------------


def test_retrieved_chunk_rejects_extra_field() -> None:
    kwargs = _valid_chunk_kwargs()
    kwargs["unknown"] = "x"
    with pytest.raises(ValidationError):
        RetrievedChunk(**kwargs)  # type: ignore[arg-type]


def test_message_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Message(role="user", content="hi", extra="bad")  # type: ignore[call-arg]


def test_llm_result_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        LLMResult(  # type: ignore[call-arg]
            answer="x",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
            extra="bad",
        )


def test_text_delta_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TextDelta(text="x", extra="bad")  # type: ignore[call-arg]


def test_final_rejects_extra_field() -> None:
    result = LLMResult(answer="x", input_tokens=1, output_tokens=1, estimated_cost_usd=0.0)
    with pytest.raises(ValidationError):
        Final(result=result, extra="bad")  # type: ignore[call-arg]


def test_pipeline_result_rejects_extra_field() -> None:
    chunk = RetrievedChunk(**_valid_chunk_kwargs())  # type: ignore[arg-type]
    usage = LLMResult(answer="x", input_tokens=1, output_tokens=1, estimated_cost_usd=0.0)
    with pytest.raises(ValidationError):
        PipelineResult(  # type: ignore[call-arg]
            answer="x",
            chunks=[chunk],
            prompt_token_count=1,
            prompt_template_id="v1",
            usage=usage,
            trace_id=UUID("00000000-0000-4000-8000-000000000000"),
            extra="bad",
        )


# ---------------------------------------------------------------------------
# Test 4: SDK isolation -- protocols.py and types.py must not import SDKs
# ---------------------------------------------------------------------------


def _find_real_import_lines(path: str, module: str) -> list[str]:
    """Return non-comment, non-string-literal lines that are real imports.

    The naive substring search ``"import voyageai" in src`` matches the ban
    documented in the module docstring itself. We instead read the file
    line-by-line and skip docstring blocks (lines bracketed by triple-quote
    markers) and comment lines.
    """
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8").splitlines()
    in_doc = False
    real: list[str] = []
    for raw in text:
        stripped = raw.strip()
        # Toggle docstring state on lines that contain triple-quoted block markers.
        triple_count = stripped.count('"""')
        if triple_count == 1:
            in_doc = not in_doc
            continue
        if in_doc or triple_count >= 2:
            # Either inside a docstring block, or a single-line docstring that
            # opens-and-closes on the same line — neither counts as a real import.
            continue
        if stripped.startswith("#"):
            continue
        # Real Python import statements at module scope.
        if stripped.startswith(f"import {module}") or stripped.startswith(f"from {module}"):
            real.append(raw)
    return real


def test_protocols_module_does_not_import_voyageai_or_anthropic() -> None:
    """D-2.38: voyageai/anthropic only in their dedicated adapter files."""
    assert (
        _find_real_import_lines("tracer_ai/rag/protocols.py", "voyageai") == []
    ), "D-2.38: voyageai must only be imported in rag/embedder.py"
    assert (
        _find_real_import_lines("tracer_ai/rag/protocols.py", "anthropic") == []
    ), "D-2.38: anthropic must only be imported in rag/llm.py"


def test_types_module_does_not_import_voyageai_or_anthropic() -> None:
    """D-2.38: types.py is stack-agnostic."""
    assert _find_real_import_lines("tracer_ai/rag/types.py", "voyageai") == []
    assert _find_real_import_lines("tracer_ai/rag/types.py", "anthropic") == []
