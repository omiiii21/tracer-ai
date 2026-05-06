"""Unit tests for BoundedDropOldestQueue (Phase 4 D-4.06/TRCR-06)."""

from __future__ import annotations

import asyncio
import time as _time
from typing import Any
from unittest.mock import patch

import pytest

from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue


@pytest.mark.asyncio
async def test_put_returns_true_when_queue_has_space() -> None:
    q = BoundedDropOldestQueue(maxsize=3)
    result = await q.put("a")
    assert result is True
    assert q.qsize() == 1


@pytest.mark.asyncio
async def test_put_drops_oldest_and_returns_false_when_full() -> None:
    q = BoundedDropOldestQueue(maxsize=2)
    await q.put("first")
    await q.put("second")
    result = await q.put("third")  # drops "first"
    assert result is False
    assert q.qsize() == 2
    item = await q.get()
    assert item == "second"
    item = await q.get()
    assert item == "third"


@pytest.mark.asyncio
async def test_get_awaits_until_item_available() -> None:
    q = BoundedDropOldestQueue(maxsize=3)

    async def producer() -> None:
        await asyncio.sleep(0.05)
        await q.put("delayed")

    async def consumer() -> Any:
        return await q.get()

    consumer_task = asyncio.create_task(consumer())
    producer_task = asyncio.create_task(producer())
    item = await asyncio.wait_for(consumer_task, timeout=1.0)
    await producer_task
    assert item == "delayed"


@pytest.mark.asyncio
async def test_qsize_reports_current_depth() -> None:
    q = BoundedDropOldestQueue(maxsize=5)
    assert q.qsize() == 0
    await q.put("a")
    assert q.qsize() == 1
    await q.put("b")
    assert q.qsize() == 2
    await q.get()
    assert q.qsize() == 1


@pytest.mark.asyncio
async def test_concurrent_producers_at_capacity_drop_oldest_deterministically() -> None:
    q = BoundedDropOldestQueue(maxsize=3)
    # Pre-fill to capacity
    for n in range(3):
        await q.put(f"old_{n}")
    # 5 concurrent producers each push one item — all 5 should drop one item each
    results = await asyncio.gather(*(q.put(f"new_{i}") for i in range(5)))
    assert all(r is False for r in results)
    assert q.qsize() == 3
    # The 3 remaining items should be from the {new_*} set (oldest old_* items dropped)
    drained: list[str] = []
    while q.qsize() > 0:
        drained.append(await q.get())
    assert all(item.startswith("new_") for item in drained)


@pytest.mark.asyncio
async def test_get_clears_not_empty_event_when_deque_emptied() -> None:
    q = BoundedDropOldestQueue(maxsize=3)
    await q.put("only")
    assert q.qsize() == 1
    item = await q.get()
    assert item == "only"
    assert q.qsize() == 0
    # _not_empty should now be clear; subsequent get() should block
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.1)


@pytest.mark.asyncio
async def test_saturation_log_fires_at_most_once_per_second() -> None:
    """D-4.08: rate-limited log; counter resets per log period."""
    q = BoundedDropOldestQueue(maxsize=2)
    await q.put("a")
    await q.put("b")
    with patch("tracer_ai.tracer.exporters.queue.log") as mock_log:
        # First drop fires the log immediately (last_log_at == 0)
        await q.put("c")
        # Subsequent drops within 1s should NOT fire another log
        await q.put("d")
        await q.put("e")
        warning_calls = [
            call
            for call in mock_log.warning.call_args_list
            if call.args and call.args[0] == "tracer.queue_saturated"
        ]
        assert len(warning_calls) == 1
        # Verify structured fields are correct
        call = warning_calls[0]
        assert call.kwargs.get("window") == "1s"
        assert "dropped" in call.kwargs
        assert "queue_depth" in call.kwargs


@pytest.mark.asyncio
async def test_log_counter_resets_after_emission() -> None:
    """After a log emit, the dropped_count counter resets to 0."""
    q = BoundedDropOldestQueue(maxsize=2)
    await q.put("a")
    await q.put("b")
    # Force the rate-limit window to be open (set _last_log_at far enough in the past).
    q._last_log_at = _time.monotonic() - 2.0
    with patch("tracer_ai.tracer.exporters.queue.log") as mock_log:
        await q.put("c")  # drops, fires log, resets counter
        # After the log fires, _dropped_count was reset to 0
        assert q._dropped_count == 0
        warning_calls = [
            call
            for call in mock_log.warning.call_args_list
            if call.args and call.args[0] == "tracer.queue_saturated"
        ]
        assert len(warning_calls) == 1


@pytest.mark.asyncio
async def test_fifo_ordering_preserved_across_puts_and_gets() -> None:
    q = BoundedDropOldestQueue(maxsize=10)
    for n in range(5):
        await q.put(n)
    drained = [await q.get() for _ in range(5)]
    assert drained == [0, 1, 2, 3, 4]
