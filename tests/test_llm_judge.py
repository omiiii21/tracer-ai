"""Tests for tracer_ai/eval/llm_judge.py (Phase 5 EVAL-01 / EVAL-04 cost fix).

Mirrors the _FakeAsyncAnthropic factory + autouse env fixture pattern from
tests/test_llm_adapter.py. The test surface verifies:

  - Judge / MockJudge runtime_checkable Protocol conformance
  - tool_use parsing path returns EvalScores with full token + cost accounting
  - EVAL-04 cost fix: judge_cost_usd computed from settings.pricing_claude_haiku_*
  - Retry policy (D-5.05): 1 retry on transient SDK errors (RateLimit / Connection
    / Timeout); 2nd failure re-raises
  - ToolUseParseError raised immediately when no tool_use block (no retry)
  - PROMPT_VERSION module constant
  - Module-level _judge_semaphore singleton with value == settings.judge_concurrency
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed required env vars so settings = Settings() succeeds at module-top import."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.eval.llm_judge", None)
    sys.modules.pop("tracer_ai.eval", None)


# ---------------------------------------------------------------------------
# _FakeAsyncAnthropic infrastructure (mirrors tests/test_llm_adapter.py:30-119).
# ---------------------------------------------------------------------------


class _FakeMessages:
    """Mocks ``client.messages`` for the judge call.

    ``calls_to_make`` is a list of (action, payload) tuples where action is one
    of {"return", "raise"}. Each call to ``create()`` consumes one entry.
    """

    def __init__(self, calls_to_make: list[tuple[str, Any]]) -> None:
        self._calls = list(calls_to_make)
        self.call_count = 0

    async def create(self, **_kwargs: Any) -> Any:
        self.call_count += 1
        if not self._calls:
            raise RuntimeError("Fake exhausted; no more queued calls")
        action, payload = self._calls.pop(0)
        if action == "raise":
            raise payload
        return payload


class _FakeAsyncAnthropic:
    def __init__(self, messages: _FakeMessages) -> None:
        self.messages = messages


def _patch_async_anthropic(monkeypatch: pytest.MonkeyPatch, fake: _FakeAsyncAnthropic) -> None:
    """Patch the AsyncAnthropic constructor used inside llm_judge.py."""
    import tracer_ai.eval.llm_judge as mod

    def _factory(*_args: Any, **_kwargs: Any) -> _FakeAsyncAnthropic:
        return fake

    monkeypatch.setattr(mod, "AsyncAnthropic", _factory)


def _build_tool_use_message(
    *,
    faithfulness: float = 0.8,
    relevance: float = 0.9,
    rationale: str = "ok",
    input_tokens: int = 1500,
    output_tokens: int = 120,
) -> Any:
    """Construct a fake AsyncAnthropic.messages.create return shape."""
    tool_use = SimpleNamespace(
        type="tool_use",
        name="submit_eval",
        input={
            "faithfulness": faithfulness,
            "relevance": relevance,
            "rationale": rationale,
        },
    )
    return SimpleNamespace(
        content=[tool_use],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        stop_reason="tool_use",
    )


def _build_text_only_message() -> Any:
    """Build a fake response with no tool_use block (only a text block)."""
    text_block = SimpleNamespace(type="text", text="I refuse to use the tool.")
    return SimpleNamespace(
        content=[text_block],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        stop_reason="end_turn",
    )


def _make_chunk():  # type: ignore[no-untyped-def]
    """Build a RetrievedChunk for judge tests."""
    from tracer_ai.rag.types import RetrievedChunk

    return RetrievedChunk(
        id=uuid4(),
        doc_id="d1",
        doc_section="auth",
        content="The Anthropic Messages API uses POST /v1/messages.",
        metadata={},
        score=0.92,
    )


# ---------------------------------------------------------------------------
# Test JudgeA / B: Protocol conformance.
# ---------------------------------------------------------------------------


def test_anthropic_judge_is_a_judge() -> None:
    """JudgeA: AnthropicJudge is structurally a Judge (runtime_checkable)."""
    from tracer_ai.eval.llm_judge import AnthropicJudge
    from tracer_ai.eval.protocols import Judge

    judge = AnthropicJudge()
    assert isinstance(judge, Judge)


def test_mock_judge_is_a_judge() -> None:
    """JudgeB: MockJudge is structurally a Judge."""
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.eval.protocols import Judge

    judge = MockJudge()
    assert isinstance(judge, Judge)


# ---------------------------------------------------------------------------
# Test JudgeC / JudgeC2: tool_use happy path + EVAL-04 cost computation.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_returns_eval_scores_with_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JudgeC: tool_use happy path returns EvalScores with all fields populated.

    JudgeJ (EVAL-04 fail-path coverage): on success, judge_cost_usd > 0 and is
    a member of the returned EvalScores field set.
    """
    msg = _build_tool_use_message(
        faithfulness=0.8, relevance=0.9, rationale="ok", input_tokens=1500, output_tokens=120
    )
    fake = _FakeAsyncAnthropic(_FakeMessages([("return", msg)]))
    _patch_async_anthropic(monkeypatch, fake)

    from tracer_ai.eval.llm_judge import AnthropicJudge

    judge = AnthropicJudge()
    chunks = [_make_chunk()]
    scores = await judge.score("ans", chunks, "q")

    assert scores.faithfulness == 0.8
    assert scores.relevance == 0.9
    assert scores.rationale == "ok"
    assert scores.judge_prompt  # non-empty
    assert isinstance(scores.judge_response, dict)
    assert scores.input_tokens == 1500
    assert scores.output_tokens == 120
    assert scores.judge_latency_ms >= 0
    # EVAL-04: judge_cost_usd populated, > 0 on success.
    assert scores.judge_cost_usd > 0


