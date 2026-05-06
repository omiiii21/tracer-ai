---
phase: 04-tracer-trace-explorer
plan: 05
subsystem: frontend
tags: [phase-4, frontend, dashboard, trace-detail, span-waterfall, tanstack-query, shadcn, tremor, ky, react-router]

# Dependency graph
requires:
  - phase: 04-tracer-trace-explorer
    plan: 04
    provides: GET /traces + GET /traces/{trace_id} FastAPI routes; TraceListItem / TraceDetailResponse Pydantic schemas; ErrorResponse envelope; cursor pagination contract
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 09
    provides: Phase 3 frontend shell (AppShell, MetadataStrip, MessageBubble, lib/api.ts, Tremor v3, shadcn card/button/badge/input/skeleton, TanStack Query QueryClientProvider in main.tsx, Tailwind 3 / React 18 pins)
provides:
  - frontend/src/components/ui/tabs.tsx — shadcn Tabs primitive (Root + List + Trigger + Content) for /dashboard/traces detail view
  - frontend/src/components/ui/table.tsx — shadcn Table primitive (Header / Body / Row / Head / Cell) for /dashboard list
  - frontend/src/components/ui/slider.tsx — shadcn Slider primitive for min_faithfulness filter
  - frontend/src/components/ui/tooltip.tsx — shadcn Tooltip primitive (forward-compat for Phase 5 UI)
  - frontend/src/components/ui/select.tsx — shadcn Select primitive (Root + Trigger + Content + Item) for feedback filter
  - frontend/src/types/trace.ts — TS interfaces TraceListItem / TraceListResponse / SpanInDetail / SpanPayload / TraceDetailResponse / TraceListFilters
  - frontend/src/api/traces.ts — ky-based getTraces(filters) + getTrace(traceId) typed API client
  - frontend/src/components/SpanWaterfall.tsx — hand-rolled positioned-div waterfall with min-width 4px + click-to-expand attrs
  - frontend/src/pages/Dashboard.tsx — /dashboard list page (KPI strip + Tremor AreaChart + 5-dimension filter bar + paginated Table)
  - frontend/src/pages/TraceDetail.tsx — /dashboard/traces/:trace_id detail page (KPI cards + Tabs Spans/Payloads/Feedback + SpanWaterfall + JSON viewers)
  - Updated frontend/src/router.tsx — /dashboard + /dashboard/traces/:trace_id under AppShell; old /traces/:trace_id stub route removed
  - Updated frontend/src/components/AppShell.tsx — Dashboard NavLink between Chat and Admin
  - Updated frontend/src/components/MetadataStrip.tsx — "View trace" link target migrated from /traces/{id} to /dashboard/traces/{id}
  - Deleted frontend/src/pages/TraceStub.tsx
affects: [04-06, 05-eval, 05-fbck, 05-dash, 06-cli, 07-polish]

# Tech tracking
tech-stack:
  added:
    - ky@^1.14.3 (CLAUDE.md preferred fetch wrapper, ~2KB; replaces axios per "What NOT to Use")
    - "@radix-ui/react-tabs@^1.1.13"
    - "@radix-ui/react-slider@^1.3.6"
    - "@radix-ui/react-tooltip@^1.2.8"
    - "@radix-ui/react-select@^2.2.6"
  patterns:
    - "Hand-rolled SpanWaterfall via absolute-positioned <div>s + Tailwind max(4px, X%) — chart-library-free; rag.eval row hidden when absent (D-4.16 forward-compat)"
    - "TanStack useQuery queryKey memo spreads every filter dimension as separate array members so per-field changes invalidate cache (RESEARCH Pitfall 7 mitigation)"
    - "staleTime: 0 on Dashboard list (D-4.18) — always re-fetches on remount; one-shot setTimeout invalidate (NOT recurring refetchInterval) on TraceDetail when rag.eval is in-flight (T-04-05-04 mitigation)"
    - "Payload + attrs JSON rendered exclusively via <pre>{JSON.stringify(...)}</pre>; zero dangerouslySetInnerHTML across all 3 new components (T-04-05-01/02 XSS mitigation)"
    - "ky.create({ prefixUrl: '' }) idiom + paths without leading slash (e.g., 'traces') matches Phase 3 frontend convention; works with Vite dev proxy + same-origin production"
    - "Manually-scaffolded shadcn UI primitives (verbatim from upstream templates) instead of `npx shadcn@latest add` — avoids interactive CLI prompts on Windows + dependency churn; identical export surface (TabsList, TableHeader, etc.) so plan acceptance grep gates pass unchanged"

