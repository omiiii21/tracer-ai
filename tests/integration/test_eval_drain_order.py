"""Phase 5 D-5.10 lifespan drain ordering -- dispatcher BEFORE consumer.

LD1 + LD2 witnesses (eval drain precedes consumer drain in shutdown):

  - LD1: Source-level invariant: in tracer_ai/api/lifespan.py finally, the
         eval_dispatcher.drain call appears at a lower line number than the
         consumer.drain call. Mirrors the live-execution invariant -- if the
         consumer drained first, eval emit-into-queue would be dropped on the
         floor when the consumer task is later cancelled.
  - LD2: Slow MockJudge + 0.1s drain timeout produces the
         eval.dispatcher_drain_incomplete warn-log in less than 5s.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import sys
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-x")
os.environ.setdefault("VOYAGE_API_KEY", "pa-test")


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)


def test_ld1_lifespan_drain_order_eval_before_consumer() -> None:
    """LD1: lifespan.py source has eval_dispatcher.drain BEFORE consumer.drain."""
    from tracer_ai.api import lifespan

    src = inspect.getsource(lifespan)
    # Match positions of the two calls in the source.
    eval_match = re.search(r"eval_disp\.drain\(", src) or re.search(
        r"eval_dispatcher\.drain\(", src
    )
    consumer_match = re.search(r"consumer\.drain\(", src)
    assert eval_match is not None, "eval_dispatcher.drain not found in lifespan.py"
    assert consumer_match is not None, "consumer.drain not found in lifespan.py"
    assert eval_match.start() < consumer_match.start(), (
        f"Drain ordering violated: eval drain @ {eval_match.start()} must be < "
        f"consumer drain @ {consumer_match.start()} in lifespan.py source"
    )


@pytest.mark.asyncio
async def test_ld2_eval_drain_warns_drain_incomplete_when_judge_is_slow() -> None:
    """LD2: slow judge + 0.1s drain timeout -> eval.dispatcher_drain_incomplete."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.protocols import EvalScores

    class _SlowJudge:
        name = "slow"

        async def score(self, answer: str, chunks: list[Any], query: str) -> EvalScores:
            await asyncio.sleep(2.0)
            return EvalScores(faithfulness=0.5)

    class _FakeWriter:
        def __init__(self) -> None:
            self.emitted: list[Any] = []

        async def emit(self, span: Any) -> None:
            self.emitted.append(span)

    class _FakeConn:
        async def execute(self, query: str, *args: Any) -> None:
            return None

    class _FakeAcquireCtx:
        async def __aenter__(self) -> _FakeConn:
            return _FakeConn()

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class _FakePool:
        def acquire(self, timeout: float | None = None) -> _FakeAcquireCtx:
            return _FakeAcquireCtx()

    import contextvars

    dispatcher = EvalDispatcher(judge=_SlowJudge(), writer=_FakeWriter(), pool=_FakePool())
    dispatcher.enqueue(uuid4(), contextvars.copy_context(), "ans", [], "q")

    with patch("tracer_ai.eval.dispatcher.log") as mock_log:
        await dispatcher.drain(timeout=0.1)
        warn_calls = [
            c
            for c in mock_log.warning.call_args_list
            if c.args and c.args[0] == "eval.dispatcher_drain_incomplete"
        ]
        assert len(warn_calls) >= 1

    # Cleanup surviving task.
    import contextlib

    for t in list(dispatcher._pending):
        t.cancel()
        with contextlib.suppress(BaseException):
            await t
