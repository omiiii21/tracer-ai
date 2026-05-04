# Wireframe: Admin

ASCII wireframe + component inventory for the `/admin` route — corpus stats, re-ingest controls, and the chunking-config tuner. The Admin surface is the operator's lever for the **C** in RAG: change what's in the corpus or how it's chunked, then watch the dashboard's quality drift chart respond.

## Route

`/admin`

## Bound API Endpoints

- `GET /admin/corpus` — current corpus snapshot (`CorpusStatusResponse`): chunk_count, embedding_model, embedding_model_version, last_indexed_at, per-doc breakdown.
- `POST /admin/ingest` — trigger corpus re-ingest as a background job (`IngestRequest{urls? | source?}` → `IngestResponse{ingest_job_id, status}`).
- `PATCH /admin/chunking-config` — update `chunk_size` (100-4000) and/or `overlap` (0-500); applies on next ingest.

All schema constraints below match [api.md](../api.md) verbatim — the `Form` validators copy the same Pydantic constraints to client-side `<FormMessage>` for fast feedback.

## Component Inventory

| Region | Component | Library |
|--------|-----------|---------|
| Page header | `Card` (variant=ghost) | shadcn/ui |
| Corpus stats card (4 KPI tiles) | `Card` + `KpiCard` x4 | shadcn/ui + Tremor v3 |
| KPI tile — chunk_count | `KpiCard` | Tremor v3 |
| KPI tile — embedding_model | `KpiCard` (text variant) | Tremor v3 |
| KPI tile — embedding_model_version | `KpiCard` (text variant) | Tremor v3 |
| KPI tile — last_indexed_at | `KpiCard` (text variant) | Tremor v3 |
| Doc list table | `Table` (cols: doc_id, doc_section, chunk_count, last_indexed_at) | shadcn/ui |
| Re-index source picker | `Select` (`claude-docs` / `Custom URLs`) | shadcn/ui |
| Custom URL list | `Textarea` (newline-delimited URLs; visible only when `Custom URLs` selected) | shadcn/ui |
| Re-index trigger | `Button` (variant=primary) | shadcn/ui |
| Ingest progress | `Toast` (job_id + status `Badge`) | shadcn/ui |
| Chunking config form | `Form` (react-hook-form + Zod resolver) | shadcn/ui |
| chunk_size input | `Input` (type=number, min=100, max=4000) | shadcn/ui |
| overlap input | `Input` (type=number, min=0, max=500) | shadcn/ui |
| Save chunking config | `Button` (variant=primary) -> `PATCH /admin/chunking-config` | shadcn/ui |
| Field validation | `<FormMessage>` (variant=destructive on 422) | shadcn/ui |
| Save confirmation | `Toast` (variant=success) | shadcn/ui |

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  Admin                                  [Chat] [Dashboard] [Admin]       │
├──────────────────────────────────────────────────────────────────────────┤
│  Corpus                                                                  │
│  ┌────────────┐ ┌────────────────┐ ┌───────────────────┐ ┌────────────┐  │
│  │  Chunks    │ │ Embedding model│ │ Model version     │ │ Indexed    │  │
│  │   4,218    │ │ voyage-code-3  │ │ voyage-code-3@…   │ │ 22h ago    │  │
│  └────────────┘ └────────────────┘ └───────────────────┘ └────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────┐  ┌────────────────────────┐    │
│  │ Documents                            │  │ Re-index               │    │
│  ├──────────────────────────────────────┤  │ Source: [claude-docs ▾]│    │
│  │ doc_id            │ section │ chunks │  │                        │    │
│  ├──────────────────────────────────────┤  │ Custom URLs (one/line):│    │
│  │ claude/auth       │ auth    │   18   │  │ ┌──────────────────┐   │    │
│  │ claude/prompt-c…  │ prompt… │   42   │  │ │                  │   │    │
│  │ claude/tools      │ tools   │   31   │  │ └──────────────────┘   │    │
│  │ claude/files      │ files   │   24   │  │                        │    │
│  │ claude/vision     │ vision  │   19   │  │       [ Re-index ]     │    │
│  │ ...               │  ...    │  ...   │  │                        │    │
│  └──────────────────────────────────────┘  └────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ Chunking config                                                  │    │
│  │   chunk_size  [  900 ]  (100-4000)                               │    │
│  │   overlap     [  100 ]  (0-500)                                  │    │
│  │                                                       [ Save ]   │    │
│  │   ⚠ Applies on next ingest. Existing chunks unchanged.           │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│                                          ┌──────────────────────────┐    │
│                                          │ Toast: Ingest queued     │    │
│                                          │ job_id: cccc…0000  [⋯]   │    │
│                                          └──────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

## States

| State | What shows |
|-------|------------|
| Loading | Stats card shows shimmer for all 4 KPI tiles; doc list `Table` shows 5 skeleton rows; both forms render but submit buttons are disabled until `GET /admin/corpus` resolves. |
| Empty | When `chunk_count == 0` (corpus not yet ingested): KPI tiles show `0` / `—`; doc list `Table` shows centered hint "Corpus not yet ingested. Click Re-index to start."; chunking-config form remains usable so values can be set before the first ingest. |
| Error | Inline `Alert` (variant=destructive) at the top of each affected card. Form-level errors render as `<FormMessage>` adjacent to the offending input — Pydantic 422 errors map field-by-field (`chunk_size: must be ≤ 4000`). 503 `UPSTREAM_UNAVAILABLE` shows a top-of-page banner. |
| Populated | All 4 KPI tiles filled from `CorpusStatusResponse`; doc list rendered from `CorpusStatusResponse.docs`; both forms enabled. After a successful ingest trigger, the Toast pins to bottom-right with the `ingest_job_id` and `status`. |

## Interactions

- **Re-index — claude-docs source:** selecting `claude-docs` from the source `Select` and clicking `[Re-index]` calls `POST /admin/ingest` with `{source: "claude-docs"}`. On success, render the Toast with the returned `ingest_job_id` + status badge.
- **Re-index — custom URLs:** selecting `Custom URLs` reveals the `Textarea`; entering one URL per line and clicking `[Re-index]` calls `POST /admin/ingest` with `{urls: [...]}` (URL pattern validated client-side against `^https?://` to match `IngestRequest.urls` Pydantic constraint). At least one URL required.
- **Source XOR enforcement:** the `Select` enforces that exactly one of `urls` / `source` is sent — passing both (or neither) yields a 400 from the server per [api.md](../api.md). The UI prevents this by construction.
- **Save chunking config:** clicking `[Save]` calls `PATCH /admin/chunking-config` with `{chunk_size, overlap}`. Field-level validation runs first: `chunk_size ∈ [100, 4000]`, `overlap ∈ [0, 500]`, plus the semantic check `overlap < chunk_size` (otherwise the server returns 422 `UNPROCESSABLE_ENTITY`). On 2xx, show `Toast` "Config updated — applies on next index" and refresh the form's stored values from the response.
- **Both fields optional in PATCH:** the server accepts a PATCH with one field; the UI reflects this — only changed fields are sent in the body.
- **Reload corpus stats:** after a successful re-index Toast appears, poll `GET /admin/corpus` once after 30 seconds (or when the user clicks the Toast's "Refresh" link) to pull updated `chunk_count` and `last_indexed_at`.
