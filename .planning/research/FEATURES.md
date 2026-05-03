# Feature Research

**Domain:** RAG chatbot with AI-native observability dashboard
**Researched:** 2026-05-04
**Confidence:** HIGH — sourced from official Context7 docs for LangSmith, Langfuse, Arize Phoenix, Braintrust, Helicone

---

## Research Basis

This feature landscape is derived from current documentation of the five production-grade LLM observability platforms named in the research brief: LangSmith (langchain-ai/langsmith-docs), Langfuse (langfuse/langfuse-docs), Arize Phoenix (arize-ai/phoenix + websites/arize_phoenix), Braintrust (websites/braintrust_dev), and Helicone (helicone/helicone). Every platform has been reviewed against the tracer-ai PRD §6 functional requirements.

Two product surfaces are separated throughout: the **Chat UI** (the chatbot end-user experience) and the **Observability Layer** (trace explorer, quality dashboard, eval loop — the product thesis).

---

## Surface 1: Chat UI

### Table Stakes

Features every LLM chat interface is expected to have. Missing any of these makes the chat feel unfinished.

| Feature | Why Expected | Complexity | PRD §6 | Notes |
|---------|--------------|------------|--------|-------|
| Text query input + streaming-style answer render | Base chat UX; users expect GPT-style conversation feel | LOW | §6.1 (non-streaming, which is fine for v1) | PRD explicitly defers streaming to v2; polled response is acceptable |
| Citation display — cited source chunks surfaced inline | Without this, a RAG answer is indistinguishable from a hallucination | MEDIUM | §6.1 — "cited source chunks (clickable to expand)" | Competitors show document title + excerpt; click-to-expand is the norm |
| Per-message cost + token display | Developers using the chatbot want to see overhead | LOW | §6.1 — "latency, token count, estimated cost" | Helicone and LangSmith both surface this per-request |
| Per-message latency display | Users calibrate expectations; operators spot slow retrievals | LOW | §6.1 | End-to-end latency is a standard field in all five platforms |
| Thumbs-up / thumbs-down feedback | Users expect to signal answer quality; it seeds eval data | LOW | §6.1 | Helicone, Langfuse, Braintrust all have rating feedback on individual responses |
| Free-text comment on thumbs-down | Captures qualitative failure mode alongside binary signal | LOW | §6.1 | Braintrust and Langfuse support comment fields on scores |
| Link from message to its trace | The core differentiator path — "see why this answer was produced" | LOW | §6.1 — "link to full trace" | None of the competitor platforms expose this directly in the chat UI; it's custom to tracer-ai |

### Differentiators (Chat Surface)

| Feature | Value Proposition | Complexity | PRD §6 | Notes |
|---------|-------------------|------------|--------|-------|
| Trace link inline in every chat message | Instant navigation from "bad answer" to diagnosis — no platform does this by default in their chat demo | LOW | §6.1 | LangSmith has a "View in LangSmith" link on traced runs but not surfaced to chat end-user |
| Per-chunk citation with similarity score visible | Shows retrieval quality signal to the user; makes the RAG mechanism transparent | MEDIUM | §6.1 — "clickable to expand" | Score display is non-standard; Langfuse shows chunk payloads in trace view, not chat view |

### Anti-Features (Chat Surface)

| Feature | Why Requested | Why Not | Alternative |
|---------|---------------|---------|-------------|
| Streaming token-by-token output | Feels faster and "alive" like ChatGPT | Adds SSE complexity to FastAPI + React; deferred explicitly in PRD §4.2 | Display full response with latency timer; ship streaming in v2 |
| Conversational memory across sessions | Users want history like a real assistant | Scope creep; changes the corpus and trace model significantly | Within-session history is fine for v1 |
| Multi-turn correction ("ignore that, try again") | Natural interaction pattern | Requires turn management and re-querying; unnecessary for portfolio demo | Single-turn is sufficient |

---

## Surface 2: Observability Layer

This is the product thesis. The five platforms were studied in detail. What follows categorizes their features by how common they are across the ecosystem.

### Table Stakes — Trace Explorer

