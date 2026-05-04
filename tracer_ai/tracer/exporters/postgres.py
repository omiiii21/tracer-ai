"""Postgres+JSONB trace exporter (Phase 2 stub; Phase 4 TRCR-06 fills body).

Per ADR 004: bounded asyncio.Queue(maxsize=1000), background consumer
batches inserts, lifespan force-flushes on shutdown.
"""
