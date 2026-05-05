"""Tests for tracer_ai.tracer.writer (Phase 3 Plan 01).

Asserts:
  1. ``NoopTraceWriter`` and ``StdoutTraceWriter`` are structurally typed as
     ``TraceWriter`` (runtime_checkable Protocol).
  2. ``await NoopTraceWriter().emit(span)`` returns None.
  3. ``StdoutTraceWriter.emit`` produces a structlog event captured by
     ``structlog.testing.capture_logs()``.
  4. ``writer.py`` does NOT contain ``from opentelemetry`` imports (ADR 005).
  5. ``Span`` Pydantic model rejects extra fields (extra='forbid').
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from tracer_ai.tracer.writer import (
    NoopTraceWriter,
    Span,
    StdoutTraceWriter,
    TraceWriter,
)


def _valid_span() -> Span:
    return Span(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        name="rag.request",
        started_at=datetime.now(UTC),
        ended_at=None,
        attrs={"gen_ai.provider.name": "anthropic"},
        payload_id=None,
    )


# ---------------------------------------------------------------------------
# Protocol structural typing
# ---------------------------------------------------------------------------


def test_noop_writer_is_structurally_a_trace_writer() -> None:
    assert isinstance(NoopTraceWriter(), TraceWriter)


def test_stdout_writer_is_structurally_a_trace_writer() -> None:
    assert isinstance(StdoutTraceWriter(), TraceWriter)


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_noop_writer_emit_returns_none() -> None:
    writer = NoopTraceWriter()
    span = _valid_span()
    result = await writer.emit(span)
    assert result is None


@pytest.mark.asyncio
async def test_stdout_writer_emit_logs_via_structlog() -> None:
    writer = StdoutTraceWriter()
    span = _valid_span()
    with capture_logs() as logs:
        await writer.emit(span)
    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "span_emitted"
    assert event["log_level"] == "info"
    # Span attributes must be carried through as kwargs (model_dump)
    assert event["name"] == "rag.request"


# ---------------------------------------------------------------------------
# Span model: extra='forbid'
# ---------------------------------------------------------------------------


def test_span_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Span(  # type: ignore[call-arg]
            trace_id=uuid4(),
            span_id=uuid4(),
            parent_span_id=None,
            name="rag.request",
            started_at=datetime.now(UTC),
            unknown="bad",
        )


# ---------------------------------------------------------------------------
# ADR 005 / D-2.40 — no opentelemetry runtime imports in writer.py
# ---------------------------------------------------------------------------


def test_writer_module_has_no_opentelemetry_import() -> None:
    """ADR 005: tracer_ai/tracer/writer.py must not import ``opentelemetry``.

    The custom Span dataclass + Pydantic model is the runtime contract;
    OTel attribute names live as bare-string constants in span.py.
    """
    src = Path("tracer_ai/tracer/writer.py").read_text(encoding="utf-8")
    in_doc = False
    real: list[str] = []
    for raw in src.splitlines():
        stripped = raw.strip()
        triple_count = stripped.count('"""')
        if triple_count == 1:
            in_doc = not in_doc
            continue
        if in_doc or triple_count >= 2:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("from opentelemetry") or stripped.startswith("import opentelemetry"):
            real.append(raw)
    assert not real, f"ADR 005 violation: opentelemetry imports found: {real}"


# ---------------------------------------------------------------------------
# Smoke: structlog logger is the standard one
# ---------------------------------------------------------------------------


def test_writer_uses_structlog() -> None:
    """The writer should create a structlog logger at module top.

    structlog returns a ``BoundLoggerLazyProxy`` until first use; the proxy
    has a ``.info()`` method, which is the only contract the writer relies on.
    PATTERNS.md §"Pattern: structlog logger at module top".
    """
    import tracer_ai.tracer.writer as mod

    assert hasattr(mod, "log")
    # Duck-type check: anything from structlog.get_logger() must expose .info()
    assert callable(mod.log.info)
    # Belt-and-suspenders: it really is a structlog product
    assert mod.log.__class__.__module__.startswith("structlog.")
