"""Pydantic v2 strict-mode wire shapes for every Phase 3 FastAPI route.

Source-of-truth for the wire contract once Phase 3 ships (per docs/api.md
preamble: "the schemas in this file are authoritative until Phase 3
RAG-05 / CHAT-* / ADMN-* ships; at that point tracer_ai/api/schemas.py
becomes source-of-truth"). FastAPI auto-emits /openapi.json from these
runtime models — no hand-maintained OpenAPI YAML is needed.

Every model uses ``model_config = ConfigDict(extra="forbid")`` per the
strict-mode pattern from ``tracer_ai/api/health.py:27-33``. Unknown fields
are rejected at validation time — closes the silent contract-drift bug
class (Pitfall E / threat T-01-06-01 / T-03-01-01).

``FeedbackRequest.rating`` is ``Literal[-1, 1]`` to mirror the DB CHECK
constraint at ``alembic/versions/0001_initial.py:127``. Both layers must
agree on allowed values; drift = bug (T-03-01-02 mitigation).

Per D-2.38 / D-2.39 / tests/test_anti_patterns.py: NO SDK imports here;
NO Pydantic v1 ``class Config:`` blocks (use ``ConfigDict``).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# /chat  (POST)
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """POST /chat request body — see docs/api.md §"POST /chat"."""

    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, Field(min_length=1, max_length=4000)]
    thread_id: str | None = None


class Citation(BaseModel):
    """One inline citation in a chat answer (1-indexed by ``idx``)."""

    model_config = ConfigDict(extra="forbid")

    idx: Annotated[int, Field(ge=1)]
    doc_id: str
    doc_section: str
    section_title: str
    source_url: str
    content: str
    score: Annotated[float, Field(ge=0.0, le=1.0)]


class ChatFinal(BaseModel):
    """Final SSE event payload from POST /chat (event: final)."""

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    cited_chunks: list[Citation]
    latency_ms: Annotated[int, Field(ge=0)]
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    estimated_cost_usd: Annotated[float, Field(ge=0.0)]


# ---------------------------------------------------------------------------
# /feedback  (POST)
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    """POST /feedback request body.

    ``rating: Literal[-1, 1]`` mirrors the DB CHECK constraint at
    ``alembic/versions/0001_initial.py:127`` (cross-layer integrity per
    PATTERNS.md §"Pattern: Pydantic Literal mirrors DB CHECK").

    ``diagnosis_tag`` is intentionally ``str | None`` (not ``Literal``) —
    Phase 5 FBCK-05 finalizes the allowed-values set; locking it now would
    force a schema migration if the taxonomy changes during calibration.
    Documented allowed values (when populated):
    "Retrieval" | "PromptAssembly" | "LLM" | "CorpusStale" | "Other".
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    rating: Literal[-1, 1]
    comment: str | None = None
    diagnosis_tag: str | None = None


class FeedbackResponse(BaseModel):
    """POST /feedback response body."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# /admin/corpus  (GET)
# ---------------------------------------------------------------------------


class DocSummary(BaseModel):
    """Per-doc summary returned by GET /admin/corpus."""

    model_config = ConfigDict(extra="forbid")

    id: str
    doc_section: str
    source_url: str
    chunk_count: Annotated[int, Field(ge=0)]
    ingested_at: datetime


class ChunkingConfig(BaseModel):
    """Current chunker config — surfaced in CorpusState and PATCHed via /admin/chunking-config.

    Bounds match docs/api.md §"PATCH /admin/chunking-config":
    chunk_size in [100, 4000], overlap in [0, 500].
    """

    model_config = ConfigDict(extra="forbid")

    chunk_size: Annotated[int, Field(ge=100, le=4000)]
    overlap: Annotated[int, Field(ge=0, le=500)]


# ChunkingConfigPatch is the same shape as ChunkingConfig (PATCH replaces both fields).
ChunkingConfigPatch = ChunkingConfig


class CorpusState(BaseModel):
    """GET /admin/corpus response body."""

    model_config = ConfigDict(extra="forbid")

    doc_count: Annotated[int, Field(ge=0)]
    chunk_count: Annotated[int, Field(ge=0)]
    embedding_model: str
    embedding_model_version: str
    last_indexed_at: datetime | None
    docs: list[DocSummary]
    chunking_config: ChunkingConfig | None = None


# ---------------------------------------------------------------------------
# /admin/ingest  (POST + GET)
# ---------------------------------------------------------------------------


class IngestSourceRequest(BaseModel):
    """POST /admin/ingest with a named source bundle (currently only "claude-docs")."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["claude-docs"]


