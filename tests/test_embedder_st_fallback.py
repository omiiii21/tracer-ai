"""Tests for STEmbedder (Phase 3 Plan 03 / CORP-05 fallback adapter).

STEmbedder is the offline-dev fallback. The test file uses
``pytest.importorskip`` so it skips cleanly on default installs (where
sentence-transformers is the optional ``[offline]`` extra).

When the dep IS available, asserts:
  1. ``STEmbedder().embed_batch(["hi"])`` returns a list with one 768-dim vector.
  2. ``STEmbedder`` instance is structurally an ``Embedder`` Protocol member
     (mypy --strict-friendly + isinstance via runtime_checkable).
  3. ImportError path: when sentence-transformers is NOT installed, constructor
     raises ImportError with an actionable hint about the [offline] extra.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide Settings env vars (STEmbedder doesn't use them, but module-import does)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.rag.embedder", None)
    yield
    sys.modules.pop("tracer_ai.rag.embedder", None)


@pytest.mark.asyncio
async def test_st_embedder_produces_768_dim_vector(configured_env: None) -> None:
    """When sentence-transformers is installed, STEmbedder yields a 768-dim float vector.

    Skipped when sentence-transformers (or one of its transitive deps required
    by the nomic model -- e.g. ``einops``) isn't importable on the host.
    The plan's acceptance criterion explicitly allows the skip path:
    "exits 0 OR skips cleanly when sentence-transformers absent."
    """
    pytest.importorskip("sentence_transformers")
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")

    try:
        e = embedder_mod.STEmbedder()
    except ImportError as exc:
        # Transitive dep missing (e.g., einops for nomic-bert-2048). Treat
        # identically to sentence_transformers being absent -- not a regression.
        pytest.skip(f"STEmbedder transitive dep missing: {exc}")

    out = await e.embed_batch(["hi"])

    assert isinstance(out, list)
    assert len(out) == 1
    assert len(out[0]) == 768
    assert all(isinstance(x, float) for x in out[0])


def test_st_embedder_structurally_is_an_embedder(configured_env: None) -> None:
    """STEmbedder satisfies the Embedder Protocol (runtime_checkable).

    Uses a stub model (no real download) so this test runs in any env where
    sentence_transformers is importable -- transitive model deps don't matter
    for the Protocol-shape assertion.
    """
    pytest.importorskip("sentence_transformers")
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")

    from tracer_ai.rag.protocols import Embedder

    # Substitute SentenceTransformer with a no-op stub so __init__ doesn't try
    # to download a model. The Protocol structural-typing assertion only
    # exercises ``name``, ``version``, ``dim``, and ``embed_batch`` presence.
    class _StubModel:
        def encode(self, texts: list[str], **kwargs: Any) -> Any:
            return [[0.0] * 768 for _ in texts]

    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        mod = real_import(name, *args, **kwargs)
        if name == "sentence_transformers":
            mod.SentenceTransformer = lambda *a, **k: _StubModel()  # type: ignore[attr-defined]
        return mod

    with patch("builtins.__import__", side_effect=_fake_import):
        e = embedder_mod.STEmbedder()

    assert isinstance(e, Embedder)
    # Surface attrs match the Protocol shape.
    assert e.name == "nomic-embed-text-v1.5"
    assert e.dim == 768


def test_st_embedder_raises_importerror_when_dep_missing(
    configured_env: None,
) -> None:
    """If sentence_transformers is missing, constructor hints at the [offline] extra."""
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")

    # Patch the import-machinery so the lazy ``from sentence_transformers import ...``
    # inside STEmbedder.__init__ fails.
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ImportError("simulated missing dep")
        return real_import(name, *args, **kwargs)

    with (
        patch("builtins.__import__", side_effect=_fake_import),
        pytest.raises(ImportError, match=r"\[offline\]"),
    ):
        embedder_mod.STEmbedder()
