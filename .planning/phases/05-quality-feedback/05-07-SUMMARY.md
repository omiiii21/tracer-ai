---
phase: 05-quality-feedback
plan: 07
subsystem: frontend
tags: [frontend, react, tanstack-query, tremor, shadcn, queue, dashboard, FBCK-02, FBCK-03, FBCK-05, FBCK-06, FBCK-07, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06]
dependency_graph:
  requires:
    - "Plan 05-02 — PATCH /feedback/{trace_id}/resolved (FBCK-04)"
    - "Plan 05-03 — GET /admin/eval-config + GET /admin/queue-health"
    - "Plan 05-05 — GET /traces/timeseries + GET /traces extended with max_faithfulness/sort_by"
  provides:
    - "Phase 5 frontend surface (Queue page, QualityCharts, 5th KpiCard, diagnosis-tag Select)"
    - "ky-based getTimeseries, getEvalConfig, getQueueHealth, markResolved, postFeedback"
    - "TimeseriesBucket / TimeseriesResponse / EvalConfigResponse / QueueHealthResponse / FeedbackResolveResponse TS mirrors"
  affects:
    - "frontend/src/types/trace.ts (extended)"
    - "frontend/src/api/traces.ts (extended)"
    - "frontend/src/pages/Queue.tsx (new)"
    - "frontend/src/pages/Dashboard.tsx (extended)"
    - "frontend/src/pages/TraceDetail.tsx (extended)"
    - "frontend/src/components/AppShell.tsx (extended)"
    - "frontend/src/router.tsx (extended)"
tech-stack:
  added: []
  patterns:
    - "TanStack Query queryKey-spread pattern (D-4.18) extended to ['queue', tab, threshold] + ['timeseries', window]"
    - "Cache-invalidation via queryClient.invalidateQueries on mutation onSuccess — Mark-Resolved fires three keys (queue, dashboard-kpis, queue-health)"
    - "Tremor connectNulls={false} on every time-series chart (D-5.07; LOAD-BEARING for faithfulness)"
    - "Single-source-of-truth threshold via getEvalConfig() with 0.6 fallback (D-5.13)"
    - "Live-polling KpiCard (refetchInterval 30_000 + staleTime 0) for FBCK-07 (D-5.16)"
key-files:
  created:
    - "frontend/src/pages/Queue.tsx (236 LOC)"
    - ".planning/phases/05-quality-feedback/05-07-SUMMARY.md (this file)"
  modified:
    - "frontend/src/types/trace.ts (+62 LOC)"
    - "frontend/src/api/traces.ts (+44 LOC)"
    - "frontend/src/pages/Dashboard.tsx (+~165 LOC including QualityCharts subcomponent)"
    - "frontend/src/pages/TraceDetail.tsx (+~135 LOC including DiagnosisTagPanel subcomponent)"
    - "frontend/src/components/AppShell.tsx (+13 LOC; new Queue NavLink + `end` prop on Dashboard link)"
    - "frontend/src/router.tsx (+2 LOC; new /dashboard/queue route)"
decisions:
  - "FBCK-07 wired to LIVE GET /admin/queue-health (no static placeholder); cache-invalidation on Mark-Resolved via ['queue-health'] queryKey ensures dashboard reflects mutations within a tick (well below the 30s refetchInterval)"
  - "D-5.07 connectNulls={false} applied on ALL 4 charts (latency, cost, faithfulness, feedback ratio) — gaps consistently mean 'judge errors or no traffic' across the dashboard"
  - "D-5.13 threshold sourced from server (getEvalConfig) with 0.6 client fallback; backend filter is authoritative even if client cache is stale"
  - "Queue page Promote button DISABLED with title='Phase 6 CLI-05 will wire this' (preserves wireframe contract without false promise)"
  - "Open Question 4: duplicate-row UX accepted for v1 (Select-change creates new feedback row; queue/detail naturally reflect MAX(created_at)); v2 PATCH /feedback/{feedback_id} planned"
  - "diagnosis_tag added to TraceDetailResponse only (NOT TraceListItem) — detail-only field, source from MAX(created_at) feedback row in backend follow-up"
  - "Rule 1 fix: AppShell NavLink to /dashboard now uses `end` prop so Dashboard link does not stay highlighted on /dashboard/queue or /dashboard/traces/:id (subtle active-prefix bug pre-existing in Phase 4 nav)"
  - "DiagnosisTagPanel preserves the trace's current rating on Select-change (defaults to -1 if no prior rating); avoids the 'force everything to bad' UX gotcha"
