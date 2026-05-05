"""TraceWriter Protocol + Span model + Noop / Stdout adapters (Phase 3).

Phase 4 TRCR-06 adds ``PostgresTraceWriter`` against the same Protocol —
the pipeline calls ``writer.emit(span)`` per stage and a one-line
lifespan swap upgrades dev (Stdout) to production (Postgres).

Per ADR 005 / D-2.40: NO ``from opentelemetry import`` lines anywhere.
The ``Span`` model below carries the JSONB ``attrs`` dict whose keys are
the bare-string constants from ``tracer_ai/tracer/span.py``.

Per PATTERNS.md §"Backend Subsystem 5" (lines 264-282).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

log = structlog.get_logger()


class Span(BaseModel):
    """A single trace span (Phase 3 dataclass; Phase 4 TRCR-01 hardens this).

    Maps 1:1 to the ``spans`` table in ``alembic/versions/0001_initial.py`` —
    Phase 4's ``PostgresTraceWriter`` will INSERT rows from this shape.
    Attribute keys in ``attrs`` come from ``tracer_ai/tracer/span.py``
    constants (e.g., ``GEN_AI_PROVIDER_NAME``); Phase 3 pipeline emit sites
    consume the constants by name.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None = None
    name: str  # e.g. "rag.request", "rag.retrieve", "rag.prompt_assemble", "rag.llm_call"
    started_at: datetime
    ended_at: datetime | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    payload_id: UUID | None = None


@runtime_checkable
class TraceWriter(Protocol):
    """Emit a ``Span`` to a backing store (Phase 3 default = Noop)."""

    async def emit(self, span: Span) -> None: ...


class NoopTraceWriter:
    """Default writer for tests + early dev — drops every span silently."""

    async def emit(self, span: Span) -> None:
        return None


class StdoutTraceWriter:
    """Dev-convenience writer — logs each span as a structlog event.

    JSON-serializes the ``Span`` via ``model_dump(mode="json")`` so UUIDs
    and timestamps are stringified in the log line.
    """

    async def emit(self, span: Span) -> None:
        log.info("span_emitted", **span.model_dump(mode="json"))