Every platform (all five) provides these. Users of any observability product will expect them on day one.

| Feature | Why Expected | Complexity | PRD §6 | Notes |
|---------|--------------|------------|--------|-------|
| Trace list view — paginated table of all requests | Entry point for any debugging session | MEDIUM | §6.2 — "trace list view" | All five platforms have this. Columns: time, query, latency, cost, score |
| Filter/search traces by time range | Can't debug without scoping to "when the issue started" | LOW | §6.2 — "filterable by time range" | Arize Phoenix REST API supports `start_time`/`end_time` filters; Langfuse has date picker |
| Filter traces by feedback rating | Find thumbs-down traces without scrolling | LOW | §6.2 — "filter by feedback rating" | LangSmith has `feedback_stats` on every run object; Langfuse supports score-based filtering |
| Filter traces by quality score threshold | Find low-faithfulness traces without manual review | LOW | §6.2 — "filter by faithfulness score" | Langfuse supports score filtering; Phoenix supports annotation-based filtering |
| Trace detail view — single request drill-down | The core debugging action: see exactly what happened | HIGH | §6.2 — "trace detail view" | All five platforms have this |
| Span waterfall / timing breakdown | "Which stage was slow?" is a core question | MEDIUM | §6.2 — "timing waterfall" | Langfuse, Phoenix, LangSmith all show parent-child span timing as a Gantt/waterfall |
| Full prompt payload inspector (what was sent to LLM) | "Did the prompt template break?" requires seeing the actual prompt | LOW | §6.2 — "full prompt, full response" | All five platforms store and display full input/output payloads |
| Full response payload inspector | See what the model returned verbatim | LOW | §6.2 | Same as above |
| Retrieved chunk list with similarity scores per trace | "Did the retriever return wrong chunks?" — the most common RAG failure | MEDIUM | §6.2 — "retrieved chunks + scores" | Phoenix has RETRIEVER span kind with document attributes; LangSmith has `run_type="retriever"` with document output |
| Token count and cost per trace | Understand spend at request level | LOW | §6.2 — implied via "cost" in §6.1 | LangSmith run object has `total_tokens`, `total_cost`, `prompt_cost`, `completion_cost` fields; Langfuse metrics API returns `totalCost` per day |
| Span attributes display (model, embedding model, retriever name) | Contextualizes what component produced each span | LOW | §6.2 / §8 trace schema | OTel GenAI conventions name these: `gen_ai.request.model`, `gen_ai.usage.input_tokens` |

### Table Stakes — Quality Dashboard

These are present on at least three of the five platforms and are expected by operators running any AI system in production.

| Feature | Why Expected | Complexity | PRD §6 | Notes |
|---------|--------------|------------|--------|-------|
| Time-series chart of request volume | Baseline traffic monitoring; detect usage spikes or drops | LOW | §6.2 — "request volume" | LangSmith prebuilt dashboards include trace counts; Langfuse metrics API has `countTraces` per day |
| Time-series chart of p50/p95 latency | Performance regression detection | MEDIUM | §6.2 — "p50/p95 latency" | LangSmith has latency alerting; Braintrust SQL API shows percentile functions |
| Time-series chart of cost (daily/weekly) | Budget awareness and cost drift detection | LOW | §6.2 — "total cost" | Langfuse metrics API `totalCost`; LangSmith `completion_cost` aggregations |
| Time-series chart of faithfulness score mean | Semantic quality drift — the core AI-native metric | MEDIUM | §6.2 — "faithfulness score distribution" | Langfuse supports score aggregations; LangSmith has feedback score alerting; Braintrust has `avg(scores.Factuality)` SQL query pattern |
| User feedback ratio chart (thumbs-down rate over time) | Leading indicator of quality problems before they're diagnosed | LOW | §6.2 — "manual-feedback ratio" | Helicone, LangSmith, Langfuse all track user feedback per request |
| Configurable time window (24h / 7d / 30d) | Default 24h is too narrow for weekly patterns; 30d shows trends | LOW | §6.2 — "configurable time window" | All platforms have this |
| Score distribution histogram (faithfulness spread) | Distinguish "mostly good with outliers" from "uniformly mediocre" | MEDIUM | §6.2 — "faithfulness score distribution" | Langfuse has score distribution views; LangSmith prebuilt dashboards |

