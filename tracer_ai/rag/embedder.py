"""Embedder adapters -- Voyage (primary) + sentence-transformers (offline fallback).

Per D-2.38 / SDK isolation: this is the ONLY file in tracer_ai/ allowed to
``import voyageai`` or ``import sentence_transformers``. The anti-pattern test
``tests/test_anti_patterns.py`` enforces this gate via git-grep.

``STEmbedder`` is documented but NOT wired to the live ``VECTOR(1024)`` chunks
table -- its 768-dim output is dimension-incompatible. Use it for unit testing
the Embedder Protocol shape or for an offline-dev schema variant (Phase 7
polish item per RESEARCH.md s2 final paragraph).

Pattern references:
  - PATTERNS.md s"Backend Subsystem 2" (lines 144-167) -- Embedder Protocol +
    SDK-isolation discipline + secret access at the SDK boundary.
  - RESEARCH.md s7.6 -- Voyage rate-limit handling: exponential backoff
    (200/400/800/1600ms, max 4 retries); honor Retry-After header.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from tracer_ai.config import settings
from tracer_ai.rag.protocols import Embedder

log = structlog.get_logger()


class VoyageEmbedder:
    """Voyage AI ``voyage-code-3`` embedder (1024-dim, code-doc specialist).

    Wraps ``voyageai.AsyncClient.embed``. Retries on 429/RateLimitError with
    exponential backoff (200/400/800/1600ms, max 4 retries) and honors the
    ``Retry-After`` header when present on the exception.
    """

    name: str = "voyage-code-3"
    version: str = "voyage-code-3@2025-09"
    dim: int = 1024

    def __init__(self, *, dim: int = 1024) -> None:
        if dim != 1024:
            raise ValueError(f"VoyageEmbedder requires dim=1024, got {dim}")
        # Lazy import so test environments without voyageai installed don't error
        # at module import time. SDK boundary: the SecretStr is unwrapped here only.
        import voyageai

        # voyageai exports AsyncClient at the package root but lacks an explicit
        # __all__; ``getattr`` access keeps mypy --strict clean (the SDK is in
        # the ignore_missing_imports override list, but attribute access on the
        # exported namespace still requires an explicit Any boundary).
        voyage_async_client: Any = getattr(voyageai, "AsyncClient")  # noqa: B009
        self._client: Any = voyage_async_client(api_key=settings.voyage_api_key.get_secret_value())

    async def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]:
        """Embed ``texts`` -- list of 1024-dim float vectors.

        Retry-on-429 schedule: 200ms, 400ms, 800ms, 1600ms (max 4 retries).
        Honors ``Retry-After`` if surfaced on the exception ``headers`` dict
        (per voyageai.error.VoyageError shape).
        """
        delays = [0.2, 0.4, 0.8, 1.6]
        last_exc: Exception | None = None
        # 5 attempts total (initial + 4 retries). The trailing None marks the
        # final attempt where any failure must propagate.
        attempts: list[float | None] = [*delays, None]
        for attempt_idx, delay in enumerate(attempts):
            try:
                result = await self._client.embed(
                    texts,
                    model=self.name,
                    input_type=input_type,
                )
                # voyageai.object.embeddings.EmbeddingsObject exposes a
                # ``embeddings: list[list[float]]`` attribute.
                embeddings: list[list[float]] = result.embeddings
                return embeddings
            except Exception as exc:
                if not _is_rate_limit_error(exc) or delay is None:
                    raise
                wait_s = _retry_after_seconds(exc) or delay
                log.warning(
                    "voyage_429_retry",
                    attempt=attempt_idx + 1,
                    wait_s=wait_s,
                )
                last_exc = exc
                await asyncio.sleep(wait_s)
        # Defensive: the loop above either returns or raises on the last attempt.
        # mypy needs a terminal raise to type-check the function as never-returning-None.
        raise RuntimeError(
            "VoyageEmbedder.embed_batch exited retry loop unexpectedly"
        ) from last_exc


def _is_rate_limit_error(exc: BaseException) -> bool:
    """True if ``exc`` is a Voyage rate-limit (429) signal.

    Detects via:
      1. Class name endswith ``RateLimitError`` (covers voyageai.error.RateLimitError
         without an import-time SDK dep on the error module).
      2. ``http_status == 429`` attribute (voyageai.error.VoyageError shape).
      3. Substring ``"429"`` or ``"rate"`` in the exception message (defensive
         fallback for SDK versions that bubble up plain HTTP exceptions).
    """
    cls_name = type(exc).__name__
    if cls_name.endswith("RateLimitError"):
        return True
    if getattr(exc, "http_status", None) == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Read ``Retry-After`` from the exception headers if available.

    Returns ``None`` when the header is missing or unparseable. Honors the
    voyageai.error.VoyageError ``headers`` dict shape; gracefully ignores
    other exception shapes.
    """
    headers = getattr(exc, "headers", None) or {}
    if not isinstance(headers, dict):
        return None
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after is None:
        return None
    try:
        return float(retry_after)
    except (TypeError, ValueError):
        return None


class STEmbedder:
    """Offline-dev fallback. NOT wired to live chunks table (dim mismatch).

    768-dim output (``nomic-ai/nomic-embed-text-v1.5``) does not fit the
    live ``chunks.embedding VECTOR(1024)`` column. Use for unit testing the
    Embedder Protocol or for an offline-dev schema variant (Phase 7 polish
    item; not v1).
    """

    name: str = "nomic-embed-text-v1.5"
    version: str = "nomic-embed-text-v1.5@1.5"
    dim: int = 768

    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers not installed. Install via: pip install -e '.[offline]'"
            ) from exc
        self._model: Any = SentenceTransformer(model_name, trust_remote_code=True)

    async def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]:
        """Encode via sentence-transformers in a thread (the underlying call is sync)."""
        loop = asyncio.get_running_loop()
        vecs: Any = await loop.run_in_executor(
            None,
            lambda: self._model.encode(texts, convert_to_numpy=True),
        )
        return [list(map(float, v)) for v in vecs]


# Static structural typing shim -- mypy --strict catches Protocol-shape drift.
# The runtime call sites instantiate via the constructors; this shim only
# exercises the type-checker.
def _accepts_embedder(_e: Embedder) -> None: ...