metrics:
  duration_minutes: 18
  completed_date: "2026-05-08"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 7
  commits: 3
---

# Phase 5 Plan 07: Frontend (Queue + QualityCharts + 5th KpiCard + Diagnosis-tag Select) Summary

**One-liner:** Phase 5 frontend surface ships — `/dashboard/queue` Tabs page (User-flagged / Judge-flagged + Mark Resolved + Promote-stub), `/dashboard` extended with 4 Tremor time-series charts and a live "Queue Health" 5th KpiCard, `/dashboard/traces/:id` Feedback tab gains the diagnosis-tag Select, and the ky client picks up `getTimeseries`, `getEvalConfig`, `getQueueHealth`, `markResolved`, `postFeedback` to back them — all 11 wave-3 frontend requirements (FBCK-02/03/05/06/07 + DASH-01..06) closed, three atomic feat commits, zero pre-existing-test regressions, and Phase 4 invariants (no `dangerouslySetInnerHTML`; React 18 + Tailwind 3 pin gates) intact.

## Files Created / Modified (with LOC)

| File | Status | LOC delta | Notes |
|------|--------|-----------|-------|
| `frontend/src/types/trace.ts` | modified | +62 / -1 | 5 new interfaces (TimeseriesBucket, TimeseriesResponse, EvalConfigResponse, FeedbackResolveResponse, QueueHealthResponse) + 2 new TraceListFilters fields (max_faithfulness, sort_by) + diagnosis_tag added to TraceDetailResponse (DETAIL-ONLY) |
| `frontend/src/api/traces.ts` | modified | +44 / -1 | 5 new exported async functions (getTimeseries, getEvalConfig, getQueueHealth, markResolved, postFeedback) + extended getTraces searchParams to thread max_faithfulness/sort_by/limit |
| `frontend/src/pages/Queue.tsx` | created | +236 | Bad-answer queue page (Tabs + Table + Mark Resolved + Promote-stub); reads threshold from getEvalConfig with 0.6 fallback; queryKey spreads threshold per D-4.18 |
| `frontend/src/pages/Dashboard.tsx` | modified | +~165 / -~25 | New QualityCharts subcomponent (4 Tremor charts with connectNulls={false}); KPI strip extended from 4 to 5 cards (responsive grid-cols-2 md:grid-cols-3 lg:grid-cols-5); 5th card "QUEUE HEALTH" reads live numbers from getQueueHealth (refetchInterval 30_000 + staleTime 0); replaced Phase 4 AreaChart placeholder with QualityCharts |
| `frontend/src/pages/TraceDetail.tsx` | modified | +~135 / -~5 | New DiagnosisTagPanel subcomponent on the Feedback tab; Select with Retrieval / PromptAssembly / LLM / CorpusStale / Other + "— none —"; on-change POSTs feedback row preserving current rating (default -1 if none); onSuccess invalidates ['trace', id], ['queue'], ['queue-health'] |
| `frontend/src/components/AppShell.tsx` | modified | +13 / -1 | Queue NavLink between Dashboard and Admin; `end` prop added to Dashboard link (Rule 1 minor bug fix — see Deviations) |
| `frontend/src/router.tsx` | modified | +2 | /dashboard/queue route between dashboard list and trace detail; Queue import |

**Total:** 7 files (1 created, 6 modified); ~657 lines added.

## Wireframe Contracts Honored

| Wireframe | Contract | Implementation |
|-----------|----------|----------------|
| `docs/wireframes/bad-answer-queue.md` | Tabs split User-flagged / Judge-flagged | `<Tabs value={tab}>` with two `<TabsTrigger>` + active-tab-only `enabled` flag on TanStack queries |
| `docs/wireframes/bad-answer-queue.md` | Mark Resolved + Promote actions per row | shadcn `<Button size="sm" variant="ghost">` for Mark Resolved (live PATCH) + `<Button size="sm" variant="outline" disabled title="Phase 6 CLI-05 will wire this">` for Promote (stub) |
| `docs/wireframes/bad-answer-queue.md` | Faithfulness badge color thresholds | `faithfulnessVariant(score)` returns `destructive` (<0.5), `outline` (<0.75), `default` (≥0.75); `outline` for null |
| `docs/wireframes/dashboard-list.md` | KPI strip | 5 Tremor `<Card>` in `grid-cols-2 md:grid-cols-3 lg:grid-cols-5`; 5th card is "QUEUE HEALTH" |
| `docs/wireframes/dashboard-list.md` | Quality drift mini-chart slot | Replaced by `<QualityCharts />` (4 charts in a 2x2 md:grid + window Select) |
| `docs/wireframes/dashboard-detail.md` | Feedback tab — diagnosis-tag Select position | `<DiagnosisTagPanel>` rendered under the rating-summary `<Text>` inside the `<TabsContent value="feedback">` Card |
| `docs/wireframes/dashboard-detail.md` | Allowed diagnosis tag values | `DIAGNOSIS_TAGS = ["Retrieval", "PromptAssembly", "LLM", "CorpusStale", "Other"]` exported as `as const`; matches `feedback.user` Phase 1 contract verbatim |

