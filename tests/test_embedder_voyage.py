"""Tests for VoyageEmbedder (Phase 3 Plan 03 / CORP-05).

Asserts:
  1. Constructor with ``dim != 1024`` raises ValueError before any SDK call.
  2. Successful embed returns the SDK's ``embeddings`` list verbatim.
  3. 429-then-success: retries on rate-limit and ultimately returns embeddings.
  4. 5x429 (initial + 4 retries all fail): adapter raises after the final retry.
  5. ``Retry-After`` header is honored when surfaced on the exception.
  6. SDK isolation: ``import voyageai`` lives only in tracer_ai/rag/embedder.py.

Mocks the ``voyageai.AsyncClient.embed`` method so no live API calls are made.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# --- Test infrastructure ---------------------------------------------------


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide the Settings env vars that VoyageEmbedder needs at construction."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.rag.embedder", None)
    yield
    sys.modules.pop("tracer_ai.rag.embedder", None)


def _make_embeddings_response(vectors: list[list[float]]) -> Any:
    """Mimic voyageai.object.embeddings.EmbeddingsObject -- only the ``embeddings`` attr is used."""

    class _Resp:
        def __init__(self, embeddings: list[list[float]]) -> None:
            self.embeddings = embeddings

    return _Resp(vectors)


def _make_rate_limit_error(headers: dict[str, str] | None = None) -> Exception:
    """Construct a 429-shaped exception that ``_is_rate_limit_error`` recognizes.

    Mirrors voyageai.error.RateLimitError class-name + ``http_status`` shape
    without importing the SDK error module here (the embedder unit tests
    intentionally exercise the runtime detection path, not the SDK class).
    """

    class RateLimitError(Exception):
        def __init__(
            self, msg: str, http_status: int = 429, headers: dict[str, str] | None = None
        ) -> None:
            super().__init__(msg)
            self.http_status = http_status
            self.headers = headers or {}

    return RateLimitError("429 too many requests", headers=headers)


# --- Test 1: dim validation ------------------------------------------------


def test_voyage_embedder_rejects_non_1024_dim(configured_env: None) -> None:
    """Constructor with ``dim=999`` raises ValueError before any SDK call."""
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")
    with pytest.raises(ValueError, match="dim=1024"):
        embedder_mod.VoyageEmbedder(dim=999)


# --- Test 2: successful embed ----------------------------------------------


@pytest.mark.asyncio
async def test_voyage_embedder_returns_embeddings_on_success(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mocked SDK returns a 1024-dim vector; adapter passes it through."""
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")

    # Stub voyageai.AsyncClient so __init__ doesn't try to hit the real API.
    fake_client_embed = AsyncMock(return_value=_make_embeddings_response([[0.1] * 1024]))

    class _FakeAsyncClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.embed = fake_client_embed

    import voyageai

    monkeypatch.setattr(voyageai, "AsyncClient", _FakeAsyncClient)

    e = embedder_mod.VoyageEmbedder()
    result = await e.embed_batch(["hi"])

    assert result == [[0.1] * 1024]
    fake_client_embed.assert_awaited_once_with(["hi"], model="voyage-code-3", input_type="document")


# --- Test 3: 429-then-success ---------------------------------------------


