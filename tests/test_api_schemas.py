"""Tests for tracer_ai.api.schemas (Phase 3 Plan 01).

Six behavioral assertions matching the plan <behavior> block:
  1. ChatRequest(question="") raises; ChatRequest(question="hi") passes.
  2. FeedbackRequest rating must be -1 or 1 (mirrors DB CHECK constraint).
  3. Citation.score must be in [0.0, 1.0].
  4. IngestUrlsRequest URL list rejects malformed URLs (no http(s)://).
  5. ChunkingConfig rejects chunk_size < 100.
  6. Every model rejects extra fields (extra='forbid').

Plus structural smoke checks: every model importable + Literal[-1, 1] mirrors
DB CHECK at alembic/versions/0001_initial.py:127.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from tracer_ai.api.schemas import (
    ChatFinal,
    ChatRequest,
    ChunkingConfig,
    ChunkingConfigPatch,
    Citation,
    CorpusState,
    DocSummary,
    FeedbackRequest,
    FeedbackResponse,
    IngestResponse,
    IngestSourceRequest,
    IngestStatus,
    IngestUrlsRequest,
)

# ---------------------------------------------------------------------------
# Test 1: ChatRequest length bounds
# ---------------------------------------------------------------------------


def test_chat_request_empty_question_raises() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question="")


def test_chat_request_valid_question_passes() -> None:
    req = ChatRequest(question="hi")
    assert req.question == "hi"
    assert req.thread_id is None


def test_chat_request_question_too_long_raises() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question="x" * 4001)


# ---------------------------------------------------------------------------
# Test 2: FeedbackRequest rating Literal[-1, 1]
# ---------------------------------------------------------------------------


def test_feedback_request_rating_zero_raises() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(trace_id=uuid4(), rating=0)  # type: ignore[arg-type]


def test_feedback_request_rating_minus_one_passes() -> None:
    fb = FeedbackRequest(trace_id=uuid4(), rating=-1)
    assert fb.rating == -1


def test_feedback_request_rating_one_passes() -> None:
    fb = FeedbackRequest(trace_id=uuid4(), rating=1)
    assert fb.rating == 1


# ---------------------------------------------------------------------------
# Test 3: Citation.score in [0.0, 1.0]
# ---------------------------------------------------------------------------


def _valid_citation_kwargs() -> dict[str, object]:
    return {
        "idx": 1,
        "doc_id": "claude-docs/auth",
        "doc_section": "auth",
        "section_title": "API Keys",
        "source_url": "https://example/auth",
        "content": "Set the x-api-key header.",
        "score": 0.5,
    }


def test_citation_score_above_one_raises() -> None:
    kwargs = _valid_citation_kwargs()
    kwargs["score"] = 1.5
    with pytest.raises(ValidationError):
        Citation(**kwargs)  # type: ignore[arg-type]


def test_citation_idx_zero_raises() -> None:
    """idx must be >= 1 (citation markers are 1-indexed)."""
    kwargs = _valid_citation_kwargs()
    kwargs["idx"] = 0
    with pytest.raises(ValidationError):
        Citation(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test 4: IngestUrlsRequest URL validation
# ---------------------------------------------------------------------------


def test_ingest_urls_request_rejects_non_url() -> None:
    with pytest.raises(ValidationError) as exc:
        IngestUrlsRequest(urls=["not-a-url"])
    # UI-SPEC §4.6: error message should reference Line N
    assert (
        "Line 1" in str(exc.value)
        or "line 1" in str(exc.value).lower()
        or "url" in str(exc.value).lower()
    )


def test_ingest_urls_request_accepts_https() -> None:
    req = IngestUrlsRequest(urls=["https://example.com/docs/auth"])
    assert req.urls == ["https://example.com/docs/auth"]


def test_ingest_urls_request_accepts_http_too() -> None:
    """Spec allows http:// for local dev (e.g., http://localhost:9000)."""
    req = IngestUrlsRequest(urls=["http://localhost:9000/doc"])
    assert req.urls[0].startswith("http://")


def test_ingest_urls_request_empty_list_raises() -> None:
    with pytest.raises(ValidationError):
        IngestUrlsRequest(urls=[])


def test_ingest_urls_request_too_many_raises() -> None:
    with pytest.raises(ValidationError):
        IngestUrlsRequest(urls=[f"https://x.com/{i}" for i in range(101)])


# ---------------------------------------------------------------------------
# Test 5: ChunkingConfig bounds
# ---------------------------------------------------------------------------


def test_chunking_config_chunk_size_below_100_raises() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(chunk_size=99, overlap=0)


def test_chunking_config_chunk_size_above_4000_raises() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(chunk_size=4001, overlap=0)


def test_chunking_config_overlap_above_500_raises() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(chunk_size=900, overlap=501)


def test_chunking_config_valid_passes() -> None:
    cfg = ChunkingConfig(chunk_size=900, overlap=100)
    assert cfg.chunk_size == 900 and cfg.overlap == 100


# ---------------------------------------------------------------------------
# Test 6: extra='forbid' on every model
# ---------------------------------------------------------------------------


def test_chunking_config_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(chunk_size=900, overlap=100, extra="x")  # type: ignore[call-arg]


def test_chat_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question="hi", extra="x")  # type: ignore[call-arg]


def test_feedback_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(trace_id=uuid4(), rating=1, extra="x")  # type: ignore[call-arg]