### Table Stakes — Evaluation & Feedback

| Feature | Why Expected | Complexity | PRD §6 | Notes |
|---------|--------------|------------|--------|-------|
| LLM-as-judge evaluation (faithfulness + relevance) | Manual review of every trace is impossible at scale; auto-scoring is baseline | HIGH | §6.2 + §6.3 — "LLM-as-judge async" | Phoenix has built-in `FaithfulnessEvaluator`; Langfuse supports RAGAS-style eval; LangSmith uses `openevals` library with `create_llm_as_judge` |
| Async eval pipeline (does not block user request) | User latency must not degrade because of evaluation overhead | MEDIUM | PRD §7 — "trace write must not add > 100ms" | All five platforms run evals out-of-band; Braintrust explicitly states "online scoring runs asynchronously without affecting latency" |
| Scores attached to trace / span objects | Evaluation results must be queryable per-trace | LOW | §6.2 | Langfuse `create_score(trace_id=...)` is the standard pattern; LangSmith `feedback_stats` on run object |
| Manual user feedback ingestion (thumbs rating) | Human signal is ground truth for eval calibration | LOW | §6.1 + §6.2 | Helicone `POST /v1/request/{id}/feedback`; Langfuse `score_trace(name="user-feedback", value=1)`; all five support this |

### Table Stakes — Alerting

| Feature | Why Expected | Complexity | PRD §6 | Notes |
|---------|--------------|------------|--------|-------|
| Threshold-based alerts on quality metrics | "Quality dropped and nobody noticed" is the nightmare scenario | MEDIUM | §6.2 — "alert thresholds configurable" | LangSmith supports alerting on Feedback Score, Latency, Error Rate; Braintrust supports alerts on quality and error rate |

### Differentiators — What tracer-ai Does That Competitors Don't Make Easy

These are features that exist as primitives in the platforms but are not surfaced as a coherent first-class workflow. tracer-ai's thesis is to make these the default experience.

| Feature | Value Proposition | Complexity | PRD §6 | Notes |
|---------|-------------------|------------|--------|-------|
| Per-stage diagnosis UI — explicit "which stage failed?" framing | Most platforms show a waterfall but don't label the failure source. tracer-ai surfaces "retriever returned wrong chunks" vs "LLM ignored right chunks" as distinct diagnoses | HIGH | PRD §2 — core problem statement | Phoenix and LangSmith both have RETRIEVER/LLM span kinds but leave interpretation to the user; no platform renders a "diagnosis summary" |
| Bad-answer queue — dedicated review workflow for flagged traces | All platforms have annotation queues, but none tie thumbs-down + auto-eval-below-threshold into a single triage queue out of the box | MEDIUM | §6.2 — "bad-answer queue: mark resolved / promote to regression set" | Langfuse Annotation Queues (Oct 2024) are the closest: bulk-add traces, structured review; but they're general-purpose, not RAG-diagnosis-specific |
| "Promote to regression set" action in the review queue | Turns production failures directly into test cases — closes the observability → improvement loop | MEDIUM | §6.3 + §6.4 | Braintrust mentions "surface real user interactions that can be used as new test cases" but no first-class promote action in UI; LangSmith has `in_dataset` flag on runs |
| Regression CLI with per-query pass/fail + report | Runnable from CI; maps to `tracer-ai eval`; enables "fix corpus → rerun → confirm regression gone" workflow | MEDIUM | §6.3 — "eval CLI" | LangSmith has dataset + experiment runner; Langfuse has `dataset.run_experiment()`; none expose this as a first-class CLI for single-user local use |
| OTel GenAI semantic conventions in trace schema | Span attributes portable to any OTel backend — escape hatch if this project grows | MEDIUM | PRD §8 trace schema | Phoenix uses OpenInference (its own OTel extension); Langfuse accepts OTel via OTLP endpoint (added Feb 2025); LangSmith uses proprietary format. tracer-ai baking OTel in from day one is a genuine differentiator for portability |
| Chunk-level scoring per retrieval event | Most platforms score the final output; tracer-ai can score each individual retrieved chunk's contribution | HIGH | Implied by span schema `rag.retrieve` events with per-chunk scores | Phoenix `DocumentRelevanceEvaluator` evaluates individual documents — this is the closest analogue; LangSmith shows chunk payloads but does not score per-chunk by default |
| Corpus admin UI + re-index from dashboard | No observability platform manages the document corpus — tracer-ai owns the full loop including corpus quality | HIGH | §6.4 — Corpus Admin UI | None of the five platforms have a corpus admin view; they observe LLM calls, not the underlying retrieval corpus |