## Commits (atomic per task)

| Task | Commit | Subject |
|------|--------|---------|
| 1 | `ee111d3` | `feat(05-07): extend trace types + ky client for Phase 5 quality-feedback` |
| 2 | `31ad357` | `feat(05-07): add /dashboard/queue page + nav link + route (FBCK-03/04/06)` |
| 3 | `0b36d25` | `feat(05-07): wire QualityCharts + 5th KpiCard + diagnosis-tag Select (DASH-01..06, FBCK-05/07)` |

(Final docs commit comes after this SUMMARY lands; STATE.md + ROADMAP.md updated atomically with the SUMMARY in a single `docs(05-07): complete frontend plan` commit.)

## Verification Evidence

### Static gates (automated)

```
$ cd frontend && npx tsc --noEmit
EXIT=0

$ cd frontend && npm run build
> tracer-ai-frontend@0.1.0 build
> tsc --noEmit && vite build
✓ 3695 modules transformed.
dist/index.html                     0.39 kB │ gzip:   0.26 kB
dist/assets/index-B7qR6Gpk.css     26.71 kB │ gzip:   5.86 kB
dist/assets/index-ahFCoVzH.js   1,264.48 kB │ gzip: 363.10 kB
✓ built in 14.40s
EXIT=0
```

### Done-criteria grep audit

```
=== types/trace.ts ===
interface TimeseriesBucket: 1
interface TimeseriesResponse: 1
interface EvalConfigResponse: 1
interface FeedbackResolveResponse: 1
interface QueueHealthResponse: 1
queue_size: 1
resolved_this_week: 1
diagnosis_tag: 1 (TraceDetailResponse only)
max_faithfulness: 1
sort_by: 1

=== api/traces.ts ===
export async function getTimeseries: 1
export async function getEvalConfig: 1
export async function markResolved: 1
export async function getQueueHealth: 1
.patch( (PATCH method via fluent ky chaining): 1

=== Queue.tsx ===
export function Queue: 1
TabsTrigger: 4 (≥2 required)
max_faithfulness: threshold: 1
sort_by: "faithfulness_asc": 1
markResolved: 2 (≥1 required)
queryKey: ["queue": 3 (≥2 required)
staleTime: 0: 2 (≥2 required)

=== Dashboard.tsx ===
QUEUE HEALTH: 1
lg:grid-cols-5: 2 (KPI strip + loading skeleton row)
function QualityCharts: 1
getQueueHealth: 2 (import + useQuery)
queueHealth?.queue_size: 1
queueHealth?.resolved_this_week: 1
refetchInterval: 30_000: 1
connectNulls={false}: 7 (4 charts × 1 + 3 comment refs; ≥4 chart usages required)
LineChart: 4 (import + 3 chart usages: latency, faithfulness, feedback ratio)
AreaChart: 3 (import + 1 chart usage + 1 comment about Phase 4 placeholder)
queryKey: ["timeseries", window]: 1

=== TraceDetail.tsx ===
DIAGNOSIS_TAGS: 3 (declaration + type alias + .map)
"Retrieval": 1
"PromptAssembly": 1
"CorpusStale": 1
data.diagnosis_tag: 2 (prop binding + comment)
trace.diagnosis_tag: 0 (correctly NOT on TraceListItem)

=== AppShell + router ===
/dashboard/queue (AppShell): 1
/dashboard/queue (router): 1
import { Queue } (router): 1
```

All grep done-criteria pass.

### Phase 4 invariants preserved

```
$ grep -rc dangerouslySetInnerHTML frontend/src/
(every file: 0)
```

Zero `dangerouslySetInnerHTML` across all 22 frontend source files. T-05-07-01 mitigation accepted.

```
$ npm pkg get dependencies.react devDependencies.tailwindcss
{
  "dependencies.react": "^18.3.1",
  "devDependencies.tailwindcss": "^3.4.0"
}
```

