"""Header-aware, fence-safe markdown chunker (Phase 3 Plan 02, CORP-02).

Algorithm (RESEARCH.md §2):
  1. Walk the doc line-by-line, tracking `inside_fence: bool` (toggled by
     ``` or ~~~ at line start).
  2. h2/h3 markdown headers are split candidates ONLY when not in a fence.
  3. Emit at chunk_size tokens; never emit while inside a fence (T-03-02-01).
  4. Each chunk inherits the most recent enclosing ##/### heading text as
     `metadata.section_title` and the full breadcrumb as `metadata.header_path`.
  5. Chunk UUID is `uuid5(NAMESPACE_DNS, f"{doc_id}#{chunk_index}")` --
     deterministic so re-ingest is idempotent (RESEARCH.md §2 idempotency).

Token counting uses `tiktoken.cl100k_base` -- close-enough estimator per
RESEARCH.md §2 (Anthropic uses its own tokenizer; tiktoken is what we have).

Fence safety carry-overlap subtlety: the last `overlap` tokens of an emitted
chunk could open-but-not-close a fence (e.g. tail begins inside a code block
that the chunker properly bracketed in the prior chunk). To preserve the
T-03-02-01 invariant `chunk.content.count("```") % 2 == 0` for EVERY chunk,
we drop the overlap if its decoded text has odd fence parity. This trades
some semantic continuity for the load-bearing fence-safety guarantee.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable
from uuid import NAMESPACE_DNS, uuid5

import structlog
import tiktoken

from tracer_ai.corpus.types import Chunk, RawDoc

log = structlog.get_logger()

_ENC = tiktoken.get_encoding("cl100k_base")
_FENCE_RE = re.compile(r"^(```|~~~)")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)\s*$")


@runtime_checkable
class Chunker(Protocol):
    """Protocol every chunker implementation satisfies (CORP-02 contract)."""

    chunk_size: int
    overlap: int

    def split(self, doc: RawDoc) -> list[Chunk]: ...


class MarkdownHeaderChunker:
    """Header-aware, fence-safe chunker with configurable size + overlap.

    Defaults match ADR 006 (`chunk_size=900`, `overlap=100`). Bounds enforced
    in `__init__`: chunk_size in [100, 4000]; overlap in [0, min(500, chunk_size-1)].
    """

    def __init__(self, chunk_size: int = 900, overlap: int = 100) -> None:
        if chunk_size < 100 or chunk_size > 4000:
            raise ValueError(f"chunk_size must be in [100, 4000], got {chunk_size}")
        if overlap < 0 or overlap > 500 or overlap >= chunk_size:
            raise ValueError(f"overlap must be in [0, min(500, chunk_size-1)], got {overlap}")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, doc: RawDoc) -> list[Chunk]:
        lines = doc.text.split("\n")
        chunks: list[Chunk] = []
        inside_fence = False
        buffer_lines: list[str] = []
        buffer_tokens = 0
        current_h2 = ""
        current_h3 = ""
        header_path: list[str] = []

        def emit() -> None:
            """Flush `buffer_lines` into a `Chunk` and seed buffer with overlap tail."""
            nonlocal buffer_lines, buffer_tokens
            if not buffer_lines:
                return
            content = "\n".join(buffer_lines).strip()
            if not content:
                buffer_lines = []
                buffer_tokens = 0
                return
            idx = len(chunks)
            cid = uuid5(NAMESPACE_DNS, f"{doc.doc_id}#{idx}")
            section_title = current_h3 or current_h2
            chunks.append(
                Chunk(
                    id=cid,
                    doc_id=doc.doc_id,
                    chunk_index=idx,
                    doc_section=doc.doc_section,
                    content=content,
                    metadata={
                        "section_title": section_title,
                        "header_path": " > ".join(header_path) if header_path else "",
                        "source_url": doc.source_url,
                    },
                )
            )
            # Carry overlap tail forward, but only if the tail is fence-balanced.
            # Without this guard, the tail could begin mid-fence and the next
            # chunk would emit with an unmatched ``` (T-03-02-01 violation).
            if self.overlap > 0 and buffer_tokens > self.overlap:
                tail_tokens = _ENC.encode(content)[-self.overlap :]
                tail_text = _ENC.decode(tail_tokens)
                if tail_text.count("```") % 2 == 0 and tail_text.count("~~~") % 2 == 0:
                    buffer_lines = [tail_text]
                    buffer_tokens = self.overlap
                else:
                    # Drop unbalanced overlap to preserve fence-safety invariant.
                    buffer_lines = []
                    buffer_tokens = 0
            else:
                buffer_lines = []
                buffer_tokens = 0

        for raw_line in lines:
            # Fence toggle: ``` or ~~~ at line start flips the state. The fence
            # line itself is part of the current chunk on both open and close.
            if _FENCE_RE.match(raw_line):
                inside_fence = not inside_fence
                buffer_lines.append(raw_line)
                buffer_tokens += len(_ENC.encode(raw_line))
                continue

            # Header detection -- only valid split point when NOT inside a fence.
            m2 = _H2_RE.match(raw_line) if not inside_fence else None
            m3 = _H3_RE.match(raw_line) if not inside_fence else None
            is_header = bool(m2 or m3)
            if is_header and buffer_lines:
                # Emit the prior section before consuming the header line.
                emit()
            if m2:
                current_h2 = m2.group(1)
                current_h3 = ""
                header_path = [current_h2]
            elif m3:
                current_h3 = m3.group(1)
                header_path = [current_h2, current_h3] if current_h2 else [current_h3]

            line_tokens = _ENC.encode(raw_line)
            line_token_count = len(line_tokens)

            # Sub-split long text lines so a single multi-paragraph line cannot
            # produce one oversized chunk. Only applied OUTSIDE fences -- inside
            # a fence we keep the line intact to preserve code-block integrity.
            if not inside_fence and not is_header and line_token_count > self.chunk_size:
                # Slice the line into chunk_size-bounded segments, emitting
                # the buffered prefix between slices.
                cursor = 0
                while cursor < line_token_count:
                    take = self.chunk_size - buffer_tokens
                    if take <= 0:
                        emit()
                        take = self.chunk_size - buffer_tokens
                    segment_tokens = line_tokens[cursor : cursor + take]
                    segment_text = _ENC.decode(segment_tokens)
                    buffer_lines.append(segment_text)
                    buffer_tokens += len(segment_tokens)
                    cursor += len(segment_tokens)
                    if buffer_tokens >= self.chunk_size:
                        emit()
            else:
                buffer_lines.append(raw_line)
                buffer_tokens += line_token_count
                # Size-based emit: never split mid-fence (preserves T-03-02-01).
                if buffer_tokens >= self.chunk_size and not inside_fence:
                    emit()

        # Final flush of any remainder.
        emit()
        log.info(
            "chunker_split",
            doc_id=doc.doc_id,
            chunks=len(chunks),
            chunk_size=self.chunk_size,
            overlap=self.overlap,
        )
        return chunks
