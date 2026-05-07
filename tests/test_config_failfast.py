"""Verify D-2.21 fail-fast behavior -- Settings() raises ValidationError on missing required vars.

Closes the Wave 0 gap from RESEARCH.md Validation Architecture for INFRA-03.

Phase 5 Plan 01 EXTENDS this file with bound-checks for the 4 new fields
(BAD_ANSWER_FAITHFULNESS_THRESHOLD, JUDGE_CONCURRENCY, JUDGE_TIMEOUT_SECONDS,
CALIBRATION_DATE) per D-5.13 / D-5.09 / D-5.05 / D-5.14.
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


# ---------------------------------------------------------------------------
# Phase 5 Plan 01: 4 new Settings fields (D-5.13 / D-5.09 / D-5.05 / D-5.14).
# ---------------------------------------------------------------------------


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the 3 required env vars so we isolate the new-field-bound failures.

    Uses a deliberately short ``sk-ant-x`` value (<20 chars after the prefix) so
    gitleaks' anthropic-api-key regex (sk-ant-[a-zA-Z0-9_-]{20,}) does NOT match.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://tracer:tracer@db:5432/tracer_ai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")


@pytest.mark.usefixtures("clean_env")
def test_bad_answer_faithfulness_threshold_rejects_out_of_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-5.13: BAD_ANSWER_FAITHFULNESS_THRESHOLD must be in [0.0, 1.0]."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BAD_ANSWER_FAITHFULNESS_THRESHOLD", "1.5")
    sys.modules.pop("tracer_ai.config", None)
    with pytest.raises(ValidationError):
        importlib.import_module("tracer_ai.config")


@pytest.mark.usefixtures("clean_env")
def test_judge_concurrency_rejects_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-5.09: JUDGE_CONCURRENCY must be >= 1 (asyncio.Semaphore bound)."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("JUDGE_CONCURRENCY", "0")
    sys.modules.pop("tracer_ai.config", None)
    with pytest.raises(ValidationError):
        importlib.import_module("tracer_ai.config")


@pytest.mark.usefixtures("clean_env")
def test_judge_timeout_seconds_rejects_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-5.05: JUDGE_TIMEOUT_SECONDS must be > 0."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("JUDGE_TIMEOUT_SECONDS", "-1")
    sys.modules.pop("tracer_ai.config", None)
    with pytest.raises(ValidationError):
        importlib.import_module("tracer_ai.config")


@pytest.mark.usefixtures("clean_env")
def test_calibration_date_accepts_tz_aware_and_naive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-5.14 + Open Question 5 RESOLVED: accept BOTH tz-aware AND naive datetimes."""
    # Subcase 1: tz-aware (UTC suffix).
    _set_required_env(monkeypatch)
    monkeypatch.setenv("CALIBRATION_DATE", "2026-05-15T12:00:00Z")
    sys.modules.pop("tracer_ai.config", None)
    config = importlib.import_module("tracer_ai.config")
    assert config.settings.calibration_date is not None

    # Subcase 2: NAIVE (no tz suffix). Pydantic v2 datetime accepts naive without raising.
    _set_required_env(monkeypatch)
    monkeypatch.setenv("CALIBRATION_DATE", "2026-05-15T12:00:00")
    sys.modules.pop("tracer_ai.config", None)
    config = importlib.import_module("tracer_ai.config")
    assert config.settings.calibration_date is not None

    # Subcase 3: unset -> None.
    _set_required_env(monkeypatch)
    monkeypatch.delenv("CALIBRATION_DATE", raising=False)
    sys.modules.pop("tracer_ai.config", None)
    config = importlib.import_module("tracer_ai.config")
    assert config.settings.calibration_date is None


@pytest.mark.usefixtures("clean_env")
def test_settings_rejects_extra_field_phase5(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-2.21 / docs/api.md D-25: extra='forbid' rejects unknown declared fields.

    Mirrors test_settings_model_rejects_extra_field above; restated under the
    Phase 5 banner so the contract is verified after the new-field additions.
    """
    _set_required_env(monkeypatch)
    sys.modules.pop("tracer_ai.config", None)
    from tracer_ai.config import Settings

    kwargs: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://t:t@db:5432/t",
        "anthropic_api_key": "sk-ant-x",
        "voyage_api_key": "pa-x",
        "extra_field_not_declared": "foo",
    }
    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.usefixtures("clean_env")
def test_phase5_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults: threshold=0.6, concurrency=4, timeout=10.0, calibration_date=None."""
    _set_required_env(monkeypatch)
    sys.modules.pop("tracer_ai.config", None)
    config = importlib.import_module("tracer_ai.config")
    s = config.settings
    assert s.bad_answer_faithfulness_threshold == 0.6
    assert s.judge_concurrency == 4
    assert s.judge_timeout_seconds == 10.0
    assert s.calibration_date is None


@pytest.mark.usefixtures("clean_env")
def test_phase5_settings_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """W9 fix: confirm BOTH lower-case attribute access AND type coercion.

    `judge_concurrency` is ``int``; `judge_timeout_seconds` and
    `bad_answer_faithfulness_threshold` are ``float``.
    """
    _set_required_env(monkeypatch)
    sys.modules.pop("tracer_ai.config", None)
    config = importlib.import_module("tracer_ai.config")
    s = config.settings
    assert isinstance(s.judge_concurrency, int)
    assert s.judge_concurrency == 4
    assert isinstance(s.judge_timeout_seconds, float)
    assert isinstance(s.bad_answer_faithfulness_threshold, float)
