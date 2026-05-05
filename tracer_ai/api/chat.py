"""POST /chat -- SSE streaming handler (Phase 3 Plan 06 / RAG-05).

Streams tokens + a single final frame from a Pipeline.run_chat_stream
generator into a ``text/event-stream`` HTTP response. The frontend's
``lib/sse.ts`` parses the response into discriminated events.

Wire format (SSE; frames separated by ``\\n\\n``):

    event: token
    data: {"text": "Auth"}

    event: final
    data: {"trace_id": "...", "cited_chunks": [...], "latency_ms": 2810,
           "input_tokens": 1240, "output_tokens": 96,
           "estimated_cost_usd": 0.0043}

Pitfall 7.4 / T-03-06-09 mitigation: ``X-Accel-Buffering: no`` defeats nginx /
uvicorn buffering so tokens stream incrementally to the client. CHAT-02 e2e
test in Plan 08 asserts >= 2 distinct DOM mutations during a streamed
response (proves no buffering).

T-03-06-03 mitigation: ``ChatRequest.question`` is bounded
``min_length=1, max_length=4000`` (FastAPI validation -> 422 on out-of-bounds);
``Pipeline.run_chat_stream`` caps the LLM ``max_tokens`` at 1024 (T-03-05-05
inherited from the LLM adapter).

T-03-06-10 mitigation: any exception in the SSE generator is caught and
re-emitted as a generic ``event: error`` frame with ``str(e)`` only;
the full traceback stays in structlog. v1 is single-user local-dev (ADR 009),
so error-message leakage is acceptable; production deployment would gate on
env to scrub the message.

NOTE: v1 has no rate limiting (single-user local-dev only per ADR 009).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from tracer_ai.api.schemas import ChatRequest
from tracer_ai.rag.types import ChatFinalEvent, TextDelta

log = structlog.get_logger()
router = APIRouter()


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    """Stream a chat response as SSE.

    Iterates ``request.app.state.pipeline.run_chat_stream(body.question)``,
    serializing each ``TextDelta`` as an ``event: token`` SSE frame and the
    single trailing ``ChatFinalEvent`` as an ``event: final`` SSE frame.
    On any exception, emits a generic ``event: error`` frame and logs the
    full exception via structlog (T-03-06-10).
    """
    pipeline = request.app.state.pipeline

    async def gen() -> AsyncIterator[bytes]:
        try:
            async for ev in pipeline.run_chat_stream(body.question):
                if isinstance(ev, TextDelta):
                    frame = f"event: token\ndata: {json.dumps({'text': ev.text})}\n\n"
                    yield frame.encode("utf-8")
                elif isinstance(ev, ChatFinalEvent):
                    payload = ev.model_dump(mode="json")
                    frame = f"event: final\ndata: {json.dumps(payload)}\n\n"
                    yield frame.encode("utf-8")
        except Exception as exc:
            log.exception("chat_stream_error", error=str(exc))
            err_frame = f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
            yield err_frame.encode("utf-8")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
