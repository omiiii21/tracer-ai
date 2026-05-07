"""Hand-rolled contextvar helpers for cross-task span parentage (D-5.06; closes TRCR-04).

Closes TRCR-04 with zero ``opentelemetry-*`` runtime deps -- preserves ADR 005's
"OTel-compatible naming, no OTel runtime" thesis (no opentelemetry-sdk, and
Phase 5 strengthens this to no opentelemetry-api either).

Per Pitfall #1 (docs/sequence-diagrams.md): capture context snapshot BEFORE
rag.request root span ends. Per D-5.10: the snapshot is taken by the SSE
generator immediately after the ``final`` frame yields, then passed to
``EvalDispatcher.enqueue(...)`` so the rag.eval span becomes a child of
rag.request rather than an orphan root.

Notes on the contract:
  - ``asyncio.create_task`` automatically calls ``contextvars.copy_context()``,
    so a child task already inherits the parent's ``_current_span`` value
    WITHOUT any explicit ``attach_context`` call.
  - ``capture_context`` + ``attach_context`` exist for the OTHER pattern: a
    snapshot taken at one moment, used in an async coroutine launched LATER
    (D-5.10's dispatcher pattern), where the dispatcher worker coroutine
    needs to install the snapshot's ``_current_span`` into its own context.
"""

from __future__ import annotations

import contextvars
from contextvars import Context, ContextVar, Token
from typing import Final

from tracer_ai.tracer.writer import Span

_current_span: Final[ContextVar[Span | None]] = ContextVar(
    "tracer_ai.current_span",
    default=None,
)


def current_span() -> Span | None:
    """Return the active span in this execution context (None at the root)."""
    return _current_span.get()


def set_current_span(span: Span | None) -> Token[Span | None]:
    """Set the active span; return a token usable with ``_current_span.reset(token)``."""
    return _current_span.set(span)


def capture_context() -> Context:
    """Snapshot current contextvars.

    Pitfall #1 (docs/sequence-diagrams.md): call BEFORE the root span's
    ``ended_at`` is set, so the snapshot's ``_current_span`` is still the
    rag.request root span (and rag.eval can become its child).
    """
    return contextvars.copy_context()


def attach_context(ctx: Context) -> None:
    """Install ContextVar values from ``ctx`` into THIS coroutine's context.

    Implementation note: ``contextvars.Context.run(func)`` is the canonical
    way to execute code inside a snapshot, but it is sync-only and would
    therefore not compose with the dispatcher's async worker coroutine.
    For tracer-ai the only var we propagate is ``_current_span``, so a
    single ``set()`` call suffices. Calling this twice with the same
    snapshot is idempotent (the second ``set()`` writes the same value).
    """
    span = ctx.get(_current_span, None)
    if span is not None:
        _current_span.set(span)
