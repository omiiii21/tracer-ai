"""Tests for tracer_ai.corpus.loader (Phase 3 Plan 02 -- Task 1).

Asserts:
  1. `discover()` returns the .md paths in `fixtures/claude-docs-sample/` (>=2).
  2. `load(auth.md)` returns a `RawDoc` with doc_id="claude-docs/auth",
     doc_section="auth", non-empty text.
  3. `_infer_section()` warns + defaults to "agent-sdk-overview" when neither
     parent dir nor file stem matches the canonical 12-section enum.
  4. `RawDoc(extra='forbid')` rejects unknown fields.
  5. `load_url()` parses a URL through a mocked transport into a RawDoc.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
import pytest
import structlog
from pydantic import ValidationError
from structlog.testing import capture_logs

from tracer_ai.corpus.loader import (
    _infer_section,
    discover,
    discover_urls,
    load,
    load_url,
)
from tracer_ai.corpus.types import RawDoc

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "claude-docs-sample"


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_returns_at_least_two_md_paths() -> None:
    paths = await discover(FIXTURE_DIR)
    assert len(paths) >= 2
    assert all(p.suffix == ".md" for p in paths)
    # Sorted -> deterministic ingest order
    assert paths == sorted(paths)


@pytest.mark.asyncio
async def test_discover_returns_empty_for_empty_dir(tmp_path: Path) -> None:
    paths = await discover(tmp_path)
    assert paths == []


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_auth_fixture_returns_expected_rawdoc() -> None:
    doc = await load(FIXTURE_DIR / "auth.md")
    assert isinstance(doc, RawDoc)
    assert doc.doc_id == "claude-docs/auth"
    assert doc.doc_section == "auth"
    assert doc.text.strip()
    assert doc.source_url.startswith("file://")
    assert isinstance(doc.loaded_at, datetime)


@pytest.mark.asyncio
async def test_load_messages_fixture_returns_messages_section() -> None:
    doc = await load(FIXTURE_DIR / "messages.md")
    assert doc.doc_id == "claude-docs/messages"
    assert doc.doc_section == "messages"


# ---------------------------------------------------------------------------
# _infer_section()
# ---------------------------------------------------------------------------


def test_infer_section_matches_file_stem() -> None:
    assert _infer_section(Path("/x/y/auth.md")) == "auth"
    assert _infer_section(Path("/x/messages/whatever.md")) == "messages"


def test_infer_section_defaults_and_warns_on_unknown() -> None:
    # Configure structlog to route through the testing capture processor.
    structlog.configure(
        processors=[structlog.testing.LogCapture()],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        cache_logger_on_first_use=False,
    )
    with capture_logs() as logs:
        section = _infer_section(Path("/some/random/unknown.md"))
    assert section == "agent-sdk-overview"
    assert any(
        e["event"] == "corpus_section_unknown" and e.get("log_level") == "warning" for e in logs
    )


# ---------------------------------------------------------------------------
# RawDoc validation
# ---------------------------------------------------------------------------


def test_rawdoc_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        RawDoc(  # type: ignore[call-arg]
            doc_id="x",
            source_url="file:///x",
            text="hi",
            doc_section="auth",
            loaded_at=datetime.now(),
            unexpected="boom",
        )


def test_rawdoc_rejects_unknown_section() -> None:
    with pytest.raises(ValidationError):
        RawDoc(
            doc_id="x",
            source_url="file:///x",
            text="hi",
            doc_section="not-a-real-section",  # type: ignore[arg-type]
            loaded_at=datetime.now(),
        )


# ---------------------------------------------------------------------------
# discover_urls() + load_url()
# ---------------------------------------------------------------------------


def test_discover_urls_is_identity() -> None:
    urls = ["https://docs.anthropic.com/a", "https://docs.anthropic.com/b"]
    assert discover_urls(urls) == urls


@pytest.mark.asyncio
async def test_load_url_returns_rawdoc_via_mock_transport() -> None:
    body = "# Hello\n\nFake docs body."

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        doc = await load_url("https://docs.anthropic.com/en/api/messages", client=client)
    assert doc.doc_id == "url/messages"
    assert doc.source_url == "https://docs.anthropic.com/en/api/messages"
    assert doc.text == body
    # URL ingest always defaults section to agent-sdk-overview per plan.
    assert doc.doc_section == "agent-sdk-overview"


@pytest.mark.asyncio
async def test_load_url_raises_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await load_url("https://example/x", client=client)
