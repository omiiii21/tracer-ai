"""Corpus dataclasses -- RawDoc + Chunk (Phase 3 Plan 02).

Pydantic v2 strict-mode (`extra="forbid"`); 12-section canonical taxonomy is
locked via `Literal[...]` (matches docs/eval/coverage_set.yaml `doc_section`
values + the chunks.doc_section column the chunker writes).

Stack-agnostic: imports stdlib + pydantic only (corpus is layer-1 in the
import DAG; SDK adapters live in `tracer_ai.rag.embedder` / `rag.llm` per D-2.38).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 12-section canonical taxonomy (Phase 1 docs/eval/coverage_set.yaml).
# Mirrored as a `Literal` so Pydantic rejects out-of-enum values at validation
# time -- prevents corpus drift across phases (Pitfall F mitigation per Plan 01-03).
DocSection = Literal[
    "auth",
    "models",
    "messages",
    "tools",
    "batches",
    "files",
    "citations",
    "vision",
    "errors-and-rate-limits",
    "prompt-caching",
    "agent-sdk-overview",
    "agent-sdk-tools",
]


class RawDoc(BaseModel):
    """A loaded source document, pre-chunking.

    `doc_id` is the stable identifier used as the UUIDv5 namespace for chunks.
    `source_url` is the click-through URL surfaced in the citation expander
    (file:// for filesystem ingest, https:// for URL-list ingest).
    """

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    source_url: str
    text: str
    doc_section: DocSection
    loaded_at: datetime


class Chunk(BaseModel):
    """A single chunk produced by `MarkdownHeaderChunker.split()`.

    `id` is a deterministic UUIDv5 of `(doc_id, chunk_index)` -- re-running
    ingest on unchanged docs is idempotent (RESEARCH.md §2 idempotency).
    `metadata` carries `{section_title, header_path, source_url}` for citations.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    doc_id: str
    chunk_index: int = Field(ge=0)
    doc_section: DocSection
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
