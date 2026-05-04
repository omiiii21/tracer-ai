"""tracer-ai Settings -- single source of truth for env-driven config.

Imported by alembic/env.py AND tracer_ai/api/main.py -- drift impossible by
construction (D-2.16).

Per Open Question Q2 / RESEARCH.md Topic 5 recommendation: FLAT shape (no
nested namespaces). The nested-with-flat-aliases pattern (D-2.20) carries
non-trivial pydantic-settings version fragility (Assumption A7). Saving
nested grouping is a future revision; cost is two characters per access
(``settings.db.url`` -> ``settings.database_url``).

Per D-2.21: ``settings = Settings()`` at module top level -- pydantic
ValidationError raises before any consumer reaches its main() / app startup,
so a missing required var (e.g., ANTHROPIC_API_KEY) prevents the api process
from binding the port.

Per D-2.39: ``model_config = SettingsConfigDict(...)`` -- the v1-style
inner-class pattern is forbidden by docs/api.md D-25 (Pydantic v2 strict-mode).

Per docs/api.md D-25 + D-2.21: the model_config below sets the strict-mode
forbid policy on extras -- unknown env vars are a Tampering bug class and
must be rejected at validation time, not silently dropped.
"""

from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level settings; fail-fast at import time per D-2.21."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="forbid",  # Tightened from Wave 3 shim per D-2.21 + docs/api.md D-25
    )

    # === Required (fail-fast on missing) ===
    database_url: PostgresDsn = Field(
        validation_alias="DATABASE_URL",
        description="postgresql+asyncpg://user:pass@host:port/dbname",
    )
    anthropic_api_key: SecretStr = Field(
        validation_alias="ANTHROPIC_API_KEY",
        description="Anthropic API key -- used by Phase 3+ rag/llm.py and eval/llm_judge.py",
    )
    voyage_api_key: SecretStr = Field(
        validation_alias="VOYAGE_API_KEY",
        description="Voyage AI API key -- used by Phase 3+ rag/embedder.py",
    )

    # === Optional with defaults ===
    llm_bot_model: str = Field(
        default="claude-sonnet-4-5-20250929",
        validation_alias="LLM_BOT_MODEL",
        description="Anthropic dated snapshot for the bot (Phase 3+)",
    )
    llm_judge_model: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias="LLM_JUDGE_MODEL",
        description="Anthropic dated snapshot for the judge (Phase 5+)",
    )
    embedding_model: str = Field(
        default="voyage-code-3",
        validation_alias="EMBEDDING_MODEL",
        description="Voyage embedding model -- must match corpus metadata (Phase 3 CORP-04)",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="structlog level -- Literal rejects out-of-enum injection at validation time",
    )
    enable_reranker: bool = Field(
        default=False,
        validation_alias="ENABLE_RERANKER",
        description="Reserved per ADR 007 -- v2 reranker flag",
    )


# D-2.21 fail-fast: ValidationError raises here if any required var is missing.
settings = Settings()
