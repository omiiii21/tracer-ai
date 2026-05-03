# ADR 007: Re-ranking — None in v1

## Status

Accepted — 2026-05-04

## Context

Cross-encoder re-rankers (Cohere Rerank, BGE local cross-encoders) re-score the top-N bi-encoder results to improve retrieval precision. They reliably improve top-1 / top-3 quality on retrieval benchmarks. The cost is real: an additional model call (latency + price) per query, a third dependency to manage alongside the embedder and the LLM, and a second tier of model-version drift to track.

tracer-ai v1's measurable goal is **per-stage trace observability**, not retrieval-precision SOTA. Adding a re-ranker before establishing a clean baseline would (a) make it harder to attribute retrieval-quality gains to upstream improvements (chunking, embedder), and (b) consume budget that is better spent on the differentiating observability features.

This decision resolves [GSD-OPEN-7](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **No re-ranker in v1 (chosen):** Ship the bi-encoder baseline. Use Phase 5 quality metrics to determine whether retrieval is in fact the bottleneck before adding cost.
- **Cohere Rerank (deferred to v2 V2-RANK-01):** Strong managed re-ranker; would require a `COHERE_API_KEY` and added latency.
- **BGE local cross-encoder (deferred to v2):** Self-hosted; no extra API key but heavier inference per query and adds a third model dependency.

## Decision

tracer-ai v1 ships **without a re-ranker**. The `Retriever` Protocol in `tracer_ai/rag/retriever.py` is designed so a re-ranking step can be inserted between the bi-encoder retrieve and the prompt-assemble stages without changing the surrounding contract — the retriever returns a ranked list of `RetrievedChunk` objects, which a future re-ranker can re-order in place. A reserved configuration flag **`ENABLE_RERANKER`** is documented in `tracer_ai/config.py` but **unimplemented in v1**: no code path consults it; it exists to advertise the v2 hook point.

Phase 5 EVAL-06 calibration is the gate for revisiting this decision. If post-calibration faithfulness scores show retrieval as the dominant failure mode, V2-RANK-01 is the lift.

## Consequences

**Positive:**
- Simpler v1 pipeline: one embedder, one LLM, no third moving piece.
- Cleaner baseline metrics — we will know whether a re-ranker would help before paying for one.
- Lower per-query cost and latency; the chat path stays responsive on a laptop.
- Hook point is documented, so adding V2-RANK-01 will not require pipeline restructuring.

**Negative:**
- Retrieval precision may underperform a re-ranked baseline. We accept this for v1 and expose the gap via per-stage trace metrics so it is diagnosable.
- Adding the re-ranker later requires a Phase 5+ calibration pass — earlier insertion would have folded into existing calibration work.

**Mandatory follow-ups:**
- [ ] Document the reserved `ENABLE_RERANKER` config flag in `/docs/api.md` with an explicit "v1: ignored; reserved for v2" note.
- [ ] After Phase 5 calibration, re-open this ADR if retrieval is the dominant failure mode (replace with a successor ADR; ADRs are immutable once Accepted).

## References

- [.planning/research/STACK.md](../../.planning/research/STACK.md) — re-ranking discussion.
- [.planning/research/SUMMARY.md §"Defer (v2+ / out of scope)"](../../.planning/research/SUMMARY.md)
- [.planning/REQUIREMENTS.md §"V2-RANK-01"](../../.planning/REQUIREMENTS.md) — v2 deferral entry.
- [ADR 002: Vector Store](./002-vector-store.md) — bi-encoder retrieval lives here.
