"""Tests for tracer_ai.corpus.chunker (Phase 3 Plan 02 -- Task 2).

Critical invariants:
  1. T-03-02-01: every chunk has even count of ``` fences (fence-safety).
  2. Headers force splits when NOT inside a fence; multiple headers -> multiple chunks.
  3. Re-running the chunker on the same input yields identical UUIDs (idempotent).
  4. Each chunk's metadata carries section_title + header_path + source_url.
  5. chunk_size + overlap configurability is honored.
  6. Doc with NO headers chunks gracefully (section_title="", chunks >= 1).
  7. Bounds: __init__ rejects out-of-range chunk_size / overlap.
  8. Chunker Protocol structurally accepts MarkdownHeaderChunker.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tracer_ai.corpus.chunker import Chunker, MarkdownHeaderChunker
from tracer_ai.corpus.types import RawDoc


def _doc(text: str, doc_id: str = "t", section: str = "auth") -> RawDoc:
    return RawDoc(
        doc_id=doc_id,
        source_url="file:///fixture",
        text=text,
        doc_section=section,  # type: ignore[arg-type]
        loaded_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Test 1 -- CRITICAL: fence safety
# ---------------------------------------------------------------------------


def test_chunker_never_splits_inside_fence() -> None:
    """T-03-02-01: every chunk has even ``` count even under aggressive splits."""
    text = (
        "## Auth\n"
        "Intro text describing authentication.\n"
        "```python\n"
        "def f():\n"
        "    pass\n"
        "    pass\n"
        "    pass\n"
        "```\n"
        "## Messages\n"
        "More text describing messages.\n"
        "```bash\n"
        "curl -X POST https://api.example/x\n"
        "```\n"
        "Trailing prose.\n"
    )
    # Force a tiny chunk_size to provoke aggressive splitting.
    chunks = MarkdownHeaderChunker(chunk_size=100, overlap=10).split(_doc(text))
    assert chunks, "expected at least one chunk"
    for c in chunks:
        assert (
            c.content.count("```") % 2 == 0
        ), f"chunk {c.chunk_index} has unmatched fence: {c.content!r}"


def test_chunker_handles_header_inside_fence_as_text_not_split() -> None:
    """A '## ' line INSIDE a fenced code block must NOT trigger a split."""
    text = (
        "Intro.\n"
        "```python\n"
        "## not a real header -- code comment\n"
        "x = 1\n"
        "```\n"
        "## Real Header\n"
        "After-real-header content.\n"
    )
    chunks = MarkdownHeaderChunker(chunk_size=2000, overlap=0).split(_doc(text))
    # Exactly one real header => 2 chunks (one before, one after).
    assert len(chunks) == 2
    # Fence content must be preserved entirely in chunk 0 (the "## not a real
    # header" line lives inside the fenced block, not as its own chunk).
    assert "```python" in chunks[0].content
    assert "## not a real header" in chunks[0].content
    # Second chunk starts at the real header.
    assert chunks[1].content.startswith("## Real Header")


# ---------------------------------------------------------------------------
# Test 2: multiple headers force multiple chunks
# ---------------------------------------------------------------------------


def test_chunker_multiple_h2_headers_yield_multiple_chunks() -> None:
    text = (
        "## Section One\nBody one.\n"
        "## Section Two\nBody two.\n"
        "## Section Three\nBody three.\n"
    )
    chunks = MarkdownHeaderChunker(chunk_size=2000, overlap=0).split(_doc(text))
    assert len(chunks) >= 3
    titles = [c.metadata["section_title"] for c in chunks]
    assert "Section One" in titles
    assert "Section Two" in titles
    assert "Section Three" in titles


# ---------------------------------------------------------------------------
# Test 3: deterministic UUIDs
# ---------------------------------------------------------------------------


