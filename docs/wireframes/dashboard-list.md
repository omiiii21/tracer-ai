# Wireframe: Dashboard — Trace List

ASCII wireframe + component inventory for the `/dashboard` route — the operator's primary lens onto the system. KPI strip + quality drift mini-chart on top, filter bar + paginated trace table below. Tremor v3 powers the chart and KPI cards; shadcn/ui powers the table, filters, and shell.

## Route

`/dashboard`

## Bound API Endpoints

- `GET /traces` — list traces with filters and cursor pagination. Query parameters per `TraceListQuery` in [api.md](../api.md): `query`, `since`, `until`, `feedback`, `min_faithfulness`, `max_latency_ms`, `limit`, `cursor`.

## Component Inventory

| Region | Component | Library |
|--------|-----------|---------|
| Page header (title + sub-nav) | `Card` | shadcn/ui |
| KPI tile — total traces (window) | `KpiCard` | Tremor v3 |
| KPI tile — avg latency_ms | `KpiCard` | Tremor v3 |
| KPI tile — avg faithfulness | `KpiCard` | Tremor v3 |
| KPI tile — total cost (USD) | `KpiCard` | Tremor v3 |
| Quality drift mini-chart | `AreaChart` (categories=[`faithfulness`, `relevance`], colors=[`emerald`, `blue`]) | Tremor v3 |
| Filter bar — query search | `Input` (placeholder "Search query text…") | shadcn/ui |
| Filter bar — time window | `Select` (Last hour / 24h / 7d / Custom…) | shadcn/ui |
| Filter bar — feedback | `Select` (All / 👍 only / 👎 only) | shadcn/ui |
| Filter bar — min_faithfulness | `Slider` (0.0–1.0, step 0.05) + numeric label | shadcn/ui |
| Filter bar — max_latency_ms | `Input` (type=number, optional) | shadcn/ui |
| Trace list | `Table` | shadcn/ui |
| Row: rating badge | `Badge` (variant=positive when rating=1, destructive when rating=-1, ghost when null) | shadcn/ui |
| Row: faithfulness | `Tooltip` over numeric value (Tooltip body shows source span_id) | shadcn/ui |
| Pagination | `Button` (variant=secondary, label "Load more") — uses `next_cursor` | shadcn/ui |
| Reset filters | `Button` (variant=ghost) — appears in Empty state | shadcn/ui |

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  Dashboard › Traces                       [Chat] [Dashboard] [Admin]     │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │  Traces    │ │ Avg latency│ │ Avg faith. │ │ Total cost │             │
│  │   1,284    │ │   2,910ms  │ │    0.81    │ │   $4.27    │             │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘             │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │  Quality drift (faithfulness · relevance) — last 7 days        │      │
│  │   1.0 ┤ ╮       ╮                                              │      │
│  │   0.8 ┤  ╲___╭──╯╲___                                          │      │
│  │   0.6 ┤              ╲___╭──                                   │      │
│  │   0.4 ┤                                                        │      │
│  │       └──────────────────────────────────────────────          │      │
│  │       Mon   Tue   Wed   Thu   Fri   Sat   Sun                  │      │
│  └────────────────────────────────────────────────────────────────┘      │
│                                                                          │
│  Filters: [Search…       ] [Last 24h ▾] [All ▾]  Faith ≥ [0.60] ━●━      │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ started_at        │ query              │ latency │ cost   │ ⚖   │ │  │
│  ├──────────────────────────────────────────────────────────────────┤    │
│  │ 04:14:31          │ How do I auth…     │ 2810ms  │ $0.004 │0.91│👍│  │
│  │ 04:13:02          │ What is prompt c…  │ 3120ms  │ $0.005 │0.42│👎│  │
│  │ 04:11:45          │ How do tools work? │ 2640ms  │ $0.004 │0.88│ —│  │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                  [ Load more ]           │
└──────────────────────────────────────────────────────────────────────────┘
```

## States

| State | What shows |
|-------|------------|
| Loading | KPI tiles render shimmer placeholders; `AreaChart` shows `<Skeleton>` of the same height; `Table` shows 5 skeleton rows; filter bar remains interactive (filters debounced and applied on response). |
| Empty | After filters applied with zero results: centered message "No traces match these filters" + `Button` (variant=ghost) "Reset filters" that clears all `TraceListQuery` parameters and re-fetches. KPI tiles show `0` / `—`; chart shows empty-state placeholder. |
| Error | Inline `Alert` (variant=destructive) above the table showing `error_code` + `message` from `ErrorResponse`; retry button re-issues `GET /traces` with the same params; KPI tiles and chart hide until success. |
| Populated | Filled KPI strip + `AreaChart` time-series + filter bar + `Table` with rows; `Load more` enabled when `next_cursor != null`, disabled when null. |

## Interactions

- **Click row:** navigates to `/dashboard/traces/{trace_id}` using the row's `trace_id`.
- **Change filter:** any filter change debounces 300ms then re-fetches `GET /traces` with the new `TraceListQuery`. Filter state is mirrored to the URL query string so the page is shareable.
- **Slider for `min_faithfulness`:** dragging the `Slider` updates the value label live; final value commits on release and triggers re-fetch.
- **Load more:** appends rows to the existing table using the response's `next_cursor` as the `cursor` parameter on the next call. Replaces the button with a spinner while in-flight.
- **Tooltip on faithfulness cell:** hovering reveals the source `span_id` (the `rag.eval` span). Clicking the cell navigates to `/dashboard/traces/{trace_id}` and pre-selects the Spans tab focused on `rag.eval`.
- **KPI / chart sync:** all KPI tiles and the `AreaChart` are computed from the **same** `TraceListQuery` window — when filters change, all four tiles + chart re-fetch together.