### Differentiators — Eval Dimension

| Feature | Value Proposition | Complexity | PRD §6 | Notes |
|---------|-------------------|------------|--------|-------|
| Pairwise experiment comparison (chunk size A vs B) | Shows which retrieval config produces better faithfulness on the same query set | HIGH | PRD §10 GSD-OPEN-6 | Langfuse has `dataset.run_experiment()` with chunk_size parameter; LangSmith has `evaluate(["exp-1","exp-2"])` pairwise; Braintrust has experiment metadata; v2 feature for tracer-ai |
| Retrieval-specific eval metrics: context recall, context precision | Beyond faithfulness: "did the retriever surface all relevant chunks?" and "was any retrieved chunk irrelevant?" | HIGH | Not in PRD §6 | RAGAS defines context_recall and context_precision; Phoenix has DocumentRelevanceEvaluator; v2 additions |

### Anti-Features (Observability Layer)

Features to explicitly not build in v1. Each is tempting but either scope-busting or unnecessary for the portfolio thesis.

| Feature | Why Requested | Why Not | What to Do Instead |
|---------|---------------|---------|-------------------|
| Real-time streaming trace updates (websocket push) | Dashboard feels "live" | Adds websocket complexity; polling on 5s interval is sufficient for local single-user demo | Poll on interval in React dashboard |
| Multi-tenant auth / user isolation | "Production ready" | Explicitly non-goal in PRD §4.2; single-user local deployment | Document as v1.5 axis in an ADR (GSD-OPEN-9) |
| Custom alert notification channels (email, Slack, PagerDuty) | Complete alerting story | Requires outbound integrations; overkill for local demo | In-UI alert display is sufficient |
| Model comparison A/B testing framework | Interesting eval feature | Out of scope; requires multiple LLM adapters active simultaneously | Document as future experiment axis |
| Prompt version management with rollback UI | LangSmith and Langfuse both have this | Adds a full CRUD surface for prompts; not part of tracer-ai's thesis | Store prompt templates as config files; version via git |
| Query rewriting / query expansion pipeline | Can improve retrieval quality | Adds a pipeline stage and eval complexity; deferred in PRD §10 GSD-OPEN-7 | Ship v1 without; add as config flag after baseline |
| Multi-modal tracing (image inputs, audio) | Comprehensive | Explicitly non-goal PRD §4.2 | Not applicable for Claude API text docs corpus |
| Synthetic data generation for eval | Some platforms auto-generate QA pairs | Requires separate LLM calls for synthetic generation; manual curated set is better for portfolio quality signal | Use 30 hand-labeled traces for calibration (GSD-OPEN-8) |

---

## Feature Dependencies

```
[Chat UI — query/answer]
    └──requires──> [RAG pipeline — retrieve/assemble/llm]
                       └──requires──> [Corpus — indexed docs]

[Trace detail view]
    └──requires──> [Span emission — tracer core]
                       └──requires──> [Chat UI — query/answer]

[LLM-as-judge eval]
    └──requires──> [Trace detail view (trace_id to attach scores)]

[Quality dashboard — faithfulness time-series]
    └──requires──> [LLM-as-judge eval]
    └──requires──> [Trace list view]

[Bad-answer queue]
    └──requires──> [User feedback (thumbs-down)]
    └──requires──> [LLM-as-judge eval (auto-eval threshold)]

[Regression CLI]
    └──requires──> [Bad-answer queue (promote action)]
    └──requires──> [LLM-as-judge eval (scoring the regression run)]

[Corpus admin UI]
    └──enhances──> [Trace detail view] (re-indexing changes what chunks retriever returns)
    └──requires──> [Corpus — indexed docs]

[Per-stage diagnosis framing]
    └──requires──> [Trace detail view]
    └──enhances──> [Bad-answer queue] (diagnosis labels the failure category)
```

