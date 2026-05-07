"""Anthropic Haiku LLM-as-judge adapter (Phase 5 EVAL-01 / EVAL-04).

Per D-2.38 / SDK isolation: this is the second of two files in tracer_ai/
allowed to ``from anthropic import ...`` (the first is tracer_ai/rag/llm.py).
The anti-pattern test ``tests/test_anti_patterns.py`` enforces this gate via
git-grep at pre-commit time; the allowlist already includes this path
(reserved during Phase 2).

Per D-5.01: ONE combined Haiku call returns BOTH faithfulness and relevance.
Per D-5.02: tool_use forced via ``tool_choice={"type":"tool","name":"submit_eval"}``;
parse via direct dict access on ``msg.content[*].input``. No regex / json.loads.
Per D-5.04: ``PROMPT_VERSION`` is a module constant -- bumped manually when
the prompt body changes (e.g., ``v2.calibrated-2026-05`` after EVAL-06).
Per D-5.05: 10s timeout, 1 retry on transient SDK errors; parse-shape errors
do NOT retry (retrying same prompt won't change the answer).
Per D-5.09: module-level asyncio.Semaphore bounds in-flight judge calls.
Per EVAL-04 (Phase 5 fix): ``judge_cost_usd`` computed on every successful
call from settings.pricing_claude_haiku_*_per_mtok.

Pattern references:
  - tracer_ai/rag/llm.py: AnthropicLLM constructor pattern (SecretStr unwrap
    at SDK boundary; settings-driven model name).
  - tests/test_llm_adapter.py:30-119: _FakeAsyncAnthropic infra pattern.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    RateLimitError,
)
from anthropic.types import ToolParam

from tracer_ai.config import settings
from tracer_ai.eval.prompts import JUDGE_SYSTEM_PROMPT, build_judge_prompt
from tracer_ai.eval.protocols import EvalScores, ToolUseParseError
from tracer_ai.rag.types import RetrievedChunk

log = structlog.get_logger()

# D-5.04: PROMPT_VERSION is a module-level constant, bumped manually when
# the prompt body changes. Bumping should follow EVAL-06 calibration cycles.
PROMPT_VERSION: str = "v1.ragas-faithfulness-relevance"

# D-5.02: SUBMIT_EVAL_TOOL is the tool schema the judge is forced to call.
# Pydantic EvalScores re-validates the same shape after parsing -- defense in
# depth against malformed model output.
SUBMIT_EVAL_TOOL: ToolParam = {
    "name": "submit_eval",
    "description": (
        "Submit faithfulness and relevance scores for an assistant answer. "
        "faithfulness measures whether the answer is grounded in the retrieved "
        "chunks (no hallucinated facts). relevance measures whether the chunks "
        "address the user's query."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "faithfulness": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "0.0 (answer contradicts chunks) to 1.0 (answer fully grounded "
                    "in the chunks)."
                ),
            },
            "relevance": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "0.0 (chunks unrelated to query) to 1.0 (chunks directly answer " "the query)."
                ),
            },
            "rationale": {
                "type": "string",
                "description": "One sentence justification for the scores.",
            },
        },
        "required": ["faithfulness", "relevance", "rationale"],
    },
}

# D-5.09: module-level singleton bounds in-flight judge calls. Eager init
# (settings is already imported above; no circular-import risk from this file).
_judge_semaphore: asyncio.Semaphore = asyncio.Semaphore(settings.judge_concurrency)


def get_judge_semaphore() -> asyncio.Semaphore:
    """Return the module-level judge semaphore (D-5.09)."""
    return _judge_semaphore


def _extract_tool_use_input(msg: Any) -> dict[str, Any]:
    """Walk msg.content for the first tool_use block; raise on parse failure.

    Per D-5.05: this raises ``ToolUseParseError`` immediately on shape mismatch
    (no retry). The dispatcher's failure-span path handles the exception by
    emitting a rag.eval span with NULL scores + ``error.type`` populated.
    """
    content = getattr(msg, "content", None)
    if not content:
        raise ToolUseParseError("judge response had empty content")
    for block in content:
        if getattr(block, "type", None) == "tool_use":
            tool_input = getattr(block, "input", None)
            if not isinstance(tool_input, dict):
                raise ToolUseParseError("tool_use block present but input is not a dict")
            return tool_input
    raise ToolUseParseError("no tool_use block found in judge response")


class AnthropicJudge:
    """Anthropic Haiku LLM-as-judge adapter (Phase 5 EVAL-01).

    Constructor wraps ``AsyncAnthropic`` with the SecretStr key unwrapped at
    the SDK boundary only (mirrors ``AnthropicLLM`` -- key never logged).
    """

    def __init__(self, name: str | None = None) -> None:
        self.name: str = name or settings.llm_judge_model
        # D-5.05: 10s timeout from settings.judge_timeout_seconds; SDK boundary
        # unwraps SecretStr exactly once at construction time.
        self._client: AsyncAnthropic = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.judge_timeout_seconds,
        )

    async def score(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        query: str,
    ) -> EvalScores:
        """Score an answer for faithfulness + relevance against retrieved chunks.

        Per D-5.05 retry policy: 1 retry on transient SDK errors
        (RateLimitError / APIConnectionError / APITimeoutError); 2nd failure
        re-raises. Parse-shape errors (ToolUseParseError) do NOT retry.

        Per EVAL-04: judge_cost_usd computed from settings.pricing_claude_haiku_*
        and populated on every successful return.
        """
        prompt = build_judge_prompt(query=query, answer=answer, chunks=chunks)

        last_exc: Exception | None = None
        msg: Any = None
        t0: float = time.perf_counter()
        for attempt in (1, 2):
            try:
                t0 = time.perf_counter()
                msg = await self._client.messages.create(
                    model=self.name,
                    max_tokens=1024,
                    system=JUDGE_SYSTEM_PROMPT,
                    tools=[SUBMIT_EVAL_TOOL],
                    tool_choice={"type": "tool", "name": "submit_eval"},
                    messages=[{"role": "user", "content": prompt}],
                )
                break
            except (RateLimitError, APIConnectionError, APITimeoutError) as exc:
                last_exc = exc
                if attempt == 1:
                    log.warning(
                        "judge_transient_error_retrying",
                        error_type=type(exc).__name__,
                    )
                    await asyncio.sleep(0.5)
                    continue
                # Second failure: propagate to dispatcher's failure-span path.
                log.warning(
                    "judge_transient_error_giving_up",
                    error_type=type(exc).__name__,
                )
                raise

        # Defensive: msg must be set if loop exited via break.
        if msg is None:  # pragma: no cover -- only reachable via logic bug
            raise RuntimeError(f"judge call exited without a message; last error: {last_exc!r}")

        # D-5.02: parse the tool_use block (no regex, no json.loads).
        tool_input = _extract_tool_use_input(msg)

        usage = getattr(msg, "usage", None)
        input_tokens: int = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens: int = int(getattr(usage, "output_tokens", 0) or 0)

        # EVAL-04 cost computation: per-million-token rates from Settings.
        cost_usd: float = (
            settings.pricing_claude_haiku_input_per_mtok * input_tokens
            + settings.pricing_claude_haiku_output_per_mtok * output_tokens
        ) / 1_000_000.0

        judge_latency_ms: int = int((time.perf_counter() - t0) * 1000)

        # D-5.03: store the FULL judge_response payload so trace-detail can
        # render it without re-running. Pydantic EvalScores re-validates the
        # tool_input fields against the [0.0, 1.0] bounds (defense in depth).
        return EvalScores(
            faithfulness=float(tool_input.get("faithfulness", 0.0)),
            relevance=float(tool_input.get("relevance", 0.0)),
            rationale=str(tool_input.get("rationale", "")),
            judge_prompt=prompt,
            judge_response=dict(tool_input),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            judge_latency_ms=judge_latency_ms,
            judge_cost_usd=cost_usd,
        )


class MockJudge:
    """In-process test double for the Judge Protocol.

    Returns canned scores -- used by integration tests that need a deterministic
    Judge without spinning up the AsyncAnthropic SDK. ``raise_on_call`` causes
    every call to raise the given exception (used to test the dispatcher's
    failure-span path).
    """

    name: str = "mock-judge"

    def __init__(
        self,
        faithfulness: float | None = 0.8,
        relevance: float | None = 0.9,
        rationale: str = "mock",
        raise_on_call: type[BaseException] | None = None,
    ) -> None:
        self._faithfulness = faithfulness
        self._relevance = relevance
        self._rationale = rationale
        self._raise_on_call = raise_on_call

    async def score(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        query: str,
    ) -> EvalScores:
        if self._raise_on_call is not None:
            raise self._raise_on_call("mock-judge raise_on_call")
        return EvalScores(
            faithfulness=self._faithfulness,
            relevance=self._relevance,
            rationale=self._rationale,
            judge_prompt=build_judge_prompt(query=query, answer=answer, chunks=chunks),
            judge_response={
                "faithfulness": self._faithfulness,
                "relevance": self._relevance,
                "rationale": self._rationale,
            },
            input_tokens=0,
            output_tokens=0,
            judge_latency_ms=0,
            judge_cost_usd=0.0,
        )