@pytest.mark.asyncio
async def test_voyage_embedder_retries_on_429_then_succeeds(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """429 twice, then success on the 3rd attempt; final return is the success payload."""
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")

    side_effects: list[Any] = [
        _make_rate_limit_error(),
        _make_rate_limit_error(),
        _make_embeddings_response([[0.2] * 1024]),
    ]
    fake_embed = AsyncMock(side_effect=side_effects)

    class _FakeAsyncClient:
        def __init__(self, *, api_key: str) -> None:
            self.embed = fake_embed

    import voyageai

    monkeypatch.setattr(voyageai, "AsyncClient", _FakeAsyncClient)

    # Speed: monkeypatch asyncio.sleep so the test isn't paced by real backoff.
    monkeypatch.setattr(embedder_mod.asyncio, "sleep", AsyncMock(return_value=None))

    e = embedder_mod.VoyageEmbedder()
    result = await e.embed_batch(["hi"])

    assert result == [[0.2] * 1024]
    assert fake_embed.await_count == 3


# --- Test 4: 5x429 raises after final retry --------------------------------


@pytest.mark.asyncio
async def test_voyage_embedder_raises_after_max_retries(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5 consecutive 429s -> adapter exhausts 4 retries and re-raises the last."""
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")

    side_effects: list[Any] = [_make_rate_limit_error() for _ in range(5)]
    fake_embed = AsyncMock(side_effect=side_effects)

    class _FakeAsyncClient:
        def __init__(self, *, api_key: str) -> None:
            self.embed = fake_embed

    import voyageai

    monkeypatch.setattr(voyageai, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(embedder_mod.asyncio, "sleep", AsyncMock(return_value=None))

    e = embedder_mod.VoyageEmbedder()
    with pytest.raises(Exception) as exc_info:
        await e.embed_batch(["hi"])

    # Error class name ends in RateLimitError per the test fixture; this
    # confirms the original exception (not RuntimeError) propagates.
    assert type(exc_info.value).__name__.endswith("RateLimitError")
    # Initial attempt + 4 retries = 5 calls.
    assert fake_embed.await_count == 5


# --- Test 5: Retry-After header is honored --------------------------------


@pytest.mark.asyncio
async def test_voyage_embedder_honors_retry_after(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Retry-After is present, adapter sleeps that many seconds."""
    embedder_mod = importlib.import_module("tracer_ai.rag.embedder")

    side_effects: list[Any] = [
        _make_rate_limit_error(headers={"Retry-After": "0.5"}),
        _make_embeddings_response([[0.3] * 1024]),
    ]
    fake_embed = AsyncMock(side_effect=side_effects)

    class _FakeAsyncClient:
        def __init__(self, *, api_key: str) -> None:
            self.embed = fake_embed

    import voyageai

    monkeypatch.setattr(voyageai, "AsyncClient", _FakeAsyncClient)

    sleep_calls: list[float] = []

    async def _capture_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(embedder_mod.asyncio, "sleep", _capture_sleep)

    e = embedder_mod.VoyageEmbedder()
    result = await e.embed_batch(["hi"])

    assert result == [[0.3] * 1024]
    assert sleep_calls == [0.5]  # honored Retry-After, not the 0.2 default


# --- Test 6: SDK isolation -------------------------------------------------


def _find_real_import_lines(path: str, module: str) -> list[str]:
    """Scan a Python source file for non-docstring, non-comment imports of ``module``.

    Mirrors the helper in tests/test_rag_protocols.py to avoid docstring
    false positives.
    """
    text = Path(path).read_text(encoding="utf-8").splitlines()
    in_doc = False
    real: list[str] = []
    for raw in text:
        stripped = raw.strip()
        triple_count = stripped.count('"""')
        if triple_count == 1:
            in_doc = not in_doc
            continue
        if in_doc or triple_count >= 2:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith(f"import {module}") or stripped.startswith(f"from {module}"):
            real.append(raw)
    return real


def test_embedder_module_is_only_voyageai_importer() -> None:
    """D-2.38: ``import voyageai`` (or ``from voyageai``) lives only in rag/embedder.py."""
    repo = Path(__file__).resolve().parent.parent
    embedder_py = repo / "tracer_ai" / "rag" / "embedder.py"
    assert _find_real_import_lines(
        str(embedder_py), "voyageai"
    ), "rag/embedder.py must contain at least one real ``import voyageai`` line"

    # Walk every other .py file under tracer_ai/ and assert none import voyageai.
    violations: list[str] = []
    for py in (repo / "tracer_ai").rglob("*.py"):
        if py.resolve() == embedder_py.resolve():
            continue
        if _find_real_import_lines(str(py), "voyageai"):
            violations.append(str(py.relative_to(repo)))
    assert (
        not violations
    ), f"D-2.38 violation: voyageai imported outside rag/embedder.py: {violations}"
