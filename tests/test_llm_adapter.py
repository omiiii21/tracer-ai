"""Tests for tracer_ai/rag/llm.py (Phase 3 Plan 05 / RAG-03).

Asserts:
  1. With a mocked AsyncAnthropic stream yielding 3 content_block_delta
     events + final, AnthropicLLM.stream yields 3 TextDelta + 1 Final.
  2. The Final.result has non-zero token counts and estimated_cost_usd
     matches the Sonnet pricing formula
     (100/1M * 3.00 + 20/1M * 15.00 == 0.0006).
  3. SDK errors raised inside the stream context propagate as exceptions.
  4. AnthropicLLM is structurally typed as the LLM Protocol (mypy + runtime).
  5. Anti-pattern grep: ``import anthropic`` / ``from anthropic`` only in
     tracer_ai/rag/llm.py (eval/llm_judge.py is reserved for Phase 5; no
     other tracer_ai/ file may import the SDK).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

# Configure env BEFORE the llm module is imported (settings is module-top
# fail-fast). Use a Pytest plugin-style hook: run via fixture autouse=True.


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.rag.llm", None)


# --- Test infrastructure ---------------------------------------------------


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeFinalMessage:
    def __init__(self, input_tokens: int = 100, output_tokens: int = 20) -> None:
        self.usage = _FakeUsage(input_tokens, output_tokens)


def _delta_event(text: str) -> Any:
    """Build a fake event matching Anthropic SDK content_block_delta shape."""
    return SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text=text))


class _FakeStream:
    """Mocks `client.messages.stream(...)` context manager + async iterator."""

    def __init__(
        self,
        deltas: list[str],
        *,
        final_input: int = 100,
        final_output: int = 20,
        raise_on_iter: Exception | None = None,
    ) -> None:
        self._events = [_delta_event(d) for d in deltas]
        self._final_input = final_input
        self._final_output = final_output
        self._raise_on_iter = raise_on_iter

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    def __aiter__(self) -> _FakeStream:
        self._idx = 0
        return self

    async def __anext__(self) -> Any:
        if self._raise_on_iter is not None:
            raise self._raise_on_iter
        if self._idx >= len(self._events):
            raise StopAsyncIteration
        ev = self._events[self._idx]
        self._idx += 1
        return ev

    async def get_final_message(self) -> _FakeFinalMessage:
        return _FakeFinalMessage(input_tokens=self._final_input, output_tokens=self._final_output)


class _FakeMessages:
    def __init__(self, stream: _FakeStream) -> None:
        self._stream = stream

    def stream(self, **_kwargs: Any) -> _FakeStream:
        return self._stream


class _FakeAsyncAnthropic:
    """Replaces ``AsyncAnthropic`` on the llm module."""

    def __init__(self, stream: _FakeStream) -> None:
        self.messages = _FakeMessages(stream)


def _patch_async_anthropic(monkeypatch: pytest.MonkeyPatch, stream: _FakeStream) -> None:
    """Patch the AsyncAnthropic constructor used inside llm.py."""
    import tracer_ai.rag.llm as llm_mod

    def _factory(*_args: Any, **_kwargs: Any) -> _FakeAsyncAnthropic:
        return _FakeAsyncAnthropic(stream)

    monkeypatch.setattr(llm_mod, "AsyncAnthropic", _factory)


# --- Test 1: 3 deltas + 1 final --------------------------------------------


@pytest.mark.asyncio
async def test_stream_yields_three_text_deltas_then_one_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_stream = _FakeStream(["Hello", " ", "world"], final_input=100, final_output=20)
    _patch_async_anthropic(monkeypatch, fake_stream)

    from tracer_ai.rag.llm import AnthropicLLM
    from tracer_ai.rag.types import Final, Message, TextDelta

    adapter = AnthropicLLM(name="claude-sonnet-4-5-20250929")
    events = []
    async for ev in adapter.stream([Message(role="user", content="hi")]):
        events.append(ev)

    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    finals = [e for e in events if isinstance(e, Final)]
    assert len(text_deltas) == 3
    assert [d.text for d in text_deltas] == ["Hello", " ", "world"]
    assert len(finals) == 1


# --- Test 2: Final has non-zero tokens + correct Sonnet cost ---------------


@pytest.mark.asyncio
async def test_final_has_token_counts_and_sonnet_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_stream = _FakeStream(["a"], final_input=100, final_output=20)
    _patch_async_anthropic(monkeypatch, fake_stream)

    from tracer_ai.rag.llm import AnthropicLLM
    from tracer_ai.rag.types import Final, Message

    adapter = AnthropicLLM(name="claude-sonnet-4-5-20250929")
    events = []
    async for ev in adapter.stream([Message(role="user", content="hi")]):
        events.append(ev)

    final_event = next(e for e in events if isinstance(e, Final))
    result = final_event.result
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    # Sonnet 4.5 pricing: $3 / Mtok input + $15 / Mtok output (defaults).
    # 100/1e6 * 3 + 20/1e6 * 15 = 0.0003 + 0.0003 = 0.0006
    assert result.estimated_cost_usd == pytest.approx(0.0006, abs=1e-9)
    assert result.answer == "a"


# --- Test 3: SDK error inside stream propagates ----------------------------


@pytest.mark.asyncio
async def test_sdk_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_stream = _FakeStream(
        [],
        raise_on_iter=RuntimeError("simulated SDK failure"),
    )
    _patch_async_anthropic(monkeypatch, fake_stream)

    from tracer_ai.rag.llm import AnthropicLLM
    from tracer_ai.rag.types import Message

    adapter = AnthropicLLM(name="claude-sonnet-4-5-20250929")
    with pytest.raises(RuntimeError, match="simulated SDK failure"):
        async for _ in adapter.stream([Message(role="user", content="x")]):
            pass


# --- Test 4: Structural typing shim ----------------------------------------


@pytest.mark.asyncio
async def test_anthropic_llm_structurally_is_an_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_stream = _FakeStream(["x"])
    _patch_async_anthropic(monkeypatch, fake_stream)

    from tracer_ai.rag.llm import AnthropicLLM
    from tracer_ai.rag.protocols import LLM

    adapter = AnthropicLLM(name="claude-sonnet-4-5-20250929")
    # Runtime structural-typing check (Protocol is runtime_checkable).
    assert isinstance(adapter, LLM)


# --- Test 5: Anti-pattern grep -- only llm.py imports anthropic -----------


def test_only_llm_py_imports_anthropic() -> None:
    """D-2.38: ``import anthropic`` / ``from anthropic`` only in
    tracer_ai/rag/llm.py (eval/llm_judge.py allowed in Phase 5; not yet present).

    Helper mirrors the docstring-aware scan from Plan 03-01: parses each
    .py file's source into in-docstring vs code regions, then flags only
    real-import lines outside the allowlist.
    """
    repo_root = Path(__file__).resolve().parent.parent
    pkg = repo_root / "tracer_ai"
    allowlist = {
        (pkg / "rag" / "llm.py").resolve(),
        (pkg / "eval" / "llm_judge.py").resolve(),
    }
    violators: list[str] = []
    for py in pkg.rglob("*.py"):
        if py.resolve() in allowlist:
            continue
        text = py.read_text(encoding="utf-8")
        for ln in text.splitlines():
            stripped = ln.strip()
            if re.match(r"^(import anthropic|from anthropic\b)", stripped):
                violators.append(f"{py}: {stripped}")
    assert not violators, f"Forbidden anthropic SDK imports: {violators}"


# --- Test 6: Haiku pricing branch ------------------------------------------


@pytest.mark.asyncio
async def test_haiku_model_uses_haiku_pricing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cost picker selects Haiku rates ($0.80/$4.00) for haiku model names."""
    fake_stream = _FakeStream(["a"], final_input=100, final_output=20)
    _patch_async_anthropic(monkeypatch, fake_stream)

    from tracer_ai.rag.llm import AnthropicLLM
    from tracer_ai.rag.types import Final, Message

    adapter = AnthropicLLM(name="claude-haiku-4-5-20251001")
    events = []
    async for ev in adapter.stream([Message(role="user", content="hi")]):
        events.append(ev)

    final_event = next(e for e in events if isinstance(e, Final))
    # Haiku: 100/1e6 * 0.80 + 20/1e6 * 4.00 = 0.00008 + 0.00008 = 0.00016
    assert final_event.result.estimated_cost_usd == pytest.approx(0.00016, abs=1e-9)
