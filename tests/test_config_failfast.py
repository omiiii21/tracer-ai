"""Verify D-2.21 fail-fast behavior -- Settings() raises ValidationError on missing required vars.

Closes the Wave 0 gap from RESEARCH.md Validation Architecture for INFRA-03.
"""

import importlib
import sys
from typing import Any

import pytest
from pydantic import ValidationError


@pytest.mark.usefixtures("clean_env")
def test_settings_raises_when_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATABASE_URL is required (D-2.19); Settings() raises if unset."""
    # clean_env (from conftest.py) already cleared all tracer-ai env vars.
    # Set the OTHER required vars so we isolate the DATABASE_URL failure.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345678901234567890")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")
    # DATABASE_URL deliberately unset
    sys.modules.pop("tracer_ai.config", None)
    with pytest.raises(ValidationError) as exc_info:
        importlib.import_module("tracer_ai.config")
    err = str(exc_info.value)
    assert "DATABASE_URL" in err or "database_url" in err


@pytest.mark.usefixtures("clean_env")
def test_settings_raises_when_anthropic_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """ANTHROPIC_API_KEY is required (D-2.19); Settings() raises if unset."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")
    sys.modules.pop("tracer_ai.config", None)
    with pytest.raises(ValidationError) as exc_info:
        importlib.import_module("tracer_ai.config")
    err = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in err or "anthropic_api_key" in err


@pytest.mark.usefixtures("clean_env")
def test_settings_raises_when_voyage_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """VOYAGE_API_KEY is required (D-2.19); Settings() raises if unset."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345678901234567890")
    sys.modules.pop("tracer_ai.config", None)
    with pytest.raises(ValidationError) as exc_info:
        importlib.import_module("tracer_ai.config")
    err = str(exc_info.value)
    assert "VOYAGE_API_KEY" in err or "voyage_api_key" in err


@pytest.mark.usefixtures("clean_env")
def test_settings_loads_with_all_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """When all required vars are set, Settings() succeeds and exposes the FLAT shape."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://tracer:tracer@db:5432/tracer_ai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345678901234567890")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")
    sys.modules.pop("tracer_ai.config", None)
    config = importlib.import_module("tracer_ai.config")
    s = config.settings
    # FLAT shape per Open Question Q2 (NOT settings.db.url)
    assert str(s.database_url).startswith("postgresql+asyncpg://")
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test-12345678901234567890"
    assert s.voyage_api_key.get_secret_value() == "test-voyage-key"
    # Defaults
    assert s.llm_bot_model == "claude-sonnet-4-5-20250929"
    assert s.embedding_model == "voyage-code-3"
    assert s.log_level == "INFO"
    assert s.enable_reranker is False


@pytest.mark.usefixtures("clean_env")
def test_settings_model_rejects_extra_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per fix W-2: directly test the extra='forbid' contract on the Pydantic model.

    The previous test asserted only that the import succeeded with an unknown env
    var present, which is a no-op (pydantic-settings ignores env vars that don't
    map to declared fields, regardless of extra='forbid'). The real contract being
    enforced by ``extra="forbid"`` (D-2.21 + docs/api.md D-25) is that constructing
    Settings with an extra FIELD raises ValidationError. Test that directly.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345678901234567890")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")
    sys.modules.pop("tracer_ai.config", None)
    from tracer_ai.config import Settings

    kwargs: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://t:t@db:5432/t",
        "anthropic_api_key": "sk-ant-x",
        "voyage_api_key": "pa-x",
        "bogus_field": "should-be-rejected",
    }
    with pytest.raises(ValidationError):
        Settings(**kwargs)