def test_chunker_deterministic_uuids() -> None:
    text = "## A\nbody.\n## B\nbody.\n"
    a = MarkdownHeaderChunker().split(_doc(text, doc_id="claude-docs/x"))
    b = MarkdownHeaderChunker().split(_doc(text, doc_id="claude-docs/x"))
    assert [c.id for c in a] == [c.id for c in b]
    # And distinct doc_ids -> distinct UUIDs even at the same chunk_index.
    c = MarkdownHeaderChunker().split(_doc(text, doc_id="claude-docs/y"))
    assert a[0].id != c[0].id


# ---------------------------------------------------------------------------
# Test 4: metadata carries section_title + header_path + source_url
# ---------------------------------------------------------------------------


def test_chunker_metadata_includes_header_path_and_source_url() -> None:
    text = "## Auth\nbody.\n### Rotation\nrotation body.\n"
    chunks = MarkdownHeaderChunker(chunk_size=2000, overlap=0).split(_doc(text))
    assert len(chunks) >= 2
    rotation = next(c for c in chunks if c.metadata["section_title"] == "Rotation")
    assert rotation.metadata["header_path"] == "Auth > Rotation"
    assert rotation.metadata["source_url"].startswith("file://")


# ---------------------------------------------------------------------------
# Test 5: chunk_size honored (smaller chunk_size -> more chunks on same doc)
# ---------------------------------------------------------------------------


def test_chunker_chunk_size_is_honored() -> None:
    # Long body without headers so size is the only split driver.
    body = "Lorem ipsum dolor sit amet. " * 400
    text = f"## A\n{body}\n"
    big = MarkdownHeaderChunker(chunk_size=900, overlap=50).split(_doc(text))
    small = MarkdownHeaderChunker(chunk_size=300, overlap=20).split(_doc(text))
    assert len(small) > len(big)


# ---------------------------------------------------------------------------
# Test 6: doc with NO headers still chunks
# ---------------------------------------------------------------------------


def test_chunker_doc_without_headers_yields_at_least_one_chunk() -> None:
    text = "Just a plain doc, no headers here at all. " * 50
    chunks = MarkdownHeaderChunker(chunk_size=2000, overlap=0).split(_doc(text))
    assert len(chunks) >= 1
    # No header -> empty section_title, empty header_path
    for c in chunks:
        assert c.metadata["section_title"] == ""
        assert c.metadata["header_path"] == ""


# ---------------------------------------------------------------------------
# Test 7: bounds enforced
# ---------------------------------------------------------------------------


def test_chunker_rejects_out_of_range_chunk_size() -> None:
    with pytest.raises(ValueError):
        MarkdownHeaderChunker(chunk_size=50)
    with pytest.raises(ValueError):
        MarkdownHeaderChunker(chunk_size=5000)


def test_chunker_rejects_overlap_geq_chunk_size() -> None:
    with pytest.raises(ValueError):
        MarkdownHeaderChunker(chunk_size=200, overlap=200)
    with pytest.raises(ValueError):
        MarkdownHeaderChunker(chunk_size=200, overlap=-1)


# ---------------------------------------------------------------------------
# Test 8: Protocol structural acceptance
# ---------------------------------------------------------------------------


def test_markdown_header_chunker_satisfies_chunker_protocol() -> None:
    impl = MarkdownHeaderChunker()
    assert isinstance(impl, Chunker)


def test_chunker_h3_inheritance_falls_back_to_h2() -> None:
    """An h3 reached after an h2 keeps the h2 in the breadcrumb."""
    text = "## Top\nbody.\n### Sub\nsub body.\n### Sub2\nmore.\n"
    chunks = MarkdownHeaderChunker(chunk_size=2000, overlap=0).split(_doc(text))
    sub = next(c for c in chunks if c.metadata["section_title"] == "Sub")
    sub2 = next(c for c in chunks if c.metadata["section_title"] == "Sub2")
    assert sub.metadata["header_path"] == "Top > Sub"
    assert sub2.metadata["header_path"] == "Top > Sub2"
