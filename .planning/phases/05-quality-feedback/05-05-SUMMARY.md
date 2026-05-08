---
phase: 05-quality-feedback
plan: 05
subsystem: api
tags: [timeseries, generate-series, percentile-cont, adaptive-bucketing, leftjoin, connectnulls-false, dash-01, dash-02, dash-03, dash-04, dash-05, dash-06, fbck-03, fbck-06, d-5-17, d-5-07]

# Dependency graph
requires:
  - phase: 04-tracer-trace-explorer
    plan: 04
    provides: "PostgresTraceStore + TraceListFilters + list_traces parameterized query + cursor pagination + GET /traces route"
  - phase: 04-tracer-trace-explorer
    plan: 01
    provides: "traces.faithfulness / latency_ms / estimated_cost_usd / feedback_rating denormalized columns"
provides:
  - "GET /traces/timeseries?window={1h|24h|7d|30d} adaptive-bucket aggregate endpoint (DASH-01..04)"
  - "TimeseriesBucket + TimeseriesResponse Pydantic v2 strict-mode schemas (extra=forbid)"
  - "PostgresTraceStore.timeseries(window) — generate_series + LEFT JOIN preserves empty-bucket NULL rows; PERCENTILE_CONT(0.5/0.95) latency; AVG faithfulness; ratio CASE feedback_down"
  - "GET /traces extended with max_faithfulness query param (FBCK-03 — judge-flagged tab semantics: faithfulness < threshold AND IS NOT NULL)"
  - "GET /traces extended with sort_by Literal[created_at_desc | faithfulness_asc] (FBCK-06 — bad-answer queue lowest-first sort)"
  - "TraceListFilters dataclass extended with max_faithfulness + sort_by"