### Dependency Notes

- **Span emission requires chat pipeline to exist first:** Phase 1 builds the pipeline; Phase 2 wraps it in spans. No span without a pipeline.
- **Quality dashboard requires both user feedback and LLM-as-judge:** Dashboard charts are meaningless until Phase 3 populates scores.
- **Bad-answer queue requires both feedback AND auto-eval:** The queue is `feedback=down OR faithfulness < threshold`. Both sources needed.
- **Regression CLI requires bad-answer queue promote action:** The CLI's "curated set" is seeded by the queue; the queue must ship first.
- **Corpus admin conflicts with hardcoded chunk config:** Once admin UI exposes chunking parameters, the pipeline must read config dynamically, not from constants.

---

## MVP Definition

### Launch With (v1)

| Feature | Surface | Why Essential |
|---------|---------|---------------|
| Working chat with cited answers | Chat | The test bed; without it nothing else is demoable |
| Trace list view with filter by time | Trace Explorer | Entry point for every debugging session |
| Trace detail view: spans + waterfall + chunk list + prompt + response | Trace Explorer | The core thesis: see exactly which stage failed |
| LLM-as-judge faithfulness + relevance score per trace (async) | Eval | Without scores, the dashboard has no quality signal |
| Thumbs-down feedback + free-text comment | Chat / Feedback | Seeds the bad-answer queue |
| Bad-answer queue (thumbs-down OR faithfulness < threshold) | Trace Explorer | Closes the loop: bad answer → diagnose → fix |
| "Promote to regression set" action | Bad-answer queue | Enables CLI eval of specific failures |
| Regression CLI (`tracer-ai eval`) | CLI | Validates fixes; doubles as integration test |
| Quality dashboard: latency, cost, faithfulness, feedback ratio time-series | Dashboard | Shows drift, not just outages |
| Corpus admin: view chunks, re-index with config | Admin | Makes "stale corpus" scenario demonstrable and fixable |

### Add After Validation (v1.x)

| Feature | Trigger for Adding |
|---------|-------------------|
| Per-chunk relevance scoring (was each retrieved chunk individually useful?) | After baseline eval metrics show retrieval as the bottleneck |
| Pairwise chunking experiment comparison | After first corpus tuning cycle reveals ambiguity in which chunk size is better |
| Auth + single-user login | When local demo is shared with external reviewers |
| Trace JSON export button | When demoing to engineers who want to integrate with their own tooling |
| Cost widget on dashboard (cumulative spend view) | After deploying to a hosted environment with real cost exposure |

### Future Consideration (v2+)

| Feature | Why Defer |
|---------|-----------|
| Streaming responses in chat | Adds SSE/websocket layer; non-goal in PRD §4.2; not needed for observability demo |
| Prompt version management UI | LangSmith/Langfuse solve this; adds full CRUD surface not needed for portfolio thesis |
| Multi-tenant support | Scope-busting; cloud deployment is a separate product evolution axis (GSD-OPEN-9) |
| Synthetic eval data generation | Requires quality calibration before automation adds value |
| Re-ranking pipeline | Add only after baseline metrics confirm retrieval quality gap (GSD-OPEN-7) |
| Context recall / context precision metrics | RAGAS-tier eval; requires reference corpus annotations; adds significant eval complexity |

---

## Feature Prioritization Matrix

