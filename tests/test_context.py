"""Tests for tracer_ai/tracer/context.py (Phase 5 D-5.06; closes TRCR-04).

Verifies the hand-rolled contextvar helpers preserve the ADR 005
"zero-opentelemetry-runtime-dep" thesis while enabling the cross-task
span-parentage pattern documented in docs/sequence-diagrams.md (Pitfall #1
"capture context BEFORE root.end()").

Notes on the contract:
  - asyncio.create_task automatically calls copy_context(), so a child
    task inherits the parent's _current_span value WITHOUT explicit
    attach_context.
  - capture_context + attach_context exist for the OTHER pattern: a snapshot
    is taken at one moment and used inside an async coroutine launched LATER
    (D-5.10's dispatcher pattern) where the dispatcher's worker coroutine
    needs to install the snapshot's _current_span into its own context.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest


def _make_span():  # type: ignore[no-untyped-def]
    """Build an isolated Span instance for context tests."""
    from tracer_ai.tracer.writer import Span

    return Span(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        name="rag.request",
        started_at=datetime.now(UTC),
        ended_at=None,
        attrs={},
        payload=None,
    )


def test_current_span_is_none_at_module_import() -> None:
    """Test 1: with no caller having set a span, current_span() returns None."""
    from tracer_ai.tracer.context import current_span

    assert current_span() is None


def test_set_and_reset_current_span() -> None:
    """Test 2: set_current_span returns a token; ContextVar.reset(tok) restores None."""
    from tracer_ai.tracer.context import _current_span, current_span, set_current_span

    span = _make_span()
    tok = set_current_span(span)
    assert current_span() is span
    _current_span.reset(tok)
    assert current_span() is None


@pytest.mark.asyncio
async def test_capture_context_then_attach_in_other_coroutine() -> None:
    """Test 3: snapshot taken inside set_current_span scope, re-attached in
    a different async task, makes current_span() return the snapshot's span."""
    from tracer_ai.tracer.context import (
        _current_span,
        attach_context,
        capture_context,
        current_span,
        set_current_span,
    )

    span = _make_span()
    tok = set_current_span(span)
    snapshot = capture_context()
    # Reset OUTER context so we can prove the snapshot, not residue, did the work.
    _current_span.reset(tok)
    assert current_span() is None

    seen_span = []

    async def worker() -> None:
        # Inside this freshly-spawned coroutine, _current_span is None until we attach.
        attach_context(snapshot)
        seen_span.append(current_span())

    await asyncio.create_task(worker())
    assert seen_span == [span]


@pytest.mark.asyncio
async def test_create_task_inherits_current_span_via_copy_context() -> None:
    """Test 4: asyncio.create_task copies the parent's context automatically;
    a child task inherits _current_span WITHOUT explicit attach_context."""
    from tracer_ai.tracer.context import _current_span, current_span, set_current_span

    span = _make_span()
    tok = set_current_span(span)
    try:
        seen: list[object] = []

        async def child() -> None:
            seen.append(current_span())

        await asyncio.create_task(child())
        assert seen == [span]
    finally:
        _current_span.reset(tok)


@pytest.mark.asyncio
async def test_child_task_mutation_does_not_leak_to_parent() -> None:
    """Test 5: setting _current_span inside a spawned task must NOT propagate
    back into the parent's context (asyncio context-isolation invariant)."""
    from tracer_ai.tracer.context import _current_span, current_span, set_current_span

    parent_span = _make_span()
    tok = set_current_span(parent_span)
    try:
        other_span = _make_span()

        async def child() -> None:
            set_current_span(other_span)
            assert current_span() is other_span

        await asyncio.create_task(child())
        # Parent's current_span MUST still be the original (no leakage).
        assert current_span() is parent_span
    finally:
        _current_span.reset(tok)


@pytest.mark.asyncio
async def test_attach_context_is_idempotent() -> None:
    """Test 6: calling attach_context twice in the same coroutine is harmless."""
    from tracer_ai.tracer.context import (
        _current_span,
        attach_context,
        capture_context,
        current_span,
        set_current_span,
    )

    span = _make_span()
    tok = set_current_span(span)
    snapshot = capture_context()
    _current_span.reset(tok)

    async def worker() -> None:
        attach_context(snapshot)
        attach_context(snapshot)  # second call: must not raise; must remain consistent
        assert current_span() is span

    await asyncio.create_task(worker())
