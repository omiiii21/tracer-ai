# ADR 005: Observability Strategy — Custom Tracer with OTel GenAI Attribute Names

## Status

Accepted — 2026-05-04

## Context

tracer-ai's product thesis is that **every RAG pipeline stage is instrumented as a structured trace** — and that the per-stage trace is the diagnosis surface that distinguishes "retriever returned wrong chunks" from "LLM ignored the right chunks" from "corpus was stale". Existing observability frameworks (Langfuse, Phoenix, OpenLLMetry, Helicone) abstract the very stages we want to expose, defeating the learning and demonstration objective. At the same time, throwing away OpenTelemetry naming would lose future portability — every backend (Datadog, Honeycomb, Langfuse-as-export-target, OTel collectors) speaks OTel attribute names.

The OpenTelemetry GenAI semantic conventions are at **Development / Experimental stability** as of 2026: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens` are defined; well-known `operation.name` values include `chat`, `embeddings`, `retrieval`, `execute_tool`, `invoke_agent`. Retrieval spans support `gen_ai.retrieval.documents` and `gen_ai.retrieval.query.text` as Opt-In attributes. Crucially, **`gen_ai.system` is DEPRECATED in the current spec** in favor of `gen_ai.provider.name` (= `"anthropic"` for our calls).

This decision resolves [GSD-OPEN-5](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **Custom tracer + OTel GenAI attribute names as constants (chosen):** Span dataclasses we own end-to-end; OTel-compatible *naming* without OTel-SDK *runtime semantics*. Future export to OTel collectors is a separate module under `tracer/exporters/otel/` that maps our spans to OTel `ReadableSpan` objects.
- **`opentelemetry-sdk` runtime (rejected):** Heavy dependency; span-lifecycle abstraction (TracerProvider, SpanProcessor, etc.) obscures the very pipeline stages we want to expose. The SDK's value is the export plumbing, which we can adopt later when needed.
- **Langfuse / Phoenix as primary backend (rejected):** Black-box trace storage defeats the learning objective. We can export TO Langfuse later — we cannot build it FROM Langfuse.
- **RAGAS as a library (rejected):** Excellent prompt patterns (we adopt those — see [ADR 008](./008-judge-prompts-thresholds.md)), but the library abstracts the pipeline stages. Use the prompts, not the abstraction.

## Decision

tracer-ai will implement a **custom tracer** in `tracer_ai/tracer/`. Span dataclasses use **OTel GenAI attribute names** as Python string constants centralized in `tracer_ai/tracer/span.py` — for example, `GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"`, `GEN_AI_OPERATION_NAME = "gen_ai.operation.name"`, `GEN_AI_REQUEST_MODEL = "gen_ai.request.model"`, `GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"`.

We use **`gen_ai.provider.name`** with the value `"anthropic"`. **`gen_ai.system` is DEPRECATED in the OTel GenAI spec and we do NOT emit it.** A custom `rag.*` namespace covers RAG-specific attributes that the OTel GenAI spec does not define (e.g., `rag.retrieval.score.mean`, `rag.eval.faithfulness`, `rag.eval.relevance`, `rag.failure_diagnosis_tag`).

Because the OTel GenAI spec is at Development stability and naming may change, the centralized-constants file IS the migration mitigation: if a name moves, we change one constant and downstream code follows. A future `tracer/exporters/otel/` module can map our `Span` dataclasses to OTel `ReadableSpan` objects without touching pipeline code — naming compatibility makes that mapping a near-identity transform.

## Consequences

**Positive:**
- No `opentelemetry-sdk` runtime dependency in v1; lean import graph and full visibility into span emission.
- Single grep finds every attribute name in use — schema drift is caught at code-review time.
- OTel-compatible naming positions us for future export to OTel collectors, Datadog, Honeycomb, or Langfuse-as-export-target with minimal wiring.
- We own span lifecycle; the trace-write hot path is bounded by our own queue mechanics ([ADR 004](./004-trace-storage.md) constraints), not the OTel SDK's.

**Negative:**
- We must track OTel GenAI spec changes manually. Mitigation: centralized constants file + an Architecture Decision review when a Stable release lands.
- The `tracer/exporters/otel/` module is unimplemented in v1 (deferred). External backends cannot consume our traces directly until that module ships.

**Mandatory follow-ups:**
- [ ] All `gen_ai.*` and `rag.*` attribute names defined as Python constants in `tracer_ai/tracer/span.py` (Phase 4 TRCR-01).
- [ ] Document the **`gen_ai.system` DEPRECATION** explicitly in `/docs/trace-schema.md` so future contributors do not accidentally re-introduce it (per D-22).
- [ ] Re-review this ADR when the OTel GenAI spec reaches Stable.

## References

- [.planning/research/ARCHITECTURE.md §"OTel GenAI Semantic Conventions — Status as of 2026"](../../.planning/research/ARCHITECTURE.md)
- [.planning/research/PITFALLS.md §"Pitfall #9"](../../.planning/research/PITFALLS.md) — OTel attribute drift and centralized-constants mitigation.
- OpenTelemetry GenAI semantic conventions (Development stability) — cited via Context7 in `.planning/research/ARCHITECTURE.md`.
- [ADR 004: Trace Storage](./004-trace-storage.md) — defines the persistence target for spans authored under this strategy.