| Feature | User Value | Build Cost | Priority |
|---------|------------|------------|----------|
| Trace detail view (waterfall + payloads) | HIGH | MEDIUM | P1 |
| LLM-as-judge faithfulness + relevance (async) | HIGH | HIGH | P1 |
| Bad-answer queue (thumbs-down + auto-eval filter) | HIGH | MEDIUM | P1 |
| Chat UI with citations + feedback | HIGH | MEDIUM | P1 |
| Quality dashboard time-series (latency, cost, faithfulness) | HIGH | MEDIUM | P1 |
| Trace list view (filter/search) | HIGH | LOW | P1 |
| Regression CLI | MEDIUM | MEDIUM | P1 |
| Corpus admin UI (view + re-index) | MEDIUM | MEDIUM | P1 |
| Per-chunk similarity score display in trace detail | MEDIUM | LOW | P1 |
| Promote-to-regression-set action | MEDIUM | LOW | P1 |
| Cost widget (cumulative dashboard) | LOW | LOW | P2 |
| Trace JSON export | LOW | LOW | P2 |
| Pairwise experiment comparison | MEDIUM | HIGH | P3 |
| Per-chunk relevance scoring | MEDIUM | HIGH | P3 |
| Streaming chat responses | LOW | MEDIUM | P3 |

---

## Cross-Reference: PRD §6 vs Gap Analysis

| PRD §6 Feature | In PRD? | In Competitor Platforms? | Gap / Note |
|----------------|---------|--------------------------|------------|
| Chat: query + cited answer | Yes §6.1 | Standard for RAG demos | No gap |
| Chat: thumbs-up/down + comment | Yes §6.1 | Helicone, Langfuse, Braintrust | No gap |
| Chat: latency/token/cost display | Yes §6.1 | LangSmith, Langfuse, Helicone | No gap |
| Chat: link to trace | Yes §6.1 | Not standard in chat UI of any platform | tracer-ai differentiator |
| Dashboard: request volume, p50/p95 latency | Yes §6.2 | LangSmith prebuilt dashboards, Braintrust | No gap |
| Dashboard: faithfulness score distribution | Yes §6.2 | Langfuse score views, LangSmith | No gap |
| Dashboard: configurable time window | Yes §6.2 | All platforms | No gap |
| Dashboard: manual-feedback ratio | Yes §6.2 | LangSmith feedback_stats, Helicone | No gap |
| Trace list: filter by query text | Yes §6.2 | Langfuse, LangSmith full-text search | No gap |
| Trace list: filter by feedback / score / latency bucket | Yes §6.2 | Langfuse, Phoenix REST API | No gap |
| Trace detail: span waterfall with payloads | Yes §6.2 | All five platforms | No gap |
| Trace detail: per-stage spans with RAG-specific attrs | Yes §6.2 / §8 | Phoenix RETRIEVER kind, LangSmith `run_type=retriever` | tracer-ai's OTel-aligned schema is more explicit |
| Bad-answer queue: thumbs-down OR auto-eval below threshold | Yes §6.2 | Langfuse annotation queues (closest), but not combined with auto-eval threshold out of the box | tracer-ai differentiator |
| Bad-answer queue: promote to regression set | Yes §6.2 | LangSmith `in_dataset=true`, Braintrust mentions in docs but no first-class promote UI | tracer-ai differentiator |
| Eval CLI: curated query set, pass/fail report | Yes §6.3 | Langfuse `dataset.run_experiment()`, LangSmith experiment runner | All are SDK-based; tracer-ai's CLI is a first-class binary (`tracer-ai eval`) |
| Corpus admin: upload/re-index, view chunk count | Yes §6.4 | None of the five platforms | tracer-ai differentiator — no competitor manages the corpus |
| Corpus admin: chunking config form | Yes §6.4 | None of the five platforms | tracer-ai differentiator |
| Corpus admin: retrieval test queries | Yes §6.4 | None of the five platforms | tracer-ai differentiator |
| LLM-as-judge per trace (async) | Yes §6.2 + §8 | Phoenix FaithfulnessEvaluator, LangSmith LLM-judge, Langfuse RAGAS integration | No gap — all platforms support this; tracer-ai implements natively with Haiku |
| **IDENTIFIED GAP: Per-stage failure classification** | No — implied by PRD §2 problem statement | No platform surfaces this as a UI feature | tracer-ai could add a "diagnosis tag" to each trace detail: "Retrieval failure / Prompt failure / Corpus staleness / LLM hallucination" — this is a key differentiator worth surfacing in requirements |
| **IDENTIFIED GAP: Alert threshold configurable in UI** | Mentioned in §6.2 "alert thresholds configurable" but no endpoint in PRD §6.4 API contract | LangSmith has alerting UI; Braintrust has alert setup | PRD does not specify how thresholds are set (config file vs. UI form) — requirements should lock this |

