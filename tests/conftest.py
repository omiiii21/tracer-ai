"""pytest configuration (Phase 2 Wave 0 scaffold)."""

import sys
from collections.abc import Iterator

import pytest


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear tracer-ai env vars AND evict tracer_ai.config from sys.modules.

    Used by tests/test_config_failfast.py (Wave 4) to verify Settings raises
    ValidationError when required vars are missing.

    Per fix W-6: this fixture also evicts `tracer_ai.config` from sys.modules.
    Module-top-level `settings = Settings()` only re-runs validation when the
    module is fresh-imported. If pytest collection imports `tracer_ai.config`
    once with valid env vars, the cached module survives subsequent fixture
    runs and the fail-fast guarantee silently regresses. Tests should ALSO call
    `sys.modules.pop("tracer_ai.config", None)` immediately before
    `importlib.import_module("tracer_ai.config")` for safety; this fixture
    establishes the baseline.
    """
    for key in (
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "VOYAGE_API_KEY",
        "LLM_BOT_MODEL",
        "LLM_JUDGE_MODEL",
        "EMBEDDING_MODEL",
        "LOG_LEVEL",
        "ENABLE_RERANKER",
    ):
        monkeypatch.delenv(key, raising=False)
    # Evict the cached module so the next import re-runs `settings = Settings()`
    # at module top level (the fail-fast point per D-2.21).
    sys.modules.pop("tracer_ai.config", None)
    yield
    # monkeypatch auto-restores env vars; we leave sys.modules state alone
    # post-yield because subsequent tests should explicitly pop again if they
    # need the fresh-import behavior (defensive depth).
