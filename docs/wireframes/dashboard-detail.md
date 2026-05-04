# Wireframe: Dashboard — Trace Detail

ASCII wireframe + component inventory for the `/dashboard/traces/{trace_id}` route — the per-stage diagnostic view that turns a "bad answer" into a tractable bug. Header card surfaces the trace-level KPIs; a tab bar splits the body into Spans (waterfall), Payloads (full prompt/response inspector), and Feedback (rating + comment + diagnosis tag).

## Route

`/dashboard/traces/{trace_id}`

## Bound API Endpoints

- `GET /traces/{trace_id}` — full trace tree: `TraceDetailResponse{trace, spans, payloads}` per [api.md](../api.md).
- `POST /feedback` — invoked from the Feedback tab when an operator updates the diagnosis tag (Phase 5 FBCK-05 surface; the wireframe documents the UI seam).

The five canonical span names rendered in the waterfall come from [trace-schema.md](../trace-schema.md): `rag.request` (root), `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`, `rag.eval`.

## Component Inventory

| Region | Component | Library |
|--------|-----------|---------|
| Page header (back button + breadcrumb) | `Card` (variant=ghost) + `Button` (icon=ArrowLeft) | shadcn/ui |
| Header KPI card (query text + 4 badges) | `Card` + `Badge` x4 (latency_ms, cost, faithfulness, relevance) | shadcn/ui |
| Header rating badge | `Badge` (variant=positive/negative/ghost) | shadcn/ui |
| Tab bar | `Tabs` (tabs: Spans / Payloads / Feedback) | shadcn/ui |
| Span waterfall — root row (`rag.request`) | custom waterfall row (timeline bar + label + duration) | custom |
| Span waterfall — sync child rows (`rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`) | custom waterfall rows (indented; solid parent line) | custom |
| Span waterfall — async child row (`rag.eval`) | custom waterfall row (indented under root; **dashed** parent line indicating async parentage) | custom |
| Span attrs JSON viewer (per row, expanded) | `<pre>` block + `Button` (Copy) | custom |
| Payload tab — span selector | `Tabs` (one tab per span_id with an oversize payload entry) | shadcn/ui |
| Payload tab — JSON viewer | `<pre>` block (pretty-printed `SpanPayload.payload`) | custom |
| Feedback tab — rating | `Badge` (variant=positive/negative) + label | shadcn/ui |
| Feedback tab — comment | `Textarea` (read-only when feedback already submitted) | shadcn/ui |
| Feedback tab — diagnosis tag (Phase 5 FBCK-05) | `Select` items: Retrieval / PromptAssembly / LLM / CorpusStale / Other | shadcn/ui |
| Back to list | `Button` (variant=ghost) -> `/dashboard` | shadcn/ui |

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  [← Back]  Dashboard › Traces › 550e8400…                                │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  "How do I authenticate to the Anthropic Messages API?"          │    │
│  │  ⏱ 2810ms  💲 $0.00432  ⚖ faith 0.91  📐 rel 0.88   👍            │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  [ Spans ]  [ Payloads ]  [ Feedback ]                                   │
│                                                                          │
│  Spans tab — waterfall:                                                  │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ rag.request           ████████████████████████████  2810ms       │    │
│  │ ├─ rag.retrieve       ██░░                            160ms      │    │
│  │ ├─ rag.prompt_assemble  █░                              80ms     │    │
│  │ └─ rag.llm_call           ██████████████████░░       2540ms      │    │
│  │ ╎  (async; via ctx_snapshot — see /docs/sequence-diagrams.md)     │   │
│  │ └╌╌rag.eval                              ████░░       710ms      │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Click a row to expand attrs:                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ rag.retrieve.attrs                                       [Copy]  │    │
│  │ {                                                                │    │
│  │   "gen_ai.operation.name": "retrieval",                          │    │
│  │   "rag.retrieval.top_k": 5,                                      │    │
│  │   "rag.retrieval.score.mean": 0.81,                              │    │
│  │   "rag.retrieved_chunk_ids": ["11111…", "22222…", ...]           │    │
│  │ }                                                                │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

Payloads tab:

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  [ rag.retrieve ]  [ rag.prompt_assemble ]  [ rag.llm_call ]  [ rag.eval ]│
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  rag.llm_call.payload                                    [Copy]  │    │
│  │  {                                                               │    │
│  │    "request": { "model": "claude-sonnet-4-5-20250929", ... },    │    │
│  │    "response": { "content": [...], "usage": {...} }              │    │
│  │  }                                                               │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

Feedback tab:

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  Rating:  👍  (recorded 2026-05-04 04:15:55 UTC)                         │
│  Comment: "Cited the right chunks."                                      │
│                                                                          │
│  Diagnosis tag (Phase 5 FBCK-05):  [ — none — ▾ ]    [Save]              │
└──────────────────────────────────────────────────────────────────────────┘
```

## States

| State | What shows |
|-------|------------|
| Loading | Header KPI card shows shimmer; tab bar visible but disabled; waterfall renders 5 skeleton rows of decreasing length. |
| Empty | Trace not found (404 from `GET /traces/{trace_id}`): centered card "Trace not found — it may have been purged" with `Button` "Back to dashboard" navigating to `/dashboard`. |
| Error | Inline `Alert` (variant=destructive) above tab bar showing `error_code` + `message`; retry button re-issues the request. Tab content hidden until success. |
| Populated | Header KPI card filled; waterfall rendered with all spans returned by the API; clicking a row expands the `attrs` JSON viewer below it. Payloads tab populated with one inner tab per `payloads` map key (only spans with oversize payloads); Feedback tab populated from `trace.feedback_rating` and the matching `feedback` row. |
| Eval pending | `rag.eval` span has `ended_at == null` (still running): waterfall renders `rag.eval` row with a striped/animated bar; faithfulness and relevance badges in the header show `—` (em-dash); a small `Tooltip` on the badges reads "Eval still running — refresh in a moment." |

## Interactions

- **Click span row:** expands the row in-place to show the `attrs` JSON viewer; a second click collapses it. Multiple rows can be expanded simultaneously.
- **Switch to Payloads tab:** reads from the already-fetched `TraceDetailResponse.payloads` map (no extra fetch); inner `Tabs` selector picks which span's payload to render.
- **Switch to Feedback tab:** displays the `feedback_rating` + comment from the trace. The diagnosis-tag `Select` is a Phase 5 FBCK-05 surface — selecting a value and clicking `[Save]` calls `POST /feedback` with `{trace_id, rating: <existing>, diagnosis_tag: <selected>}`.
- **Back button:** navigates to `/dashboard` preserving filter state via the URL query string (so the operator returns to the same filtered list).
- **Refresh on eval-pending:** when the page detects `rag.eval.ended_at == null` on initial load, it polls `GET /traces/{trace_id}` once after 5 seconds; if still pending, it stops polling and leaves a manual "Refresh" `Button` near the eval row.