---

## Competitor Feature Analysis

| Feature | LangSmith | Langfuse | Arize Phoenix | Braintrust | Helicone | tracer-ai approach |
|---------|-----------|----------|---------------|------------|----------|--------------------|
| Trace list + filter | Yes | Yes | Yes (REST + UI) | Yes (CLI + UI) | Yes | Custom React table |
| Span waterfall | Yes | Yes | Yes | Yes | Partial (sessions) | Custom React component |
| Full payload inspector | Yes | Yes | Yes | Yes | Yes | Inline expandable JSON |
| Retrieved chunk list in trace | Yes (retriever run) | Yes (span output) | Yes (RETRIEVER span) | Yes (span log) | No (proxy-only) | First-class span events with scores |
| LLM-as-judge eval | Yes (openevals) | Yes (RAGAS integration) | Yes (built-in FaithfulnessEvaluator) | Yes (autoevals) | No | Custom Haiku judge |
| Dataset / regression set | Yes (Dataset) | Yes (Dataset) | Yes (Dataset) | Yes (Dataset) | No | Regression case file + CLI |
| Annotation / review queue | Yes (annotation queues) | Yes (annotation queues Oct 2024) | Yes (annotations) | Yes (human review) | No | Bad-answer queue (custom) |
| Promote trace → test case | Yes (in_dataset flag) | Yes (add to dataset) | Yes (add to dataset) | Mentioned in docs | No | "Promote to regression set" action |
| Prompt management + versioning | Yes (full feature) | Yes (full feature) | Yes | Yes | No | Not in scope (use config files) |
| Cost tracking | Yes (per-run) | Yes (daily metrics API) | Partial | Yes (metrics) | Yes (primary feature) | Per-trace + dashboard aggregate |
| Alert thresholds | Yes (3 metrics) | No (as of research date) | No | Yes | No | Config-driven threshold for bad-answer queue |
| Corpus / document admin | No | No | No | No | No | tracer-ai exclusive feature |
| OTel export | No (proprietary) | Yes (OTLP endpoint, Feb 2025) | Yes (OpenInference = OTel extension) | No | No | OTel GenAI conventions in schema; exporters/ dir |
| Chat UI | No | No | No | No | No | tracer-ai exclusive (chatbot as test bed) |

---

## Sources

- LangSmith: `/langchain-ai/langsmith-docs` via Context7 — trace format, run object fields, annotation queues, alerting (3 metric types: Error Rate, Feedback Score, Latency), prebuilt dashboards, `run_type="retriever"` convention
- Langfuse: `/langfuse/langfuse-docs` via Context7 — scoring API, annotation queues (Oct 2024 release), metrics API (daily cost/token/trace count), prompt management with label/version, RAGAS integration, OTel OTLP support (Feb 2025)
- Arize Phoenix: `/websites/arize_phoenix` + `/arize-ai/phoenix` via Context7 — RETRIEVER span kind, FaithfulnessEvaluator, DocumentRelevanceEvaluator, REST API for traces/spans with filter params, OTel OpenInference conventions
- Braintrust: `/websites/braintrust_dev` via Context7 — online scoring (async, production), SQL metrics API with percentile functions, human review, experiment comparison, bt view CLI
- Helicone: `/helicone/helicone` via Context7 — proxy-based approach, per-request cost/latency, user feedback endpoint (`POST /v1/request/{id}/feedback`), sessions for multi-step tracing, custom property headers
- tracer-ai PRD: `tracer-ai-foundation-prd.md` — functional requirements §6, non-goals §4.2, trace schema §8, open questions §10

---
*Feature research for: RAG chatbot with AI-native observability*
*Researched: 2026-05-04*