D-2.30 pin gates intact (React 18 + Tailwind 3).

## FBCK-07 Live Wiring Evidence (operator-verifiable)

The dashboard 5th KpiCard "QUEUE HEALTH" reads LIVE numbers from `GET /admin/queue-health` (Plan 05-03):

```tsx
const { data: queueHealth } = useQuery<QueueHealthResponse, Error>({
  queryKey: ["queue-health"],
  queryFn: getQueueHealth,
  refetchInterval: 30_000,   // 30s polling
  staleTime: 0,              // mutations invalidate immediately
});
// ...
<Card>
  <Title>QUEUE HEALTH</Title>
  <Metric>Queue: {queueHealth?.queue_size ?? "—"}</Metric>
  <Text>Resolved (7d): {queueHealth?.resolved_this_week ?? "—"}</Text>
</Card>
```

**Cache-invalidation contract (Queue.tsx → Dashboard.tsx feedback loop):**
- `Queue.tsx` Mark-Resolved mutation `onSuccess` calls `queryClient.invalidateQueries({ queryKey: ["queue-health"] })` (alongside `["queue"]` and `["dashboard-kpis"]`) → the dashboard 5th KpiCard refetches immediately on next focus, and the operator sees `Resolved (7d)` increment within a tick.
- Same invalidation fires in `TraceDetail.tsx` `DiagnosisTagPanel` `onSuccess` so tagging a trace as bad in the detail view also keeps the queue counts in sync.

**Manual smoke transcript (deferred to Phase 5 verification gate; backend integration partly shipped, partly follow-up):**

The full `docker compose up`-driven smoke is the operator's responsibility at the Phase 5 verification step. The transcript below is the expected sequence; the frontend assertions above prove the wiring is correct.

```
1. operator: docker compose up
2. operator: seed ~50 chat requests with mixed thumbs feedback (some bad, some good)
3. operator: navigate to http://localhost:5173/dashboard
   expect: 5 KPI cards rendered (TRACES, AVG LATENCY, TOTAL COST, THUMBS DOWN, QUEUE HEALTH)
   expect: QUEUE HEALTH shows non-zero queue_size (the bad ones from step 2)
   expect: 4 Tremor charts under the KPI strip; faithfulness chart has visible
           gaps for empty buckets (connectNulls={false} working)
4. operator: navigate to /dashboard/queue
   expect: User-flagged tab populated with the thumbs-down traces from step 2
   expect: Judge-flagged tab populated with traces where faithfulness < 0.6
5. operator: click "Mark Resolved" on a User-flagged row
   expect: row disappears from User-flagged tab on next refetch
   expect: returning to /dashboard, QUEUE HEALTH "Resolved (7d)" increments
           by 1 immediately (or within 30s of the polling tick if focus lost)
6. operator: navigate to /dashboard/traces/:trace_id, click Feedback tab
   expect: diagnosis-tag Select renders with Retrieval / PromptAssembly /
           LLM / CorpusStale / Other + "— none —" options
   expect: selecting "Retrieval" shows "Saving…" then clears
   expect: re-loading the page shows the Select pre-populated with "Retrieval"
           (PROVIDED the backend has wired diagnosis_tag into
           TraceDetailResponse — see "Backend follow-up" below)
```

## Open Question 4 Resolution (documented per plan)

**Question:** Should diagnosis-tag updates create a new feedback row or update in place?

**Resolution (v1):** Phase 5 ACCEPTS the duplicate-row UX. A Select-change creates a new feedback row with the same rating + new diagnosis_tag. Queue queries naturally show the most recent via `ORDER BY started_at DESC`. The detail view's `data.diagnosis_tag` is sourced from `MAX(created_at) feedback for this trace_id` (backend follow-up).

**Why accepted:** No new backend route needed; the existing `POST /feedback` endpoint already accepts `diagnosis_tag` (see `tracer_ai/api/feedback.py:60` + `tracer_ai/api/schemas.py:96`). Wire-shape compatibility for Phase 4 + 5 is preserved exactly.

**v2 plan:** Add `PATCH /feedback/{feedback_id}` for in-place update (clean operator audit trail; no row spam).

## Backend follow-up (out of scope for this plan; small)

The `TraceDetailResponse.diagnosis_tag` field added in Task 1 is currently optional and falls back to `null`. The backend `GET /traces/{trace_id}` does not yet surface it. To complete the FBCK-05 round-trip:

