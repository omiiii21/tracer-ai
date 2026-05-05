"""tracer-ai CLI -- ingest subcommand (Phase 3 Plan 05, CORP-01).

Per D-2.37 / tests/test_anti_patterns.py allowlist: ``print()`` is allowed
in this file ONLY (cli/__main__.py). All ingest output goes to stdout for
shell consumption.

Usage:
    python -m tracer_ai.cli ingest --source ./fixtures/claude-docs-sample
    python -m tracer_ai.cli ingest --urls ./urls.txt

Exit codes:
    0  success (errors == 0)
    1  ingest produced one or more errors
    2  argparse / argument validation failure
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg
import structlog

from tracer_ai.config import settings
from tracer_ai.corpus.chunker import MarkdownHeaderChunker
from tracer_ai.corpus.ingest import IngestResult, run_ingest
from tracer_ai.rag.embedder import VoyageEmbedder

log = structlog.get_logger()


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argparse subcommand tree.

    The ``ingest`` subcommand uses a mutually-exclusive --source / --urls
    argument group; exactly one is required.
    """
    parser = argparse.ArgumentParser(
        prog="tracer-ai",
        description="tracer-ai CLI: ingest, query, and admin operations",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Ingest a corpus into the chunks table")
    src_group = ingest.add_mutually_exclusive_group(required=True)
    src_group.add_argument(
        "--source",
        type=Path,
        help="Filesystem directory of .md files to ingest",
    )
    src_group.add_argument(
        "--urls",
        type=Path,
        help="Text file with one URL per line to ingest",
    )
    ingest.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Embedding batch size (default: 64)",
    )
    return parser


async def _run_ingest_async(
    *,
    source: Path | None,
    urls: list[str] | None,
    batch_size: int,
) -> IngestResult:
    """Build deps + open pool + run ingest + close pool."""
    embedder = VoyageEmbedder()
    chunker = MarkdownHeaderChunker(
        chunk_size=settings.chunking_default_size,
        overlap=settings.chunking_default_overlap,
    )
    asyncpg_dsn = str(settings.database_url).replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn=asyncpg_dsn, min_size=1, max_size=4)
    try:
        return await run_ingest(
            source=source,
            urls=urls,
            embedder=embedder,
            chunker=chunker,
            pool=pool,
            batch_size=batch_size,
        )
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "ingest":
        # argparse's required=True on the subcommand dest already covers this,
        # but the explicit guard keeps the type-checker happy and documents intent.
        parser.error("only 'ingest' is supported in Phase 3")
        return 2  # unreachable -- parser.error sys.exits 2.

    urls_list: list[str] | None = None
    if args.urls is not None:
        urls_path: Path = args.urls
        if not urls_path.exists():
            print(f"error: --urls file not found: {urls_path}", file=sys.stderr)
            return 2
        urls_list = [
            ln.strip() for ln in urls_path.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]

    result = asyncio.run(
        _run_ingest_async(
            source=args.source,
            urls=urls_list,
            batch_size=args.batch_size,
        )
    )
    # ``print`` allowlist: cli/__main__.py is the only tracer_ai/ file that
    # may emit raw print(); per-D-2.37.
    print(result.model_dump_json(indent=2))
    return 1 if result.errors else 0


if __name__ == "__main__":  # pragma: no cover -- exercised via subprocess in tests
    raise SystemExit(main())
