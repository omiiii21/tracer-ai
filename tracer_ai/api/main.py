"""tracer-ai FastAPI app -- entry point.

Per RESEARCH.md Topic 3 + FastAPI 0.100+ docs: uses ``lifespan=`` async
context manager (the on-event hook pattern is deprecated and removed in
modern FastAPI).

Per Phase 3 Plan 03 PATTERNS.md s"Backend Subsystem 6 -- lifespan.py":
the lifespan body lives in ``tracer_ai.api.lifespan`` so the CORP-04
embedding-model identity assertion can be unit-tested in isolation from
the FastAPI router setup. Phase 3+ adapter wiring (pipeline, embedder,
retriever, llm, writer) goes there too.

Per D-2.33: GET /healthz is the only Phase 2 endpoint. Phase 3+ adds
chat, feedback, traces, admin routes.

Per D-2.37: structured logging only -- bind a logger via the structlog
factory (see ``log = ...`` below); ad-hoc stdout writes are forbidden.
"""

import structlog
from fastapi import FastAPI

from tracer_ai import __version__
from tracer_ai.api.lifespan import lifespan

log = structlog.get_logger()

app = FastAPI(
    title="tracer-ai",
    version=__version__,
    lifespan=lifespan,
)

# Routes registered after app creation per the canonical FastAPI pattern.
from tracer_ai.api import chat, feedback, health  # noqa: E402

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(feedback.router)
