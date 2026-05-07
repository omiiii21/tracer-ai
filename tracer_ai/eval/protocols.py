"""Phase 5 eval Protocol + result schema (D-5.01..D-5.05 / EVAL-04).

The Judge Protocol mirrors the LLM Protocol shape (tracer_ai/rag/protocols.py)
so the dispatcher can compose adapters interchangeably for testing. Phase 5
ships ``AnthropicJudge`` (production) + ``MockJudge`` (test double); both
satisfy this contract structurally.

EvalScores carries the parsed judge output (faithfulness / relevance / rationale)
plus the full prompt + response (D-5.03 -- propagated to span_payloads), token
counts (D-5.02), latency, and ``judge_cost_usd`` (Phase 5 EVAL-04 fix --
computed by the adapter from settings.pricing_claude_haiku_*).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from tracer_ai.rag.types import RetrievedChunk


class EvalScores(BaseModel):
    """Parsed judge output (D-5.02 / D-5.03 / EVAL-04).

    Populated from Anthropic ``tool_use.input`` direct dict access. The
    ``judge_prompt`` and ``judge_response`` fields are propagated to the
    rag.eval span_payloads row so the trace-detail Payloads tab can answer
    "why did the judge score this 0.4?" without re-running the judge call.

    ``judge_cost_usd`` (Phase 5 EVAL-04 fix) carries the computed Anthropic
    spend for this judge call so the dispatcher can stamp the rag.eval span's
    ``rag.eval.judge_cost_usd`` attribute and the dashboard can sum it.
    """

    model_config = ConfigDict(extra="forbid")

    faithfulness: float | None = Field(default=None, ge=0.0, le=1.0)
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = ""
    judge_prompt: str = ""
    judge_response: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    judge_latency_ms: int = Field(default=0, ge=0)
    judge_cost_usd: float = Field(default=0.0, ge=0.0)  # NEW: EVAL-04 fix


class ToolUseParseError(Exception):
    """Judge response did not contain a valid tool_use content block.

    Per D-5.05: parse-shape errors do NOT retry. The dispatcher catches this
    in its failure-span path and emits a rag.eval span with NULL scores.
    """


@runtime_checkable
class Judge(Protocol):
    """Score an answer + retrieved chunks for faithfulness + relevance.

    Phase 5 adapter: ``AnthropicJudge`` wrapping
    ``AsyncAnthropic.messages.create(..., tools=[SUBMIT_EVAL_TOOL])``.
    Returns one ``EvalScores`` per call (no streaming -- tool_use is a single
    structured blob).
    """

    name: str

    async def score(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        query: str,
    ) -> EvalScores: ...