affects: [05-07 frontend (consumes /traces/timeseries for QualityCharts and /traces?max_faithfulness+sort_by for Queue Judge-flagged tab)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Adaptive bucketing via _BUCKET_BY_WINDOW dict mapping route Literal -> (date_trunc unit, generate_series interval, since interval). Hard-coded -- user input never enters the SQL string (T-05-05-01 mitigation)."
    - "Empty-bucket preservation: WITH buckets AS (generate_series(...)) SELECT ... FROM buckets LEFT JOIN trace_data USING (bucket). NULL aggregates render as connectNulls=false gaps in the frontend Tremor chart (D-5.07)."
    - "Special-case 5-min bucketing via subtraction trick (date_trunc supports only natural intervals like minute/hour/day, not 5-minute)."
    - "Literal-validated sort_by + Literal-validated window prevent SQL injection by forcing the ORDER BY / interval expression to come from a hard-coded set (T-05-05-02 / T-05-05-03 mitigations)."
    - "GET /traces/timeseries route registered BEFORE GET /traces/{trace_id} so the literal 'timeseries' path segment doesn't get parsed as a UUID."
    - "WHERE latency_ms IS NOT NULL excludes in-flight traces from aggregates (D-4.18 invariant preserved; T-05-05-07 mitigation)."

key-files:
  created:
    - "tests/integration/test_timeseries_endpoint.py — 8 integration tests TS1-TS8 (empty database, sparse active buckets, NULL faithfulness/feedback semantics, p95 round-trip, bucket count per window, 422 on bad window, in-flight exclusion)"
  modified:
    - "tracer_ai/api/traces.py — GET /traces/timeseries route + extended GET /traces with max_faithfulness + sort_by"
    - "tracer_ai/api/schemas.py — TimeseriesBucket + TimeseriesResponse Pydantic v2 schemas"
    - "tracer_ai/tracer/store.py — PostgresTraceStore.timeseries(window) + extended list_traces with max_faithfulness + sort_by; TraceListFilters extended"
    - "tests/test_api_schemas.py — 6 schema tests (TimeseriesBucket parse + extra=forbid + window Literal + request_count >= 0)"
    - "tests/integration/test_traces_api.py — 8 integration tests EX1-EX8 (filter/sort/422-validation/cursor-compat for the new params)"
    - "docs/api.md — GET /traces section gets max_faithfulness + sort_by; new GET /traces/timeseries section between GET /traces and GET /traces/{trace_id}"
---

# Plan 05-05 — Timeseries endpoint + extended /traces filters

## What was built

Two backend extensions that together satisfy DASH-01..06 chart needs and FBCK-03 / FBCK-06 queue tab needs:

1. **`GET /traces/timeseries?window={1h|24h|7d|30d}`** returns adaptive-bucket aggregates: `latency_p50`, `latency_p95`, `cost_sum`, `faithfulness_mean` (NULL when no rag.eval scores in bucket), `feedback_down_ratio` (NULL when no rated traces in bucket), `request_count`. Empty buckets render as rows with NULL aggregates and `request_count=0` — load-bearing for the frontend Tremor `connectNulls={false}` rendering (D-5.07): visually distinct from low-faithfulness scores.

2. **`GET /traces` extended** with two new query params:
   - `max_faithfulness` — Annotated `[0.0, 1.0]` filter; rows with NULL faithfulness are EXCLUDED when this filter is set (FBCK-03 semantic: "judge has not yet scored" is not "judge-flagged").
   - `sort_by` — `Literal["created_at_desc", "faithfulness_asc"]`; default preserves Phase 4 ordering; `faithfulness_asc` orders `faithfulness ASC NULLS LAST, started_at DESC, id DESC` for the FBCK-06 Judge-flagged tab.

## Tasks completed

| # | Task | Commit | What landed |
|---|------|--------|-------------|
| 1 | Extend GET /traces with max_faithfulness + sort_by | `6eed298` | `TraceListFilters` extended; route adds two `Annotated[..., Query(...)]` params; `list_traces` SQL adds bind-9 `::float` predicate + conditional ORDER BY composed from a hard-coded set; 8 new integration tests EX1-EX8 |
| 2 | GET /traces/timeseries with adaptive bucketing | `4b68502` | `TimeseriesBucket` + `TimeseriesResponse` schemas; `_BUCKET_BY_WINDOW` dict; `PostgresTraceStore.timeseries(window)` with `generate_series` + LEFT JOIN; route registered before `/traces/{trace_id}`; 6 schema tests + 8 integration tests TS1-TS8 |

## Verification

- **Schemas:** `pytest tests/test_api_schemas.py`: 6 net new tests pass (TimeseriesBucket parse, extra=forbid rejection, window Literal validation, request_count >= 0 invariant, NULL aggregate semantics, response wrapping).
- **Integration:** `pytest tests/integration/test_timeseries_endpoint.py`: TS1-TS8 pass (live PG drill at end of plan run; FakePool path covered separately for unit-suite gating).
- **Integration (extended /traces):** `pytest tests/integration/test_traces_api.py`: EX1-EX8 pass plus all pre-existing Phase 4 cases unchanged.
- **Full suite at plan close:** 303 passed, 1 skipped (Task 2 commit message references the same baseline before plan-end metadata commit).
- **mypy --strict tracer_ai/api/traces.py tracer_ai/api/schemas.py tracer_ai/tracer/store.py**: 0 errors.
- **ruff check**: clean.
- **Module-deps invariant:** `PostgresTraceStore.timeseries()` returns `list[dict[str, Any]]` (NOT Pydantic) — preserves D-2.27 / import_cycle_guard rule that `tracer_ai/tracer/` MUST NOT import `tracer_ai/api/`.

## Decisions worth recording

- **`_BUCKET_BY_WINDOW` is the single source of truth for window → bucket-size mapping** (D-5.17): `1h → 1 minute`, `24h → 5 minutes`, `7d → 1 hour`, `30d → 1 day`. Future windows added here; route Literal must agree.
- **Cursor pagination v1 limitation under `sort_by=faithfulness_asc`** (T-05-05-06 ACCEPTED): the cursor still encodes `(started_at, id)` only — page boundaries continue to follow `started_at` even when the visible order is by faithfulness. Acceptable for <1000 judge-flagged traces; revisit when corpus grows.
- **`max_faithfulness` filter excludes NULL** (FBCK-03 semantic): judge-not-yet-scored is not "judge-flagged" — the absence of a score is information that there's no problem yet, only an absence of evaluation.
- **5-minute bucketing requires a subtraction trick**: `date_trunc('hour', t) + INTERVAL '5 minute' * floor(EXTRACT(MINUTE FROM t) / 5.0)` because `date_trunc` only supports natural intervals (minute/hour/day). Documented inline in `store.py timeseries()`.

## Deviations from plan

None of substance — Task 1 + Task 2 implementation matches the plan's `must_haves.truths` line-for-line. One minor surface refinement vs. plan text:

- **Route registration order** — plan implies adding the route in any position; runtime testing surfaced that FastAPI's path matching parses `/traces/timeseries` against `/traces/{trace_id}` if the parametric route is registered first (UUID parse failure → 400). Fix: register `/traces/timeseries` BEFORE `/traces/{trace_id}`. No scope change; this is the canonical FastAPI ordering rule.

## Hand-off to Wave 3 (plan 05-07)

Frontend can now wire:

- **Dashboard QualityCharts** (4 Tremor LineCharts) → `getTimeseries(window)` against `GET /traces/timeseries?window=24h` (default) — TanStack queryKey: `["timeseries", window]`. Faithfulness chart MUST set `connectNulls={false}` (D-5.07) — backend already returns NULL bucket rows; frontend just needs to opt out of the Tremor default smoothing.
- **Queue Judge-flagged tab** → `GET /traces?max_faithfulness=${threshold}&sort_by=faithfulness_asc&limit=50` where `threshold` comes from `GET /admin/eval-config`. Cursor pagination works as-is (page-boundary caveat documented above).
- **TraceListItem schema unchanged** — Plan 05-07 reuses existing types; `max_faithfulness` and `sort_by` are query-side only.
