"""Anthropic streaming LLM adapter (Phase 3 Plan 05, RAG-03 / CHAT-02).

Per D-2.38 / SDK isolation: this is the ONLY file in tracer_ai/ allowed to
``import anthropic`` (alongside tracer_ai/eval/llm_judge.py in Phase 5).
The anti-pattern test ``tests/test_anti_patterns.py`` enforces this gate via
git-grep at pre-commit time.

Pattern references:
  - PATTERNS.md s"Backend Subsystem 4 -- llm.py" (lines 213-230) -- SDK
    isolation discipline + secret handling at the SDK boundary.
  - RESEARCH.md s3 lines 142-164 -- LLM Protocol shape + streaming semantics
    (TextDelta deltas + one final Final(LLMResult) at end).
  - RESEARCH.md s3 lines 162-164 -- cost computation from
    Settings.pricing.claude_sonnet_4_5_input_per_mtok / _output_per_mtok.

Streaming SDK shape (anthropic >= 0.49):
  async with client.messages.stream(
      model=..., max_tokens=..., system=..., messages=[...]
  ) as stream:
      async for event in stream:
          # event.type == "content_block_delta" carries event.delta.text
      final = await stream.get_final_message()
      # final.usage.input_tokens / final.usage.output_tokens
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from tracer_ai.config import settings
from tracer_ai.rag.protocols import LLM
from tracer_ai.rag.types import Final, LLMResult, Message, StreamEvent, TextDelta

log = structlog.get_logger()


def _cost_per_mtok(model_name: str) -> tuple[float, float]:
    """Pick (input_per_mtok, output_per_mtok) from settings based on model.

    Sonnet pricing if name contains "sonnet"; Haiku pricing if "haiku".
    Falls back to Sonnet pricing for unknown models (defensive default --
    Sonnet rates are higher so a misconfiguration fails toward over-estimating
    cost rather than silently under-reporting).
    """
    name = model_name.lower()
    if "haiku" in name:
        return (
            settings.pricing_claude_haiku_input_per_mtok,
            settings.pricing_claude_haiku_output_per_mtok,
        )
    # Default to Sonnet rates for "sonnet" or any unrecognized name.
    return (
        settings.pricing_claude_sonnet_4_5_input_per_mtok,
        settings.pricing_claude_sonnet_4_5_output_per_mtok,
    )


class AnthropicLLM:
    """Streaming Anthropic adapter -- yields TextDelta events + one Final(LLMResult).

    Constructor wraps ``AsyncAnthropic`` with the SecretStr key unwrapped at
    the SDK boundary only (T-03-05-02 mitigation -- key never logged).
    """

    def __init__(self, name: str | None = None) -> None:
        self.name: str = name or settings.llm_bot_model
        # SDK boundary: unwrap SecretStr exactly once at construction time.
        self._client: AsyncAnthropic = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )

    async def stream(
        self, messages: list[Message], *, max_tokens: int = 1024
    ) -> AsyncIterator[StreamEvent]:
        """Stream tokens from Anthropic; yield TextDelta events then one Final.

        Extracts the system prompt from any role="system" entry in ``messages``
        (Anthropic's API takes ``system`` as a top-level kwarg, not a turn).
        Remaining user/assistant entries are passed as ``messages``.

        Cost is computed from the final ``usage.input_tokens`` /
        ``usage.output_tokens`` against the per-million-token rates in
        ``Settings.pricing_*``. T-03-05-05 mitigation -- ``max_tokens=1024``
        default caps single-response cost.
        """
        # Split system from turn-message list. Anthropic's API surface treats
        # the system prompt as a top-level field separate from messages.
        system_parts: list[str] = []
        turn_messages: list[dict[str, str]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                turn_messages.append({"role": m.role, "content": m.content})
        system_prompt = "\n\n".join(system_parts) if system_parts else ""

        answer_parts: list[str] = []
        # ``messages.stream`` is a context manager whose iterator yields events
        # of type "content_block_delta" carrying ``delta.text`` for text-deltas.
        async with self._client.messages.stream(
            model=self.name,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=turn_messages,  # type: ignore[arg-type]
        ) as stream:
            async for event in stream:
                event_type: Any = getattr(event, "type", None)
                if event_type == "content_block_delta":
                    delta: Any = getattr(event, "delta", None)
                    text: Any = getattr(delta, "text", None)
                    if isinstance(text, str) and text:
                        answer_parts.append(text)
                        yield TextDelta(text=text)
            final = await stream.get_final_message()

        # Final usage + cost computation. ``final.usage`` is the SDK's
        # token-accounting object exposing ``.input_tokens`` / ``.output_tokens``.
        usage: Any = getattr(final, "usage", None)
        input_tokens: int = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens: int = int(getattr(usage, "output_tokens", 0) or 0)
        in_rate, out_rate = _cost_per_mtok(self.name)
        estimated_cost_usd = (input_tokens / 1_000_000.0) * in_rate + (
            output_tokens / 1_000_000.0
        ) * out_rate

        result = LLMResult(
            answer="".join(answer_parts),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
        log.info(
            "llm_stream_complete",
            model=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
        yield Final(result=result)


# Static structural typing shim -- mypy --strict catches Protocol-shape drift.
def _accepts_llm(_l: LLM) -> None: ...
