"""Corpus loader -- filesystem markdown + URL-list (Phase 3 Plan 02, CORP-01).

Two ingest paths share the same `RawDoc` output shape:

- Filesystem: `discover(source_dir)` -> sorted list of .md paths;
  `load(path)` -> `RawDoc` (reads file, infers doc_section).
- URL-list: `discover_urls(urls)` -> identity (no FS walk needed);
  `load_url(url)` -> `RawDoc` via `httpx.AsyncClient` with 30s timeout.

Section inference: the immediate parent directory name OR the file stem must
match one of the 12 canonical doc_section values; otherwise we default to
`agent-sdk-overview` and emit a structured warning (T-03-02-04 mitigation --
section is always one of the 12 locked enum values).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog

from tracer_ai.corpus.types import DocSection, RawDoc

log = structlog.get_logger()

# Mirror of `DocSection` Literal values as a runtime `set` for O(1) membership
# tests in `_infer_section`. The Literal in types.py remains the single source
# of truth -- a regression here is caught when `Literal[...]` rejects an
# unknown value during `RawDoc(...)` construction.
_ALLOWED_SECTIONS: frozenset[str] = frozenset(
    {
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
    }
)

_DEFAULT_SECTION: DocSection = "agent-sdk-overview"

# URL-> slug regex: keep [a-z0-9-]; collapse other chars to '-'.
_SLUG_NORMALIZE = re.compile(r"[^a-z0-9-]+")


def _infer_section(path: Path) -> DocSection:
    """Map a markdown path to one of the 12 canonical doc_section values.

    Tries the immediate parent directory name first, then the file stem.
    Falls back to `agent-sdk-overview` on miss with a structured warning.
    """
    candidates = [path.parent.name, path.stem]
    for c in candidates:
        if c in _ALLOWED_SECTIONS:
            # The cast through Literal is safe: membership in `_ALLOWED_SECTIONS`
            # is the runtime mirror of the Literal type.
            return c  # type: ignore[return-value]
    log.warning("corpus_section_unknown", path=str(path), candidates=candidates)
    return _DEFAULT_SECTION


async def discover(source_dir: Path) -> list[Path]:
    """Return all `**/*.md` paths under `source_dir`, sorted (deterministic order)."""
    paths = sorted(source_dir.rglob("*.md"))
    log.info("corpus_discover", source_dir=str(source_dir), count=len(paths))
    return paths


async def load(path: Path) -> RawDoc:
    """Read a markdown file from disk into a `RawDoc`.

    `doc_id` is `claude-docs/<file-stem>` so chunk UUIDv5 namespacing stays
    stable across renames of the parent directory.
    """
    text = path.read_text(encoding="utf-8")
    return RawDoc(
        doc_id=f"claude-docs/{path.stem}",
        source_url=f"file://{path.resolve().as_posix()}",
        text=text,
        doc_section=_infer_section(path),
        loaded_at=datetime.now(UTC),
    )


def discover_urls(urls: list[str]) -> list[str]:
    """Identity for the URL-list path -- no filesystem walk needed.

    Kept symmetric with `discover()` so `run_ingest()` can branch on input
    shape without bespoke control flow per source variant.
    """
    log.info("corpus_discover_urls", count=len(urls))
    return urls


async def load_url(url: str, *, client: httpx.AsyncClient | None = None) -> RawDoc:
    """Fetch a URL into a `RawDoc`.

    `client` is injectable for tests; if omitted, an `AsyncClient` with a 30s
    timeout (T-03-02-03 DoS mitigation) and `follow_redirects=True` is created
    and closed in `finally`.
    """
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        # doc_id from URL path slug; e.g. https://docs.anthropic.com/en/api/messages -> messages
        last_segment = url.rsplit("/", 1)[-1].lower() or "doc"
        slug = _SLUG_NORMALIZE.sub("-", last_segment).strip("-") or "doc"
        return RawDoc(
            doc_id=f"url/{slug}",
            source_url=url,
            text=resp.text,
            # URL ingest defaults to overview; admin can re-tag in v2 (per plan).
            doc_section=_DEFAULT_SECTION,
            loaded_at=datetime.now(UTC),
        )
    finally:
        if own_client:
            await client.aclose()