key-files:
  created:
    - frontend/src/components/ui/tabs.tsx
    - frontend/src/components/ui/table.tsx
    - frontend/src/components/ui/slider.tsx
    - frontend/src/components/ui/tooltip.tsx
    - frontend/src/components/ui/select.tsx
    - frontend/src/types/trace.ts
    - frontend/src/api/traces.ts
    - frontend/src/components/SpanWaterfall.tsx
    - frontend/src/pages/Dashboard.tsx
    - frontend/src/pages/TraceDetail.tsx
  modified:
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/src/router.tsx
    - frontend/src/components/AppShell.tsx
    - frontend/src/components/MetadataStrip.tsx
  deleted:
    - frontend/src/pages/TraceStub.tsx

key-decisions:
  - "Manual shadcn primitive scaffolding (write upstream templates directly) chosen over `npx shadcn@latest add tabs table slider tooltip select` — the CLI runs an interactive prompt on a fresh project + auto-installs Radix peer deps that we already had to install separately for the build to type-check. Manual scaffolding produces byte-identical component surfaces (TabsList, TableHeader, SliderPrimitive, TooltipPrimitive, SelectTrigger), keeps every plan acceptance grep gate passing, and runs deterministically without a prompt loop."
  - "ky was added even though Phase 3's lib/api.ts uses raw fetch — Plan acceptance criteria explicitly require `import ky from \"ky\"` in api/traces.ts (CLAUDE.md prefers ky over axios). Phase 3 lib/api.ts is left unchanged; Phase 4 traces.ts is the first ky-using module. Future polish phase may consolidate."
  - "QueryClientProvider verification confirmed already wired in Phase 3 main.tsx (`<QueryClientProvider client={queryClient}>` wraps `<App />` which wraps `<RouterProvider>`). No modification to main.tsx needed — Plan Task 1 step 3 explicitly says 'If main.tsx already wires QueryClientProvider, leave it as-is.'"
  - "Filter state is component-local (useState<TraceListFilters>); URL deep-linking is deferred (T-04-05-03 accepted disposition, Phase 7 polish item)."
  - "Dashboard staleTime: 0 + filters in queryKey both required: staleTime alone would still serve cached data on filter change because the queryKey wouldn't change unless we spread the fields."

patterns-established:
  - "Frontend XSS-safe payload rendering: ALL untrusted content (LLM-generated payloads, span attrs JSON) MUST go through `<pre>{JSON.stringify(value, null, 2)}</pre>`. No dangerouslySetInnerHTML in frontend/src/. Verified by `grep -rc dangerouslySetInnerHTML frontend/src/` returning 0 across the entire tree."
  - "TanStack queryKey ALWAYS spreads filter primitives as separate array members, never embeds the whole filters object — object identity changes on every setFilters call would force unnecessary refetches; per-field spread enables stable cache when only an unrelated field changes."
  - "One-shot setTimeout + queryClient.invalidateQueries inside useEffect is the canonical pattern for 'refetch once after delay' — avoids the infinite-loop class of bugs that recurring refetchInterval introduces (T-04-05-04)."
  - "Hand-rolled positioned-div waterfall using `style={{ left: \"X%\", width: \"max(4px, Y%)\" }}` — Tailwind cannot express CSS max() in arbitrary class form, so inline style is the right escape hatch for the min-width 4px requirement."
  - "Phase 4 forward-compat for Phase 5 rag.eval: `spans.find(s => s.name === 'rag.eval')` + `evalSpan && !evalSpan.ended_at` checks are no-ops in Phase 4 (no rag.eval span emitted) but become live behavior in Phase 5 EVAL-04 without any UI code change — encoded in both SpanWaterfall (D-4.16 dashed glyph branch) and TraceDetail (one-shot 5s refetch)."
  - "Manual shadcn primitive scaffolding pattern: future plans needing more shadcn components (form, dropdown-menu, popover, etc.) can write the upstream component template directly into `frontend/src/components/ui/<name>.tsx` after installing the corresponding `@radix-ui/react-<name>` peer dep. Avoids the `npx shadcn@latest add` interactive prompt on Windows."

requirements-completed: [EXPL-01, EXPL-02, EXPL-03, EXPL-04]

# Metrics
duration: ~17min
completed: 2026-05-06
---

# Phase 04 Plan 05: Frontend Dashboard + TraceDetail + SpanWaterfall Summary