def test_citation_rejects_extra_field() -> None:
    kwargs = _valid_citation_kwargs()
    kwargs["extra"] = "x"
    with pytest.raises(ValidationError):
        Citation(**kwargs)  # type: ignore[arg-type]


def test_ingest_source_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        IngestSourceRequest(source="claude-docs", extra="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Smoke: every model importable and instantiable
# ---------------------------------------------------------------------------


def test_chat_final_constructs() -> None:
    citation = Citation(**_valid_citation_kwargs())  # type: ignore[arg-type]
    final = ChatFinal(
        trace_id=uuid4(),
        cited_chunks=[citation],
        latency_ms=1500,
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=0.001,
    )
    assert final.latency_ms == 1500


def test_feedback_response_constructs() -> None:
    resp = FeedbackResponse(id=uuid4(), created_at=datetime.now(UTC))
    assert isinstance(resp.id, UUID)


def test_doc_summary_constructs() -> None:
    doc = DocSummary(
        id="claude-docs/auth",
        doc_section="auth",
        source_url="https://example/auth",
        chunk_count=18,
        ingested_at=datetime.now(UTC),
    )
    assert doc.chunk_count == 18


def test_corpus_state_constructs() -> None:
    cs = CorpusState(
        doc_count=1,
        chunk_count=18,
        embedding_model="voyage-code-3",
        embedding_model_version="voyage-code-3@2025-09",
        last_indexed_at=datetime.now(UTC),
        docs=[
            DocSummary(
                id="claude-docs/auth",
                doc_section="auth",
                source_url="https://example/auth",
                chunk_count=18,
                ingested_at=datetime.now(UTC),
            )
        ],
        chunking_config=None,
    )
    assert cs.doc_count == 1


def test_ingest_response_constructs() -> None:
    resp = IngestResponse(ingest_job_id=uuid4(), status="queued")
    assert resp.status == "queued"


def test_ingest_status_constructs() -> None:
    s = IngestStatus(
        ingest_job_id=uuid4(),
        status="running",
        started_at=datetime.now(UTC),
        finished_at=None,
        docs_processed=5,
        docs_total=20,
        chunks_written=120,
        progress=0.25,
        error=None,
    )
    assert s.progress == 0.25


def test_ingest_status_progress_above_one_raises() -> None:
    with pytest.raises(ValidationError):
        IngestStatus(
            ingest_job_id=uuid4(),
            status="running",
            started_at=datetime.now(UTC),
            finished_at=None,
            docs_processed=5,
            docs_total=20,
            chunks_written=120,
            progress=1.5,
            error=None,
        )


def test_chunking_config_patch_alias_of_chunking_config() -> None:
    """ChunkingConfigPatch is the same shape as ChunkingConfig."""
    patch = ChunkingConfigPatch(chunk_size=600, overlap=50)
    assert patch.chunk_size == 600


# ---------------------------------------------------------------------------
# Phase 5 Plan 05 (D-5.17 / DASH-01..04) -- TimeseriesBucket / TimeseriesResponse
# ---------------------------------------------------------------------------


def test_timeseries_bucket_full_row_parses() -> None:
    """SC1: TimeseriesBucket parses a fully-populated bucket row."""
    from tracer_ai.api.schemas import TimeseriesBucket

    bucket = TimeseriesBucket(
        bucket_start=datetime.now(UTC),
        latency_p50=100.0,
        latency_p95=250.0,
        cost_sum=0.001,
        faithfulness_mean=0.85,
        feedback_down_ratio=0.1,
        request_count=5,
    )
    assert bucket.request_count == 5
    assert bucket.faithfulness_mean == 0.85


def test_timeseries_bucket_empty_bucket_parses() -> None:
    """SC2: empty bucket (no traces in window) parses with NULL aggregates + count=0."""
    from tracer_ai.api.schemas import TimeseriesBucket

    bucket = TimeseriesBucket(
        bucket_start=datetime.now(UTC),
        latency_p50=None,
        latency_p95=None,
        cost_sum=0.0,
        faithfulness_mean=None,
        feedback_down_ratio=None,
        request_count=0,
    )
    assert bucket.request_count == 0
    assert bucket.faithfulness_mean is None
    assert bucket.feedback_down_ratio is None


def test_timeseries_bucket_rejects_extra_field() -> None:
    """SC3: extra='forbid' on TimeseriesBucket."""
    from tracer_ai.api.schemas import TimeseriesBucket

    with pytest.raises(ValidationError):
        TimeseriesBucket(  # type: ignore[call-arg]
            bucket_start=datetime.now(UTC),
            cost_sum=0.0,
            request_count=0,
            extra="x",
        )


def test_timeseries_response_window_literal_24h_parses() -> None:
    """SC4a: window='24h' is allowed."""
    from tracer_ai.api.schemas import TimeseriesResponse

    resp = TimeseriesResponse(window="24h", buckets=[])
    assert resp.window == "24h"


def test_timeseries_response_invalid_window_raises() -> None:
    """SC4b: window='5m' fails Literal validation."""
    from tracer_ai.api.schemas import TimeseriesResponse

    with pytest.raises(ValidationError):
        TimeseriesResponse(window="5m", buckets=[])  # type: ignore[arg-type]


def test_timeseries_bucket_rejects_negative_request_count() -> None:
    """SC5: request_count must be >= 0."""
    from tracer_ai.api.schemas import TimeseriesBucket

    with pytest.raises(ValidationError):
        TimeseriesBucket(
            bucket_start=datetime.now(UTC),
            cost_sum=0.0,
            request_count=-1,
        )