_URL_PATTERN = re.compile(r"^https?://")


class IngestUrlsRequest(BaseModel):
    """POST /admin/ingest with an explicit URL list.

    Each URL must start with ``http://`` or ``https://``. Per UI-SPEC §4.6,
    error messages reference the 1-indexed URL line ("Line 1: not a URL").
    """

    model_config = ConfigDict(extra="forbid")

    urls: Annotated[list[str], Field(min_length=1, max_length=100)]

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, v: list[str]) -> list[str]:
        for i, u in enumerate(v):
            if not _URL_PATTERN.match(u):
                raise ValueError(f"Line {i + 1}: not a URL (must start with http:// or https://)")
        return v


# Discriminated by field shape at the route layer (FastAPI accepts either body).
IngestRequest = IngestSourceRequest | IngestUrlsRequest


class IngestResponse(BaseModel):
    """POST /admin/ingest response body — returns immediately with job id."""

    model_config = ConfigDict(extra="forbid")

    ingest_job_id: UUID
    status: Literal["queued"]


class IngestStatus(BaseModel):
    """GET /admin/ingest/{ingest_job_id} response body — polled every 2s by UI."""

    model_config = ConfigDict(extra="forbid")

    ingest_job_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    started_at: datetime | None
    finished_at: datetime | None
    docs_processed: Annotated[int, Field(ge=0)]
    docs_total: int | None
    chunks_written: Annotated[int, Field(ge=0)]
    progress: Annotated[float, Field(ge=0.0, le=1.0)]
    error: str | None = None


# ---------------------------------------------------------------------------
# /traces  (GET — list + detail)  Phase 4 Plan 04 — EXPL-01 / EXPL-02
# ---------------------------------------------------------------------------


class TraceListItem(BaseModel):
    """One row in GET /traces response (docs/api.md §4).

    ``latency_ms`` and ``estimated_cost_usd`` are REQUIRED per docs/api.md §4
    even though the underlying DB columns are NULLable (in-flight traces may
    have NULL latency_ms before _emit_root finishes). The store layer filters
    in-flight traces out of list_traces (``WHERE latency_ms IS NOT NULL``);
    for get_trace the store coalesces NULLs to 0 / 0.0 for the detail view.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    started_at: datetime
    query_text: str
    latency_ms: int
    estimated_cost_usd: float
    faithfulness: float | None = None
    feedback_rating: Literal[-1, 1] | None = None


class TraceListResponse(BaseModel):
    """GET /traces response envelope (docs/api.md §4)."""

    model_config = ConfigDict(extra="forbid")

    items: list[TraceListItem]
    next_cursor: str | None = None


class SpanInResponse(BaseModel):
    """Per-span shape inside GET /traces/{trace_id} (docs/api.md §5)."""

    model_config = ConfigDict(extra="forbid")

    span_id: UUID
    parent_span_id: UUID | None = None
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    attrs: dict[str, Any]


class SpanPayloadResponse(BaseModel):
    """Per-span payload entry inside GET /traces/{trace_id}.payloads (docs/api.md §5)."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]


class TraceDetailResponse(BaseModel):
    """GET /traces/{trace_id} response envelope (docs/api.md §5)."""

    model_config = ConfigDict(extra="forbid")

    trace: TraceListItem
    spans: list[SpanInResponse]
    payloads: dict[str, SpanPayloadResponse]


# ---------------------------------------------------------------------------
# Common Error Envelope (docs/api.md §"Common Error Envelope")
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """One field-level error inside ErrorResponse.details."""

    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    message: str


class ErrorResponse(BaseModel):
    """Canonical error envelope returned on 4xx / 5xx responses.

    ``error_code`` is uppercase + underscores (e.g., ``INVALID_REQUEST``,
    ``TRACE_NOT_FOUND``). ``request_id`` correlates to the rag.request root
    span trace_id so an operator can pivot from the error envelope to the
    trace explorer without re-keying.
    """

    model_config = ConfigDict(extra="forbid")

    error_code: Annotated[str, Field(pattern=r"^[A-Z_]+$")]
    message: str
    details: list[ErrorDetail] = []
    request_id: UUID