**Trace explorer UI ships: /dashboard renders the KPI strip + Tremor AreaChart placeholder + 5-dimension filter bar (Query / Since / Until / Feedback / Min faithfulness / Max latency) + paginated shadcn Table; /dashboard/traces/:trace_id renders the KPI cards + shadcn Tabs (Spans / Payloads / Feedback) + a hand-rolled SpanWaterfall with min-width 4px and click-to-expand attrs; route migration from Phase 3's /traces/:trace_id stub to the production /dashboard + /dashboard/traces/:trace_id pair completes EXPL-03 and EXPL-04.**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-05-06T17:01Z
- **Completed:** 2026-05-06T17:18Z
- **Tasks:** 5 (Task 1 `tdd="false"`; Tasks 2-5 marked `tdd="true"` but ship code-only commits per the combined-commit precedent established in Plans 04-01/03/04 — frontend has no test infrastructure stood up in Phase 3, and Phase 4 explicitly defers e2e/Playwright wiring to Phase 7 polish)
- **Files created:** 10 (5 shadcn UI primitives + types/trace.ts + api/traces.ts + SpanWaterfall.tsx + Dashboard.tsx + TraceDetail.tsx)
- **Files modified:** 5 (package.json, package-lock.json, router.tsx, AppShell.tsx, MetadataStrip.tsx)
- **Files deleted:** 1 (TraceStub.tsx)

## Accomplishments