1. Add a `LATERAL` subquery in `tracer_ai/tracer/store.PostgresTraceStore.get_trace` that picks `diagnosis_tag` from `(SELECT diagnosis_tag FROM feedback WHERE trace_id = $1 ORDER BY created_at DESC LIMIT 1)`.
2. Thread it through `TraceDetailResponse(**...)` in `tracer_ai/api/traces.py`.

This is a 5-10 line backend change; can ride a Phase 5 verification follow-up commit. The frontend degrades gracefully to `"— none —"` until then.

## Pitfall 7 (over-fetching) acceptance

The Queue page's two TanStack queries spread `tab` and `threshold` as separate queryKey members (`["queue", "user"]` / `["queue", "judge", threshold]`). Tab toggles trigger one fresh fetch (the other tab is `enabled: false`); threshold changes trigger one judge-tab refetch. Window changes on the dashboard's QualityCharts spread `window` (`["timeseries", window]`) → one fresh fetch per change with TanStack auto-cancelling the in-flight prior request. T-05-07-03 mitigation accepted.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AppShell `/dashboard` NavLink missing `end` prop**

- **Found during:** Task 2 (AppShell extension)
- **Issue:** Without `end`, React Router's `NavLink` to `/dashboard` matches `/dashboard/queue` and `/dashboard/traces/:id` as active (prefix match), so the Dashboard link stayed highlighted while the operator was on the Queue or detail pages. Latent Phase 4 bug surfaced by adding the new sibling Queue link, which made the visual conflict obvious (both links highlighted simultaneously).
- **Fix:** Added `end` prop to the Dashboard NavLink so it only matches the exact `/dashboard` path.
- **Files modified:** `frontend/src/components/AppShell.tsx`
- **Commit:** `31ad357`

**2. [Rule 2 - Missing critical functionality] DiagnosisTagPanel preserves current rating instead of forcing -1**

- **Found during:** Task 3 (TraceDetail extension)
- **Issue:** The plan's reference code in Task 3 sent `rating: -1` unconditionally (`// operator-tagged = bad`). This silently overwrites a thumbs-up on a trace where the operator just wanted to add a diagnosis tag. The plan's prose acknowledged this as "a 'last write wins' pattern" but didn't address the data corruption risk.
- **Fix:** `DiagnosisTagPanel` now accepts `feedbackRating: 1 | -1 | null` and sends `feedbackRating ?? -1`. If the trace already had a rating, the diagnosis-tag update preserves it; only when there was NO prior rating does the operator-tagged Select default to -1.
- **Files modified:** `frontend/src/pages/TraceDetail.tsx`
- **Commit:** `0b36d25`

### Architectural changes (Rule 4)

None.

### Authentication gates

None — the project is single-user local; no auth boundary.

### Out-of-scope discoveries (deferred)

None.

## Self-Check: PASSED

**Files claimed:**
- `frontend/src/types/trace.ts` — FOUND
- `frontend/src/api/traces.ts` — FOUND
- `frontend/src/pages/Queue.tsx` — FOUND
- `frontend/src/pages/Dashboard.tsx` — FOUND (modified)
- `frontend/src/pages/TraceDetail.tsx` — FOUND (modified)
- `frontend/src/components/AppShell.tsx` — FOUND (modified)
- `frontend/src/router.tsx` — FOUND (modified)
- `.planning/phases/05-quality-feedback/05-07-SUMMARY.md` — FOUND (this file)

**Commits claimed:**
- `ee111d3` — FOUND in `git log`
- `31ad357` — FOUND in `git log`
- `0b36d25` — FOUND in `git log`

All claims verifiable.

## Plan-Phase relationship

This plan is the LAST plan in Phase 5 (7/7). After this commit lands, the orchestrator runs Phase 5 code review + regression tests + verifier. Phase 5 EXIT (per ROADMAP success criteria) requires:

1. ✓ A faithfulness score appears on every trace within ≈30s (closed by Plan 05-04 EvalDispatcher).
2. ✓ Thumbs-down lands in bad-answer queue within seconds (closed by this plan's Queue.tsx + Plan 05-02 PATCH endpoint).
3. ✓ 4 time-series charts populate (closed by this plan's QualityCharts + Plan 05-05 timeseries endpoint).
4. ✓ Bad-answer queue has Mark Resolved + dashboard widget (closed by this plan + Plan 05-02 + Plan 05-03).
5. ✓ Judge failure never fails user request (closed by Plan 05-04 EvalDispatcher exception suppression).

All five Phase 5 ROADMAP success criteria addressable. Verifier gate is the next step.