@pytest.mark.asyncio
async def test_judge_cost_usd_matches_pricing_formula(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JudgeC2 (EVAL-04 cost fix): judge_cost_usd = (in_rate * in_toks + out_rate * out_toks) / 1e6.

    Defaults: 0.80 USD / Mtok input, 4.00 USD / Mtok output.
    1500 input + 120 output -> (0.80 * 1500 + 4.00 * 120) / 1e6 = 0.00168 USD.
    """
    msg = _build_tool_use_message(input_tokens=1500, output_tokens=120)
    fake = _FakeAsyncAnthropic(_FakeMessages([("return", msg)]))
    _patch_async_anthropic(monkeypatch, fake)

    from tracer_ai.config import settings
    from tracer_ai.eval.llm_judge import AnthropicJudge

    judge = AnthropicJudge()
    scores = await judge.score("ans", [_make_chunk()], "q")
    expected = (
        settings.pricing_claude_haiku_input_per_mtok * 1500
        + settings.pricing_claude_haiku_output_per_mtok * 120
    ) / 1_000_000
    assert scores.judge_cost_usd == pytest.approx(expected, rel=1e-6)
    # Sanity check against the literal default value.
    assert scores.judge_cost_usd == pytest.approx(0.00168, rel=1e-6)


# ---------------------------------------------------------------------------
# Test JudgeD: 1 retry on RateLimitError, then succeed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retries_once_on_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JudgeD: RateLimitError on first call -> 1 retry -> success on 2nd call.

    Speeds the test by patching the backoff sleep to a no-op.
    """
    import httpx
    from anthropic import RateLimitError

    # SDK 0.49+ requires (message, *, response: httpx.Response, body). Build a
    # real httpx.Response with an attached Request so super().__init__ can
    # access response.request without an AttributeError.
    fake_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_response = httpx.Response(429, request=fake_request)
    rate_err: BaseException = RateLimitError(message="rate", response=fake_response, body=None)

    success_msg = _build_tool_use_message()
    fake_msgs = _FakeMessages([("raise", rate_err), ("return", success_msg)])
    fake = _FakeAsyncAnthropic(fake_msgs)
    _patch_async_anthropic(monkeypatch, fake)

    import tracer_ai.eval.llm_judge as mod

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)

    judge = mod.AnthropicJudge()
    scores = await judge.score("ans", [_make_chunk()], "q")
    assert scores.faithfulness == 0.8
    assert fake_msgs.call_count == 2  # one failed call + one successful retry


# ---------------------------------------------------------------------------
# Test JudgeE: 2 timeouts -> raise; total attempts == 2.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_does_not_retry_more_than_once_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JudgeE: 2 APITimeoutError raises -> 2 attempts total -> propagate the error."""
    from anthropic import APITimeoutError

    try:
        timeout_err = APITimeoutError(request=SimpleNamespace(url="x"))  # type: ignore[arg-type]
    except TypeError:
        timeout_err = APITimeoutError("timeout")  # type: ignore[call-arg]

    fake_msgs = _FakeMessages([("raise", timeout_err), ("raise", timeout_err)])
    fake = _FakeAsyncAnthropic(fake_msgs)
    _patch_async_anthropic(monkeypatch, fake)

    import tracer_ai.eval.llm_judge as mod

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)

    judge = mod.AnthropicJudge()
    with pytest.raises(APITimeoutError):
        await judge.score("ans", [_make_chunk()], "q")
    assert fake_msgs.call_count == 2  # NO third attempt


# ---------------------------------------------------------------------------
# Test JudgeF: text-only response -> ToolUseParseError (no retry).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_tool_use_block_raises_parse_error_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JudgeF: response without a tool_use content block raises ToolUseParseError.

    Per D-5.05: parse-shape errors do NOT retry (the model didn't fill the tool
    schema; retrying same prompt won't change the answer).
    """
    text_only = _build_text_only_message()
    fake_msgs = _FakeMessages([("return", text_only)])
    fake = _FakeAsyncAnthropic(fake_msgs)
    _patch_async_anthropic(monkeypatch, fake)

    from tracer_ai.eval.llm_judge import AnthropicJudge
    from tracer_ai.eval.protocols import ToolUseParseError

    judge = AnthropicJudge()
    with pytest.raises(ToolUseParseError):
        await judge.score("ans", [_make_chunk()], "q")
    # Single call -- no retry on parse error.
    assert fake_msgs.call_count == 1


# ---------------------------------------------------------------------------
# Test JudgeG: PROMPT_VERSION constant.
# ---------------------------------------------------------------------------


def test_prompt_version_constant_locked() -> None:
    """JudgeG (D-5.04): PROMPT_VERSION = 'v1.ragas-faithfulness-relevance' exactly."""
    from tracer_ai.eval.llm_judge import PROMPT_VERSION

    assert PROMPT_VERSION == "v1.ragas-faithfulness-relevance"


# ---------------------------------------------------------------------------
# Test JudgeH: module-level _judge_semaphore singleton.
# ---------------------------------------------------------------------------


def test_get_judge_semaphore_is_singleton() -> None:
    """JudgeH (D-5.09): repeated calls return the same Semaphore; value matches
    settings.judge_concurrency."""
    from tracer_ai.config import settings
    from tracer_ai.eval.llm_judge import get_judge_semaphore

    s1 = get_judge_semaphore()
    s2 = get_judge_semaphore()
    assert s1 is s2
    # Semaphore._value reflects available permits (== max at construction).
    assert s1._value == settings.judge_concurrency  # type: ignore[attr-defined]
