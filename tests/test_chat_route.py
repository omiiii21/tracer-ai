"""Tests for tracer_ai/api/chat.py (Phase 3 Plan 06 / RAG-05 + RAG-06).

CI-enforced witnesses:
  1. POST /chat returns text/event-stream and emits >= 1 ``event: token`` and
     exactly 1 ``event: final`` SSE frame.
  2. POST /chat with question="" -> 422 (Pydantic min_length=1).
  3. POST /chat with question of 4001 chars -> 422 (Pydantic max_length=4000).
  4. Response headers include ``Cache-Control: no-cache`` and
     ``X-Accel-Buffering: no`` (Pitfall 7.4 mitigation).
  5. Final SSE frame's data JSON contains the expected keys.
  6. Mocked-stack chat (50 canned chunks + instant token deltas) completes a
     full SSE response in < 1500ms (RAG-06 automated gate).
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide minimal env so settings imports cleanly inside tests."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.api.chat", None)
    sys.modules.pop("tracer_ai.rag.pipeline", None)


# --- Test infrastructure ---------------------------------------------------


def _make_cited_chunks(n: int) -> list[Any]:
    """Build N CitedChunk fixtures (used for the latency gate)."""
    from tracer_ai.rag.types import CitedChunk

    return [
        CitedChunk(
            idx=i + 1,
            doc_url=f"https://docs.anthropic.com/doc-{i}",
            section_title=f"Section {i}",
            text=f"chunk {i} content",
            score=0.9 - i * 0.005,
        )
        for i in range(n)
    ]


class _FakePipeline:
    """Yields configurable TextDelta events then exactly one ChatFinalEvent."""

    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        n_chunks: int = 3,
    ) -> None:
        self._deltas = deltas if deltas is not None else ["hi", " there"]
        self._n_chunks = n_chunks

    async def run_chat_stream(self, query: str) -> AsyncIterator[Any]:
        from tracer_ai.rag.types import ChatFinalEvent, TextDelta

        for d in self._deltas:
            yield TextDelta(text=d)
        yield ChatFinalEvent(
            trace_id=str(uuid4()),
            cited_chunks=_make_cited_chunks(self._n_chunks),
            latency_ms=42,
            input_tokens=120,
            output_tokens=18,
            estimated_cost_usd=0.000234,
        )


def _build_app(pipeline: Any) -> Any:
    """Build a minimal FastAPI app with the chat router + a fake pipeline."""
    from fastapi import FastAPI

    from tracer_ai import __version__
    from tracer_ai.api import chat

    app = FastAPI(title="tracer-ai-test", version=__version__)
    app.state.pipeline = pipeline
    app.include_router(chat.router)
    return app


# --- Tests ------------------------------------------------------------------


def test_streams_token_and_final() -> None:
    """Happy path: 2 token frames + 1 final frame."""
    from fastapi.testclient import TestClient

    app = _build_app(_FakePipeline(deltas=["Auth", "enticate"]))
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "How does auth work?"})
    assert resp.status_code == 200
    body = resp.text
    # >= 1 (in fact exactly 2) token events
    assert body.count("event: token") == 2
    assert body.count("event: final") == 1


def test_response_content_type_is_event_stream() -> None:
    """Content-type must start with text/event-stream."""
    from fastapi.testclient import TestClient

    app = _build_app(_FakePipeline())
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "hi"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


def test_validates_empty_question() -> None:
    """question='' fails ChatRequest min_length=1 -> 422."""
    from fastapi.testclient import TestClient

    app = _build_app(_FakePipeline())
    client = TestClient(app)
    resp = client.post("/chat", json={"question": ""})
    assert resp.status_code == 422


def test_validates_oversize_question() -> None:
    """4001-char question fails ChatRequest max_length=4000 -> 422."""
    from fastapi.testclient import TestClient

    app = _build_app(_FakePipeline())
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "a" * 4001})
    assert resp.status_code == 422


def test_response_headers() -> None:
    """Cache-Control + X-Accel-Buffering headers (Pitfall 7.4)."""
    from fastapi.testclient import TestClient

    app = _build_app(_FakePipeline())
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "hi"})
    assert resp.status_code == 200
    # FastAPI / Starlette normalize header names to lower-case on the response.
    assert resp.headers.get("cache-control") == "no-cache"
    assert resp.headers.get("x-accel-buffering") == "no"


def _parse_final_payload(body: str) -> dict[str, Any]:
    """Extract the data line of the ``event: final`` SSE frame."""
    # Frames are separated by blank lines.
    for frame in body.split("\n\n"):
        if "event: final" not in frame:
            continue
        for line in frame.splitlines():
            if line.startswith("data: "):
                payload: dict[str, Any] = json.loads(line[len("data: ") :])
                return payload
    raise AssertionError(f"No final frame in body: {body!r}")


def test_final_payload_shape() -> None:
    """Final frame contains all required keys with correct types."""
    from fastapi.testclient import TestClient

    app = _build_app(_FakePipeline())
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "hi"})
    assert resp.status_code == 200

    payload = _parse_final_payload(resp.text)
    assert "trace_id" in payload and isinstance(payload["trace_id"], str)
    assert "cited_chunks" in payload and isinstance(payload["cited_chunks"], list)
    assert "latency_ms" in payload and isinstance(payload["latency_ms"], int)
    assert "input_tokens" in payload and isinstance(payload["input_tokens"], int)
    assert "output_tokens" in payload and isinstance(payload["output_tokens"], int)
    assert "estimated_cost_usd" in payload and isinstance(payload["estimated_cost_usd"], float)


def test_chat_end_to_end_latency() -> None:
    """RAG-06 automated gate: 20-token mocked stack + 50 canned chunks < 1500ms."""
    from fastapi.testclient import TestClient

    pipeline = _FakePipeline(
        deltas=[f"tok{i}" for i in range(20)],
        n_chunks=50,
    )
    app = _build_app(pipeline)
    client = TestClient(app)

    t0 = time.perf_counter()
    resp = client.post("/chat", json={"question": "How does prompt caching work?"})
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200
    # Sanity: the response really did contain 20 token frames + 1 final frame.
    assert resp.text.count("event: token") == 20
    assert resp.text.count("event: final") == 1
    assert elapsed_ms < 1500, f"mocked-stack latency {elapsed_ms:.0f}ms exceeds 1500ms gate"
