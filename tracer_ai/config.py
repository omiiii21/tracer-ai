"""tracer-ai Settings -- single source of truth for env-driven config.

Imported by alembic/env.py AND tracer_ai/api/main.py -- drift impossible by
construction (D-2.16).

Wave 3 (this file) ships the MINIMAL shim with only `database_url` so the
Alembic env.py can resolve the DSN. Wave 4 EXPANDS this file to add all
remaining required vars (ANTHROPIC_API_KEY, VOYAGE_API_KEY, LLM_BOT_MODEL,
LLM_JUDGE_MODEL, EMBEDDING_MODEL, LOG_LEVEL, ENABLE_RERANKER) and tightens
``extra="ignore"`` to ``extra="forbid"`` per D-2.21 fail-fast contract.

Per Open Question Q2 / RESEARCH.md Topic 5 recommendation: FLAT shape (no
nested ``db.url``). The nested-with-flat-aliases pattern (D-2.20) carries
non-trivial pydantic-settings version fragility (Assumption A7). Saving
nested grouping is a future revision; cost is two characters per access
(``settings.db.url`` -> ``settings.database_url``).
"""
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level settings; fail-fast at import time per D-2.21.

    Wave 3 minimal shim. Wave 4 expands.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",  # Wave 4 changes to "forbid" once all vars are added
    )

    # === Required ===
    database_url: PostgresDsn = Field(
        validation_alias="DATABASE_URL",
        description="postgresql+asyncpg://user:pass@host:port/dbname",
    )


# D-2.21: settings instantiated at module top level -- ValidationError raises before
# any consumer reaches its main() / app startup.
settings = Settings()