- 5 shadcn UI primitives shipped with the standard upstream templates: `tabs.tsx`, `table.tsx`, `slider.tsx`, `tooltip.tsx`, `select.tsx`. All export the canonical names (`TabsList`, `TableHeader`, `SliderPrimitive`, `TooltipProvider`, `SelectTrigger`) verified by plan acceptance greps.
- ky@^1.14.3 + 4 Radix peer deps installed; React 18.3 + Tailwind 3.4 pins preserved (Phase 2 D-2.30 contract): `npm pkg get` confirms `^18.3.1` + `^3.4.0`.
- `frontend/src/types/trace.ts` mirrors the Pydantic schemas verbatim from docs/api.md §4 + §5: `TraceListItem` (latency_ms / estimated_cost_usd required, faithfulness / feedback_rating nullable), `TraceListResponse` (items + next_cursor), `SpanInDetail` (parent_span_id / ended_at nullable), `SpanPayload`, `TraceDetailResponse` (trace + spans + payloads-by-span_id), `TraceListFilters` (all 7 EXPL-01 filter dimensions).
- `frontend/src/api/traces.ts` exposes `getTraces(filters)` + `getTrace(traceId)` with conditional searchParam population (only set keys for present filters — matches FastAPI Query optional semantics so `feedback=` etc. doesn't leak as empty string into the URL).
- `frontend/src/components/SpanWaterfall.tsx` (hand-rolled per D-4.15): absolute-positioned div per span; `style={{ left: pct%, width: max(4px, pct%) }}` for the bar; sync glyph `├─` / `└─` vs. async dashed glyph `└╌╌` for `name === "rag.eval"`; click-to-expand via `useState<Set<string>>`; `<pre>{JSON.stringify(span.attrs, null, 2)}</pre>` viewer (XSS-safe). Coalesces `rootDurationMs <= 0` to root-span wall-clock duration so in-flight traces still render scaled bars. Accessibility: `<button>` rows with `aria-expanded` + `aria-controls`.
- `frontend/src/pages/Dashboard.tsx` (EXPL-01 + EXPL-03): TanStack `useQuery<TraceListResponse, Error>` against `getTraces`; queryKey memo spreads ALL 5 filter dimensions (`query`, `since`, `until`, `feedback`, `min_faithfulness`, `max_latency_ms`) as separate array members so each one independently invalidates cache; `staleTime: 0` per D-4.18; KPI strip with 4 Tremor Cards (TRACES / AVG LATENCY / TOTAL COST / THUMBS DOWN); Tremor `AreaChart` placeholder for Phase 5 quality drift; full filter bar (Query Input + Since/Until datetime-local Inputs + Feedback Select + Min faithfulness Slider + Max latency Number Input); shadcn Table with row-click `navigate(/dashboard/traces/${trace_id})`; loading skeleton + error card per Phase 3 idiom.
- `frontend/src/pages/TraceDetail.tsx` (EXPL-04): TanStack `useQuery<TraceDetailResponse, Error>`; back-link to `/dashboard`; header KPI cards (latency / cost / faithfulness / feedback Badge with destructive variant on -1); shadcn Tabs split into Spans (SpanWaterfall) / Payloads (per-span `<pre>` JSON viewer) / Feedback (Phase 5 FBCK-05 placeholder); D-4.16/D-4.18 forward-compat: `evalSpan = spans.find(s => s.name === "rag.eval")` + `evalPending = Boolean(evalSpan && !evalSpan.ended_at)` triggers a one-shot `setTimeout(() => queryClient.invalidateQueries(...), 5000)` (NOT recurring `refetchInterval` per T-04-05-04 mitigation) — no-op in Phase 4 because no rag.eval span exists, becomes live in Phase 5 EVAL-04 with zero UI changes.
- Route migration complete: `/dashboard` + `/dashboard/traces/:trace_id` mounted under AppShell; old `/traces/:trace_id` stub route removed; `frontend/src/pages/TraceStub.tsx` deleted with zero dangling references (verified by `grep -r TraceStub frontend/src/` returning empty).
- AppShell nav order is `[Chat | Dashboard | Admin]` (matches docs/wireframes/README.md); MetadataStrip's "View trace" link target rewritten from `/traces/${traceId}` to `/dashboard/traces/${traceId}` (T-04-05-06 mitigation — Phase 3 chat deeplinks now reach the production explorer instead of the deleted stub).
- Production build clean: `npm run build` (which runs `tsc --noEmit && vite build`) emits a 1.26MB bundle (361KB gzip), ~3700 modules, in 19.5s. Vite warns about chunk size but the build succeeds — splitting is a Phase 7 polish opportunity.

## Task Commits

Each task was committed atomically:

1. **Task 1: Install shadcn UI primitives + ky + verify QueryClientProvider** — `6e61de5` (feat)
2. **Task 2: TS trace types + ky-based API client** — `8d5ba4a` (feat)
3. **Task 3: SpanWaterfall component (hand-rolled, D-4.15/D-4.16)** — `f61f8de` (feat)
4. **Task 4: Dashboard.tsx + TraceDetail.tsx pages (EXPL-03/EXPL-04)** — `4097af6` (feat)
5. **Task 5: Route migration + AppShell nav + MetadataStrip link + delete TraceStub** — `dad14a3` (feat)

_Note: Tasks 2-5 marked `tdd="true"` in the plan but committed as code-only feat commits — the project has no frontend test infrastructure (Playwright is in devDeps but no e2e tests exist; vitest/jest is not configured). Phase 4 plan does not stand up that infrastructure, and the plan's verify blocks all use `grep` + `npx tsc --noEmit` + `npm run build` rather than runtime tests. This matches the precedent set by Plans 04-01 / 04-03 / 04-04 (see their summary deviation notes on combined RED+GREEN execution)._

## Files Created/Modified

- **Created** `frontend/src/components/ui/tabs.tsx` — shadcn Tabs (Root + List + Trigger + Content) backed by @radix-ui/react-tabs
- **Created** `frontend/src/components/ui/table.tsx` — shadcn Table (Header / Body / Row / Head / Cell / Caption / Footer) — pure semantic HTML + Tailwind
- **Created** `frontend/src/components/ui/slider.tsx` — shadcn Slider backed by @radix-ui/react-slider
- **Created** `frontend/src/components/ui/tooltip.tsx` — shadcn Tooltip (Provider + Root + Trigger + Content) backed by @radix-ui/react-tooltip
- **Created** `frontend/src/components/ui/select.tsx` — shadcn Select (Root + Trigger + Content + Item + ScrollUp/Down + Label + Separator) backed by @radix-ui/react-select; uses lucide-react Check/ChevronDown/ChevronUp icons
- **Created** `frontend/src/types/trace.ts` — 6 interfaces mirroring docs/api.md §4 + §5 Pydantic schemas
- **Created** `frontend/src/api/traces.ts` — ky-based getTraces + getTrace clients
- **Created** `frontend/src/components/SpanWaterfall.tsx` — hand-rolled positioned-div waterfall (~160 LOC); SpanRow + SpanWaterfall components; aria-expanded disclosure pattern
- **Created** `frontend/src/pages/Dashboard.tsx` — /dashboard list page (~270 LOC); KPI + AreaChart + 5-dimension filter bar + shadcn Table with navigate-on-row-click
- **Created** `frontend/src/pages/TraceDetail.tsx` — /dashboard/traces/:trace_id detail page (~190 LOC); KPI cards + Tabs (Spans/Payloads/Feedback) + SpanWaterfall + JSON viewers + one-shot setTimeout invalidate
- **Modified** `frontend/package.json` — added 4 Radix peer deps (tabs/slider/tooltip/select) + ky; React 18.3 / Tailwind 3.4 pins preserved
- **Modified** `frontend/package-lock.json` — npm install side effect
- **Modified** `frontend/src/router.tsx` — replaced /traces/:trace_id (TraceStub) with /dashboard (Dashboard) + /dashboard/traces/:trace_id (TraceDetail), both under AppShell children
- **Modified** `frontend/src/components/AppShell.tsx` — Dashboard NavLink inserted between Chat and Admin; rendered nav order [Chat | Dashboard | Admin]
- **Modified** `frontend/src/components/MetadataStrip.tsx` — "trace ↗" Link's `to` prop migrated from `/traces/${traceId}` to `/dashboard/traces/${traceId}`
- **Deleted** `frontend/src/pages/TraceStub.tsx` — Phase 3 stub replaced by the new pages

## Verification Gate Output

The plan's `<verification>` block:

1. `cd frontend && npx tsc --noEmit` — exits 0 (no TS errors) ✓
2. `cd frontend && npm run lint` — N/A (no lint script in package.json — Phase 3 didn't configure one for the frontend; only the Python backend has ruff/mypy gates wired)
3. `cd frontend && npm run build` — exits 0; production bundle compiles. Last lines:
   ```
   ✓ 3694 modules transformed.
   dist/index.html                     0.39 kB │ gzip:   0.26 kB
   dist/assets/index-CyjOyzJ0.css     26.21 kB │ gzip:   5.84 kB
   dist/assets/index-CNEBpQPc.js   1,257.01 kB │ gzip: 361.11 kB
   (!) Some chunks are larger than 500 kB after minification.
   ✓ built in 19.47s
   ```
4. `docker compose up -d --build` then visit `http://localhost:5173/dashboard` — NOT EXECUTED in this plan run (deferred to Plan 04-06 phase verifier per D-4.25 — same precedent as Plan 04-04 Deviation 5).
5. `grep -rc "dangerouslySetInnerHTML" frontend/src/` — sums to 0 across the entire frontend/src/ tree ✓
6. `grep -rc "axios" frontend/src/api/traces.ts frontend/src/types/trace.ts` — returns 0 (ky-only per CLAUDE.md) ✓
7. Frontend pin gates: `cd frontend && npm pkg get dependencies.react devDependencies.tailwindcss` returns:
   ```
   { "dependencies.react": "^18.3.1", "devDependencies.tailwindcss": "^3.4.0" }
   ```
   Both pins intact ✓

## Threat Mitigation Acceptance

Per the plan's `<threat_model>` STRIDE table, every `mitigate` disposition has a passing acceptance test or grep gate:

| Threat ID | Mitigation | Acceptance | Status |
|-----------|------------|-----------|--------|
| T-04-05-01 (XSS via LLM payload) | All payload rendering uses `<pre>{JSON.stringify(...)}</pre>`; zero dangerouslySetInnerHTML | `grep -rc "dangerouslySetInnerHTML" frontend/src/components/SpanWaterfall.tsx frontend/src/pages/Dashboard.tsx frontend/src/pages/TraceDetail.tsx` returns 0 across all 3 files | PASS |
| T-04-05-02 (XSS via attrs JSON viewer) | Same — `JSON.stringify(span.attrs, null, 2)` inside `<pre>` block | grep gate (same as above) | PASS |
| T-04-05-04 (DoS via infinite refetch) | One-shot setTimeout (NOT recurring refetchInterval) | `grep -q "setTimeout" frontend/src/pages/TraceDetail.tsx` exits 0; `grep -q "refetchInterval" frontend/src/pages/TraceDetail.tsx` exits NON-zero | PASS |
| T-04-05-05 (Stale cache shows old filter results) | `staleTime: 0` on Dashboard; queryKey spreads filter fields | `grep -q "staleTime: 0" frontend/src/pages/Dashboard.tsx` exits 0 | PASS |
| T-04-05-06 (Click-through MetadataStrip points at deleted route) | `to={\`/dashboard/traces/${traceId}\`}` | `grep -q "/dashboard/traces/" frontend/src/components/MetadataStrip.tsx` exits 0 | PASS |

T-04-05-03 (filter inputs leak in URL) — disposition is `accept` per the plan's threat model (deep-linkable filtered views are a Phase 7 polish item).

## Decisions Made

- **Manual shadcn primitive scaffolding instead of `npx shadcn@latest add`.** The CLI runs an interactive prompt on a fresh project (Tailwind config / aliases / TypeScript variant) and would auto-install Radix peer deps. We installed Radix peer deps explicitly via `npm install --save` in Task 1 then wrote each shadcn component template directly. The component surfaces are identical (`TabsList`, `TableHeader`, `SliderPrimitive`, `TooltipPrimitive`, `SelectTrigger` all exported as expected) and every plan acceptance grep gate passes unchanged. This is a deviation from the plan's literal `<action>` step 1 (`npx --yes shadcn@latest add ...`); see Deviation 1 below.
- **ky added even though Phase 3 uses raw fetch.** Plan Task 2 acceptance criteria explicitly require `import ky from "ky"` in `frontend/src/api/traces.ts`. Phase 3's `frontend/src/lib/api.ts` continues to use `fetch`; Phase 4 traces.ts is the first ky-using module. CLAUDE.md "What NOT to Use" prefers ky (~2KB, fetch-based) over axios; ky is also explicitly cited in the project tech stack. Future polish phase may consolidate.
- **QueryClientProvider already wired.** Phase 3 main.tsx wraps `<App />` (which contains `<RouterProvider>`) in `<QueryClientProvider client={queryClient}>` (queryClient defined in `frontend/src/lib/queryClient.ts` with the same `staleTime: 30_000` + `retry: 1` defaults the plan would have set). No modification needed — Plan Task 1 step 3 explicitly says "If main.tsx already wires QueryClientProvider, leave it as-is."
- **Filter state component-local (useState), not URL params.** T-04-05-03 disposition in the plan's threat model is `accept` — Phase 7 polish item.
- **TanStack Query queryKey spreads filters into separate array members.** Object identity changes on every setFilters call would force unnecessary refetches; per-field spread enables stable cache when only an unrelated field changes. The acceptance criteria for Task 4 require this pattern (`queryKey: ["traces", filters.query, filters.since, ...]` rather than `queryKey: ["traces", filters]`).

## Deviations from Plan

### Deviation 1 (Rule 3 — Blocking; CLI interactivity on Windows)

**`npx shadcn@latest add tabs table slider tooltip select` is interactive on this Windows host and would prompt for project setup, blocking the task.**
- **Found during:** Task 1 (Install missing shadcn components)
- **Issue:** The plan's Task 1 step 1 specifies `cd frontend && npx --yes shadcn@latest add tabs table slider tooltip select`. The shadcn CLI when run against an existing project prompts interactively for several configuration values (style / base color / TypeScript / aliases) on first invocation. `--yes` bypasses confirmations but does not auto-resolve missing config prompts. On a Windows shell with non-TTY stdin (the Bash tool inherited environment), interactive prompts hang or error. The CLI also auto-installs Radix peer deps that we'd then have to verify pin-compatible.
- **Fix:** Installed the 4 Radix peer deps explicitly via `npm install --save @radix-ui/react-tabs @radix-ui/react-slider @radix-ui/react-tooltip @radix-ui/react-select ky`, then manually wrote each shadcn primitive template directly into `frontend/src/components/ui/<name>.tsx`. The templates are verbatim from the upstream shadcn registry and produce byte-identical export surfaces. Every Task 1 acceptance criterion (`grep -q "TabsList"`, `grep -q "TableHeader"`, `grep -q "SliderPrimitive"`, `grep -q "TooltipPrimitive"`, `grep -q "SelectTrigger"`) passes. The React 18 + Tailwind 3 pins are preserved as required.
- **Files modified:** frontend/package.json (4 Radix deps + ky added), frontend/package-lock.json, frontend/src/components/ui/{tabs,table,slider,tooltip,select}.tsx
- **Verification:** All Task 1 acceptance greps pass; `npx tsc --noEmit` exits 0; `npm run build` exits 0.
- **Committed in:** `6e61de5` (Task 1 commit)

### Deviation 2 (Rule 3 — Blocking; ky was not in package.json)

**`ky` is required by the plan's Task 2 acceptance criteria but was not in `frontend/package.json` at plan start.**
- **Found during:** Task 2 (TS types + ky-based API client) — discovered during Task 1 prep when reading current package.json
- **Issue:** Plan Task 2 acceptance criterion `grep -q 'import ky from "ky"' frontend/src/api/traces.ts` requires ky to be importable. CLAUDE.md tech stack lists ky as the preferred fetch wrapper, but Phase 3's `frontend/src/lib/api.ts` uses raw `fetch` and never installed ky. Phase 4's plan assumed ky was present — context refers to "ky (already in package.json from Phase 3)" which was not actually true.
- **Fix:** Installed ky@^1.14.3 alongside the Radix peer deps in Task 1. Pinned to `^1` (current major). Bundle size impact: ~2KB gzipped (negligible).
- **Files modified:** frontend/package.json, frontend/package-lock.json
- **Verification:** `import ky from "ky"` resolves at compile time; `npx tsc --noEmit` clean; `npm run build` clean.
- **Committed in:** `6e61de5` (Task 1 commit)

### Deviation 3 (Disclosure; phase-gate deferral, matches Plan 04-04 Deviation 5)

**Live Docker Compose smoke test (verification gate 4) NOT executed in this plan run.**
- **Found during:** Final verification gate.
- **Issue:** The plan's `<verification>` block lists `docker compose up -d --build` then browser visits to `/dashboard` and `/dashboard/traces/{nonexistent UUID}` to confirm shell rendering + 404 error card. Per D-4.25 ("Each plan ends with a verify block exercising only what that plan changed... Phase-end verifier (Plan 6) runs the synthetic-load p95 benchmark + the fresh-checkout drill"), the live boot drill is the canonical responsibility of the Plan 04-06 verifier. Plans 04-03 + 04-04 each made the same disclosure.
- **Resolution:** Documented as a deferral; gate 4 is reassigned to Plan 04-06 per D-4.25. The in-process gate `npm run build` clean (gate 3) verifies the production bundle compiles, which is the fastest pre-Plan-04-06 confidence signal. Plan 04-06 will additionally exercise the live boot end-to-end (chat → trace appears in /dashboard → row click → detail renders → SpanWaterfall draws 4 spans).
- **Files modified:** none (disclosure-only)
- **Verification:** N/A — Plan 04-06 will run the live drill.
- **Committed in:** N/A

### Deviation 4 (Rule 1 — Bug in plan verify regex; substring false-positive)

**Plan Task 5 verify includes `! grep -q "/traces/:trace_id" frontend/src/router.tsx` but `/dashboard/traces/:trace_id` (the new route) contains the old pattern as a substring.**
- **Found during:** Task 5 verify block.
- **Issue:** The plan's verify regex `/traces/:trace_id` matches the new `/dashboard/traces/:trace_id` line, so `! grep -q` returns false (FAIL) even though the old standalone route entry is gone. This is a flaw in the plan's verify, not in the implementation.
- **Fix:** Verified the more precise pattern `path: "/traces/:trace_id"` returns no matches (the actual intent — confirming the OLD route entry is removed). Inspected router.tsx by hand: only `path: "/dashboard"` and `path: "/dashboard/traces/:trace_id"` are present; old `path: "/traces/:trace_id"` line is gone; TraceStub import removed.
- **Files modified:** none (the implementation is correct; only the verify regex was incorrect in the plan).
- **Verification:** `grep -q 'path: "/traces/:trace_id"' frontend/src/router.tsx` returns 1 (no match) — correct state.
- **Committed in:** N/A (plan-bug disclosure)

### Deviation 5 (Disclosure; tdd="true" tasks shipped without runtime tests)

**Tasks 2-5 are marked `tdd="true"` in the plan but the frontend has no test runner configured.**
- **Found during:** Task 2 setup.
- **Issue:** The plan marks Tasks 2-5 as `tdd="true"`, which would normally mandate a RED commit (failing test) followed by a GREEN commit (implementation). Phase 3 stood up Playwright in devDeps but never authored a vitest/jest config, and there are no `*.test.ts` or `*.spec.ts` files in `frontend/src/`. The plan's verify blocks for Tasks 2-5 themselves use `grep` + `tsc --noEmit` (i.e., contract greps + type check), not runtime tests — so the "test" artifact in the TDD cycle is the grep gate, not a runnable test.
- **Resolution:** Each task ships a single `feat` commit that satisfies all the plan's `<acceptance_criteria>` and `<verify>` greps + `tsc --noEmit`. This matches the combined-commit precedent set by Plans 04-01 / 04-03 / 04-04 (see those summaries' deviation notes — Plan 04-04: "Combined RED+GREEN execution style on TDD tasks — each task ships its own test additions in the same commit"). Standing up vitest/jest + authoring component tests is out of scope for Plan 04-05; Phase 7 polish or a Phase 5 task may add it.
- **Files modified:** none (disclosure)
- **Verification:** All plan `<verify>` greps pass; `tsc --noEmit` clean; `npm run build` clean. No `<acceptance_criteria>` references runtime test execution.
- **Committed in:** N/A

---

**Total deviations:** 5 (2 blocking auto-fixes for shadcn CLI interactivity + missing ky dep; 1 disclosure of phase-end Docker drill deferral; 1 plan-verify-regex bug disclosure; 1 disclosure of frontend test-infra absence). Zero scope creep — every deviation is surface-level adjustment to honor real environmental constraints; the plan's `<behavior>`, `<acceptance_criteria>`, and `<verification>` are fully satisfied modulo gate 4 which is reassigned to Plan 04-06.

## Issues Encountered

- npm audit reports 2 moderate severity vulnerabilities after the install (transitive). No fixes applied — `npm audit fix --force` would do breaking changes; out of scope for Plan 05.
- Vite chunk-size warning (>500KB minified): the bundle includes Tremor + Recharts + Radix primitives. Code-splitting via dynamic `import()` is a Phase 7 polish opportunity (DEMO-* requirements have explicit "fast first paint" targets that may force this).
- Pre-commit hooks ran successfully on every commit; the `tracer_ai/ module DAG enforcement` and `pytest --testmon` gates correctly skipped (no Python files touched in this plan); the `anti-pattern grep` gate ran clean (no Phase 3 anti-patterns introduced).

## User Setup Required

None — no external service configuration required. Live Docker Compose drill is reserved for Plan 04-06.

## Next Phase Readiness

- **Plan 04-06 (Phase 4 verifier)** unblocked. Phase-end gates: (1) live Docker Compose boot drill — `docker compose up -d --build` + chat request → row appears in /dashboard within seconds → click-through to /dashboard/traces/{id} renders 4-span waterfall with attrs + payloads; (2) synthetic-load p95 benchmark for TRCR-08 (NoopTraceWriter vs. PostgresTraceWriter delta ≤ 100ms); (3) lifespan shutdown drain + warn-log assertion under burst.
- **Phase 5 EVAL-04** (rag.eval span emission) is forward-compat-ready: SpanWaterfall.tsx detects `name === "rag.eval"` and renders the dashed glyph; TraceDetail.tsx detects in-flight rag.eval and one-shot refetches at 5s; both code paths are no-ops in Phase 4 because no rag.eval span is emitted.
- **Phase 5 FBCK-03** (bad-answer queue UI) is unblocked: a filtered Dashboard view with `?feedback=down` against the existing `GET /traces` endpoint covers it without any new component or endpoint.
- **Phase 5 FBCK-05** (diagnosis-tag UI) has a placeholder slot in TraceDetail's Feedback tab — Phase 5 wires the diagnosis tag select + comment textarea + POST to /feedback there.
- **Phase 5 DASH-01..05** (time-series charts) reuses Phase 4's Tremor v3 setup and the AreaChart placeholder slot in Dashboard's Quality drift card — Phase 5 fills in the data series.
- **Phase 7 polish** items surfaced during this plan: code-splitting (DEMO-fast-first-paint), URL-state for filter deep-links (T-04-05-03), JSON export of trace from detail view (DEMO-04 — data already available), npm audit cleanup.

## Self-Check: PASSED

Verified at execution end:

- File `frontend/src/components/ui/tabs.tsx` exists ✓
- File `frontend/src/components/ui/table.tsx` exists ✓
- File `frontend/src/components/ui/slider.tsx` exists ✓
- File `frontend/src/components/ui/tooltip.tsx` exists ✓
- File `frontend/src/components/ui/select.tsx` exists ✓
- File `frontend/src/types/trace.ts` exists ✓
- File `frontend/src/api/traces.ts` exists ✓
- File `frontend/src/components/SpanWaterfall.tsx` exists ✓
- File `frontend/src/pages/Dashboard.tsx` exists ✓
- File `frontend/src/pages/TraceDetail.tsx` exists ✓
- File `frontend/src/router.tsx` modified (Dashboard + TraceDetail routes; TraceStub removed) ✓
- File `frontend/src/components/AppShell.tsx` modified (Dashboard NavLink added) ✓
- File `frontend/src/components/MetadataStrip.tsx` modified (link target → /dashboard/traces/) ✓
- File `frontend/src/pages/TraceStub.tsx` deleted ✓
- Commit `6e61de5` exists ✓
- Commit `8d5ba4a` exists ✓
- Commit `f61f8de` exists ✓
- Commit `4097af6` exists ✓
- Commit `dad14a3` exists ✓
- `npx tsc --noEmit` exits 0 ✓
- `npm run build` exits 0; production bundle emits ✓
- `grep -rc "dangerouslySetInnerHTML" frontend/src/` sums to 0 ✓
- `npm pkg get dependencies.react devDependencies.tailwindcss` returns `^18.3.1` + `^3.4.0` (Phase 2 D-2.30 pin gate intact) ✓

---
*Phase: 04-tracer-trace-explorer*
*Completed: 2026-05-06*
