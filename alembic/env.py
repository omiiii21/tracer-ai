"""Alembic env.py -- async pattern for SQLAlchemy 2.0 + asyncpg + pgvector.

Per D-2.16: imports tracer_ai.config.settings as the single source of DSN,
ensuring no drift between migrations and the api process.

Per RESEARCH.md Topic 2: uses async_engine_from_config() + connection.run_sync()
because the synchronous engine factory does NOT work with asyncpg DSNs.

Per RESEARCH.md Topic 2 + D-2.17: include_object hook skips spans_y* partition
children so Phase 3+ autogenerate does not try to recreate them.
"""

import asyncio
from logging.config import fileConfig
from typing import Any

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from tracer_ai.config import settings  # D-2.16 -- single source of DSN

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the placeholder sqlalchemy.url with the real DSN from Settings
config.set_main_option("sqlalchemy.url", str(settings.database_url))

# Phase 2 D-2.17: hand-curated initial revision; no autogenerate from models in Phase 2.
# Phase 3+ revisions MAY set target_metadata to a real MetaData object for autogenerate.
target_metadata = None


def _include_object(obj: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Skip spans_y* partition children on autogenerate (RESEARCH.md Topic 2)."""
    return not (type_ == "table" and name.startswith("spans_y"))


def do_run_migrations(connection: Any) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    raise RuntimeError("offline mode not supported (asyncpg DSN required)")
else:
    run_migrations_online()
