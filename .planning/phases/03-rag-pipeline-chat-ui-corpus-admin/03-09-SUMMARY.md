---
phase: 03-rag-pipeline-chat-ui-corpus-admin
plan: 09
subsystem: frontend/admin-ui
tags: [react, tanstack-query, tremor, shadcn, react-18-pinned, tailwind-v3-pinned, state-machine, polling, sse-route-fix, playwright]

# Dependency graph
requires:
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 07
    provides: GET /admin/corpus, POST /admin/ingest (202 + 409), GET /admin/ingest/{job_id}, PATCH /admin/chunking-config (Plan 07 backend admin API)
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 08
    provides: frontend/src/lib/api.ts, lib/queryClient.ts, lib/sse.ts, router.tsx (with /admin AdminPlaceholder), AppShell, shadcn primitives (card/button/textarea/badge/label/dialog/toast/accordion), Toaster wired in main.tsx
provides:
  - frontend/src/components/ui/input.tsx (shadcn Input number-field primitive)
  - frontend/src/components/ui/skeleton.tsx (shadcn Skeleton primitive)
  - frontend/src/lib/api.ts admin wrappers (getCorpus, postIngest, getIngestStatus, patchChunkingConfig)
  - frontend/src/lib/api.ts admin types (DocSummary alias, ChunkingConfig, expanded IngestStatus with ingest_job_id + nullable docs_total)
  - frontend/src/pages/Admin.tsx (orchestrator; useQuery(['corpus'], getCorpus); empty corpus Callout; loading Skeletons; rose error card)
  - frontend/src/components/CorpusCards.tsx (4 Tremor Card/Metric/Text/Title; date-fns formatRelative + format)
  - frontend/src/components/DocList.tsx (Tremor Table; sortBy doc.id; Badge for section; ExternalLink icon; Skeleton empty state)
  - frontend/src/components/ReindexButton.tsx (idle/confirming/running/done/error state machine + 2s polling + invalidateQueries on succeeded)
  - frontend/src/components/IngestProgress.tsx (Tremor ProgressBar + 1Hz-tick elapsed counter row)
  - frontend/src/components/UrlIngestForm.tsx (client-side ^https?:// per-line regex + Line N: not a URL inline error)
  - frontend/src/components/ChunkingConfigForm.tsx (Input number fields + bounds + success toast + invalidateQueries)
  - frontend/tests/admin.spec.ts (8 e2e tests covering ADMN-01..04 + empty-corpus banner)
  - .gitignore additions (Playwright runtime artifacts)
affects: [04-tracer-postgres-writer (orthogonal), Phase 5 dashboard (separate page)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ReindexButton state machine: 5-state (idle, confirming, running, done, error) machine driven by TanStack Query useMutation + useQuery refetchInterval=2000. Pattern: useEffect watches statusQuery.data and transitions on succeeded/failed. Re-arm to idle 3s after done."
    - "Two-tap confirm pattern (T-03-09-04): first click sets state=confirming + setTimeout(3000) revert; second click within 3s fires the mutation. Lighter UX than a modal + matches research-doc 'no auth, single-user local' intent."
    - "TanStack Query polling pattern: useQuery({ queryKey: ['ingest', jobId], queryFn: () => getIngestStatus(jobId), enabled: !!jobId && state === 'running', refetchInterval: 2000 }). Auto-stops because enabled flips false when state transitions out of running."
    - "Server-cache invalidation: queryClient.invalidateQueries({ queryKey: ['corpus'] }) on succeeded re-index AND on chunking-config save → KPI cards + doc list refresh atomically."
    - "Empty corpus surface: Tremor Callout color='amber' + AlertTriangle icon as a banner above CorpusCards; DocList renders Skeleton rows + 'No documents indexed yet.' centered text. Plan 09 UI-SPEC §4.8."
    - "URL ingest client-side validation: split text by \\n, regex `^https?://` per non-empty line. On first failure, surface 'Line N: not a URL' inline (matches ADMN-04 e2e expectation). Server-side Plan 01 schema re-validates → defense in depth (T-03-09-01)."
    - "Chunking config bounds: client-side min/max attrs on Input + setFieldError-on-mismatch + server-side Pydantic Field(ge/le) + Plan 02 chunker constructor re-validation. Three layers (T-03-09-05)."
    - "Toast locator narrowing: when shadcn Toast renders, both <div>title</div> and <span aria-live>title</span> match the same getByText regex. Fix: .first() in tests OR narrow by role to the visible toast body."

key-files:
  created:
    - frontend/src/components/ui/input.tsx
    - frontend/src/components/ui/skeleton.tsx
    - frontend/src/pages/Admin.tsx (overwritten from Task-1 minimal shell)
    - frontend/src/components/CorpusCards.tsx
    - frontend/src/components/DocList.tsx
    - frontend/src/components/ReindexButton.tsx
    - frontend/src/components/IngestProgress.tsx
    - frontend/src/components/UrlIngestForm.tsx
    - frontend/src/components/ChunkingConfigForm.tsx
    - frontend/tests/admin.spec.ts
    - .planning/phases/03-rag-pipeline-chat-ui-corpus-admin/03-09-SUMMARY.md
  modified:
    - frontend/src/lib/api.ts (extended with 4 admin wrappers + DocSummary alias + ChunkingConfig type + expanded IngestStatus)
    - frontend/src/router.tsx (replaced AdminPlaceholder import with real Admin import)
    - frontend/tests/chat.spec.ts (Rule 3 bug-fix — route stubs now method-guarded)
    - .gitignore (added Playwright runtime artifact paths)

key-decisions:
  - "Two-task atomic split (Task 1: types/api/primitives/router; Task 2: page + components + tests). Task 1 ships the wire surface so Task 2 can implement against a stable typed contract. The minimal Admin shell in Task 1 keeps tsc + build green between tasks (bisectability)."
  - "ReindexButton uses useEffect to react to statusQuery.data, NOT useQuery's onSuccess (which is deprecated in TanStack Query v5). Pattern: setState on terminal status + clear jobId + show toast + invalidate corpus."
  - "DocSummary as the canonical name (matches plan task wording); CorpusDoc kept as a back-compat type alias so Plan 08 lib/api.ts type isn't a breaking change."
  - "IngestStatus.docs_total is `number | null` (was `number` in Plan 08). Plan 07 backend may emit null when total isn't yet known; the IngestProgress UI handles null gracefully."
  - "Empty corpus is BOTH a Tremor Callout banner above CorpusCards AND a Skeleton-rows DocList placeholder. The Callout is the action-prompt; the Skeleton rows are the visual placeholder. Two surfaces — both cued by chunk_count === 0."
  - "Tremor Toast strict-mode locator fix in test: `.getByText(/Chunking settings saved/i).first()` — needed because shadcn Toast renders both the visible <div> and a <span aria-live='assertive'> sibling for accessibility, and Playwright's strict-mode mode flags ambiguity."
  - "Rule 3 fix in chat.spec.ts: `**/chat` glob matched both GET (page navigation) and POST (API). Added `if (method !== 'POST') route.continue()` guards. Without this, the chat page navigation rendered the SSE response body as raw text. Pre-existing bug from Plan 08 (per Plan 08 SUMMARY: 'they were not executed end-to-end in this run because Playwright requires bringing up the Vite dev server'). Fix is required to satisfy Plan 09's >=13-tests verification gate."

patterns-established:
  - "5-state TanStack Query state machine for any 2-stage admin operation: idle → confirming → running → done|error. Reusable for any future admin operation that needs accidental-click protection + polled status (e.g., re-embed-all-chunks, regression-test-replay)."
  - "Per-line client validation pattern with line-number error: split by \\n, iterate, regex-test, return 'Line N: <reason>' on first failure. Reusable for any future textarea-of-list input (corpus exclusion list, allowed-domains list, etc.)."
  - "TanStack Query invalidate-on-mutation-success pattern: useMutation onSuccess → queryClient.invalidateQueries({ queryKey: ['<resource>'] }). Reusable for any mutation that mutates server state the page is also reading."

requirements-completed:
  - ADMN-01
  - ADMN-02
  - ADMN-03
  - ADMN-04

# Metrics
duration: ~1h46m
completed: 2026-05-05
---

# Phase 3 Plan 09: Admin Page Frontend Summary

**Built the /admin page surfacing all 4 KPI cards (Documents, Chunks, Embedding Model, Last Indexed), per-doc Tremor Table, Re-index button with idle/confirming/running/done/error state machine + 2s polling, URL ingest with client-side regex validation, and chunking config form. Closes ADMN-01..04 with 8 passing Playwright e2e tests against route-stubbed /admin/* endpoints.**

## Performance

- **Duration:** ~1h46m
- **Started:** 2026-05-05T18:04:36Z
- **Completed:** 2026-05-05T19:51:07Z
- **Tasks:** 2 (both type="auto")
- **Files created:** 11 (2 shadcn primitives + 6 components + 1 page + 1 e2e spec + 1 SUMMARY)
- **Files modified:** 4 (lib/api.ts extension + router.tsx Admin wiring + chat.spec.ts Rule-3 bug-fix + .gitignore Playwright artifacts)

## Accomplishments

- **`getCorpus`, `postIngest`, `getIngestStatus`, `patchChunkingConfig` typed wrappers** added to `frontend/src/lib/api.ts`. Each is a thin async function returning the typed Plan 07 wire shape; `postIngest` translates HTTP 409 into `Error("Ingest already in progress")` for clean UI handling. The existing `Citation`, `ChatRequest`, `FeedbackRequest` exports from Plan 08 are preserved verbatim.
- **`DocSummary` (canonical name, matches plan wording) + `ChunkingConfig`** types added; `CorpusDoc` retained as a back-compat alias. `IngestStatus.docs_total` widened to `number | null` (Plan 07 backend may emit null when total isn't yet known); `ingest_job_id` added to `IngestStatus` per plan task spec.
- **Two new shadcn primitives** following the Plan 08 React-18 idiom (forwardRef + cn() + displayName): `frontend/src/components/ui/input.tsx` (h-10 number/text input with focus ring) and `frontend/src/components/ui/skeleton.tsx` (animate-pulse rounded muted div). No new transitive deps; no Radix needed.
- **`Admin.tsx` orchestrator** uses `useQuery(['corpus'], getCorpus, { staleTime: 30_000 })`. Three rendering paths: (a) `isLoading` → Skeleton placeholders for cards + doc list, (b) `isError` → rose-tinted Card with error message + Retry button (calls `queryClient.invalidateQueries`), (c) success → CorpusCards + DocList + actions panel. Empty-corpus path additionally renders an amber `<Callout>` banner above the cards (UI-SPEC §4.8). Layout: `max-w-7xl mx-auto p-8 space-y-6` + `lg:grid-cols-3` with DocList in 2-col + actions in 1-col.
- **`CorpusCards.tsx`** renders 4 Tremor `Card` components in a `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4` grid. Labels are load-bearing for the e2e (`DOCUMENTS`, `CHUNKS`, `EMBEDDING MODEL`, `LAST INDEXED` — uppercase, exact). Last-indexed uses `formatRelative` (top metric) + `format(date, 'PPpp')` (subtitle) from `date-fns`. Embedding-model card overrides `Metric` to `text-base` because model names are too long for the default 2xl style.
- **`DocList.tsx`** renders a Tremor `Table` with columns: Doc ID (font-mono), Section (shadcn Badge variant=secondary), Chunks (right-aligned, locale-formatted), Source (truncated url + `<ExternalLink>` icon, target=_blank rel=noreferrer), Last ingested (`formatRelative`). Default sort: doc.id ascending (`[...docs].sort((a, b) => a.id.localeCompare(b.id))` memoized). Empty state (`docs.length === 0 && chunkCount === 0`): 4 Skeleton rows + centered "No documents indexed yet." text.
- **`ReindexButton.tsx`** is the 5-state machine surface:
  - `idle` → button label "Re-index corpus" (default variant)
  - first click → `confirming`, label "Click again to confirm"; `setTimeout(3000)` reverts to `idle` if no second click
  - second click within 3s → `useMutation(postIngest)`; on success: stash `jobId`, transition to `running`
  - `running` → useQuery polls `getIngestStatus(jobId)` every 2s; renders `<Loader2 spinning />` icon + IngestProgress below; button is disabled
  - on `succeeded`: invalidate `['corpus']`, transition to `done` ("Re-index complete"), success toast (`{chunks_written} chunks written.`), 3s timer reverts to `idle`
  - on `failed`: transition to `error` ("Re-index failed — retry"), destructive variant; clicking reverts to `idle`
- **`IngestProgress.tsx`** uses Tremor `<ProgressBar value={progress * 100} color="amber" />` + a counter row showing `{processed} / {total} docs · {chunks} chunks · {elapsed}s elapsed`. The elapsed counter ticks once a second (`setInterval` in a useEffect gated on `status.status === "running"`) so the user sees fresh elapsed time even though the polled `started_at` only updates every 2s. `docs_total` is rendered conditionally (renders just `{processed} docs` when total is null per the Plan-07 wire shape).
- **`UrlIngestForm.tsx`** has shadcn Label + Textarea + Button. Submission splits the text by `\n`, validates each non-empty line against `/^https?:\/\//`, surfaces `Line N: not a URL` inline (with `role="alert"` + `aria-describedby` linkage for a11y) on first failure. Otherwise it calls `useMutation(postIngest with {urls})`. On success: clears the textarea + shows a queue-confirmation toast.
- **`ChunkingConfigForm.tsx`** uses two `<Input type="number">` fields with `min/max/step` (`chunk_size: 100..4000 step 50`, `overlap: 0..500 step 10`). Initial values are derived from `corpus.chunking_config` (Plan 07 returns it) or fall back to `900/100`. Submit calls `useMutation(patchChunkingConfig)`; on success: `invalidateQueries({ queryKey: ['corpus'] })` + success toast `"Chunking settings saved." / "They'll apply on the next re-index."`.
- **8 admin Playwright tests** in `frontend/tests/admin.spec.ts`:
  1. `renders 4 KPI cards with the expected labels (ADMN-01)` — heading "Corpus" + DOCUMENTS/CHUNKS/EMBEDDING MODEL/LAST INDEXED visible.
  2. `renders the doc list with a row per doc (ADMN-01)` — `[data-testid="doc-row"]` count = 3; each `claude-docs/*` id visible.
  3. `re-index button is two-tap and starts polling (ADMN-02)` — first click → "Click again to confirm"; second click → POST happens; `[data-testid="ingest-progress"]` appears.
  4. `re-index progress UI shows docs/chunks counts (ADMN-02)` — counter shows "18 / 52 docs" + "1,243 chunks".
  5. `chunking config form persists via PATCH (ADMN-03)` — fill 600/50, submit; assert PATCH body `{chunk_size: 600, overlap: 50}`; assert success toast.
  6. `URL ingest validates each line client-side (ADMN-04)` — invalid line → "Line 1: not a URL" inline; no POST sent.
  7. `URL ingest submits valid URLs (ADMN-04)` — two valid URLs → POST `{urls: [...]}` with both URLs.
  8. `empty corpus surfaces amber Callout banner (ADMN-01)` — chunk_count=0 → `[data-testid="empty-corpus-banner"]` visible + "No documents indexed yet." in DocList.
- **All 8 admin + 8 chat = 16/16 Playwright tests pass** in the full `npx playwright test` run on chromium. tsc + vite build clean. Pin gates intact (react@^18.3.1, tailwindcss@^3.4; `react@^19` count = 0, `tailwindcss@^4` count = 0).

## Task Commits

Each task committed atomically as planned:

1. **Task 1: input + skeleton primitives + admin api wrappers + Admin route shell** — `ae2a6d3` (feat)
2. **Task 2: Admin page + 6 components + 8 e2e tests + chat.spec.ts route bug-fix + .gitignore** — `79f100d` (feat)

## Files Created/Modified

**Created (11):**
- `frontend/src/components/ui/input.tsx` — shadcn Input primitive (number/text fields).
- `frontend/src/components/ui/skeleton.tsx` — shadcn Skeleton primitive (loading placeholders).
- `frontend/src/pages/Admin.tsx` — orchestrator (useQuery['corpus']; loading/error/empty/success rendering).
- `frontend/src/components/CorpusCards.tsx` — 4 Tremor KPI cards (Tremor Card/Metric/Text/Title + date-fns).
- `frontend/src/components/DocList.tsx` — Tremor Table with Badge + ExternalLink + Skeleton-rows empty state.
- `frontend/src/components/ReindexButton.tsx` — 5-state machine + useMutation + useQuery polling + invalidateQueries.
- `frontend/src/components/IngestProgress.tsx` — Tremor ProgressBar + 1Hz-tick counter row.
- `frontend/src/components/UrlIngestForm.tsx` — client-side `^https?://` regex + inline Line N error + useMutation.
- `frontend/src/components/ChunkingConfigForm.tsx` — Input number fields + bounds + useMutation + toast + invalidateQueries.
- `frontend/tests/admin.spec.ts` — 8 e2e tests covering ADMN-01..04 + empty-corpus banner.
- `.planning/phases/03-rag-pipeline-chat-ui-corpus-admin/03-09-SUMMARY.md` — this summary.

**Modified (4):**
- `frontend/src/lib/api.ts` — added `DocSummary` (canonical) + `ChunkingConfig`; expanded `IngestStatus` with `ingest_job_id` + `docs_total: number | null`; added 4 admin endpoint wrappers.
- `frontend/src/router.tsx` — replaced `AdminPlaceholder` with real `import { Admin } from "@/pages/Admin"`.
- `frontend/tests/chat.spec.ts` — **Rule 3 fix:** added `if (method !== 'POST') route.continue()` guards to `/chat` and `/feedback` route stubs. Without this, GET /chat (page navigation) was being intercepted and served the SSE response body as HTML, breaking all 7 chat tests downstream of `await page.goto('/chat')`.
- `.gitignore` — added Playwright runtime artifact paths (`frontend/test-results/`, `frontend/playwright-report/`, `frontend/.playwright/`).

## Decisions Made

- **Two-task atomic split (Task 1 = wire surface; Task 2 = page + components + tests).** Task 1 ships typed wrappers + types + primitives + a minimal Admin route shell so the router compiles. Task 2 implements the page and components against the stable Task-1 contract. Bisectability: if Task 2 misbehaves, Task 1 is independently green (tsc + build at `ae2a6d3`).
- **`DocSummary` as the canonical name** (matches plan task wording verbatim); `CorpusDoc` retained as `type CorpusDoc = DocSummary` so Plan 08 imports don't break. Single-source-of-truth for the wire shape.
- **`IngestStatus.docs_total: number | null`** (was `number` in Plan 08). Plan 07 backend may emit null when the total isn't yet known (per the Plan 07 admin.py wire); `IngestProgress` handles null by rendering just `{processed} docs` instead of `{processed} / {total} docs`.
- **ReindexButton uses `useEffect(..., [statusQuery.data, state, ...])` to drive transitions**, NOT TanStack Query v5's deprecated `onSuccess` per-query callback. Pattern: useEffect watches `statusQuery.data` + current state; sets terminal state + invalidates `['corpus']` + shows toast + clears jobId.
- **5-state machine over a `confirmingTimerRef`-managed pattern.** Tracking confirming/running/done/error explicitly — instead of inferring from `useMutation.isPending` + `useQuery.isPending` flags — gives the e2e test a `data-state` attribute it can assert on, and lets the button cleanly disambiguate "running and disabled" from "error and ready to retry".
- **Two-tap confirm pattern** (3s revert) replaces a modal Dialog. Lighter UX; matches the research-doc 'no auth, single-user local' intent. The URL ingest form uses single-tap (the URL list itself is the deliberate input).
- **Tremor `Callout color="amber"`** for the empty-corpus banner (matches UI-SPEC §4.8); the `data-testid="empty-corpus-banner"` attribute lets the e2e select it without depending on Tremor's internal class structure.
- **`.first()` locator narrowing in the chunking-config test.** shadcn Toast renders the title text twice — once in the visible `<div>` and once in an `aria-live="assertive"` `<span>` for screen readers. Playwright's strict-mode mode flagged the ambiguity. Adding `.first()` is the documented Playwright pattern for this case.
- **Rule 3 chat.spec.ts route-stub bug-fix.** The Plan 08 tests stubbed `**/chat` without method guard, intercepting both POST (the SSE API) and GET (the page navigation). Browser GET → Playwright stub → SSE body served as HTML → Vite HMR script never injected → React app never renders → all selectors timeout. The Plan 08 SUMMARY notes that the e2e tests "were not executed end-to-end in this run" — confirming the bug was latent. Without this fix, Plan 09's `>=13 passing tests` verification gate fails. Same fix applied symmetrically to `/feedback`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] chat.spec.ts route-stub method-guard bug-fix**
- **Found during:** Task 2 verify (running full Playwright suite to satisfy Plan 09's `>=13 passing tests` gate)
- **Issue:** Plan 08's `chat.spec.ts` registers `page.route("**/chat", ...)` without checking the request method. The glob matches both GET `/chat` (browser navigating to the chat page) and POST `/chat` (the SSE API call). When the browser navigates to `/chat`, Playwright intercepts and returns the SSE response body as HTML — Vite's dev-server HMR script is never injected, the React app never mounts, and all subsequent selectors (`getByRole("textbox")`, etc.) time out. 7 of 8 chat tests fail. Plan 08 SUMMARY documents that the tests "were not executed end-to-end in this run" — confirming the bug was latent.
- **Fix:** Added `if (route.request().method() !== "POST") { await route.continue(); return; }` guard to both the `/chat` and `/feedback` stubs in `chat.spec.ts`. Page navigations now fall through to Vite; only the API POST is intercepted.
- **Files modified:** `frontend/tests/chat.spec.ts` (route handler bodies).
- **Commit:** `79f100d`
- **Witness:** before fix, `npx playwright test tests/chat.spec.ts` reports `1 passed, 7 failed`; after fix, `8 passed`. Full suite: `16 passed (chat 8 + admin 8)`.

**2. [Rule 3 - Blocker] Playwright Chromium browser missing**
- **Found during:** First admin test run
- **Issue:** Playwright was upgraded since Plan 08, requiring `chromium_headless_shell-1217`. Only `chromium-1208` was installed locally. All Playwright tests aborted with `Executable doesn't exist at ...chrome-headless-shell-win64.zip`.
- **Fix:** Ran `npx playwright install chromium` to download the missing browser bundle (~111MB).
- **Files modified:** None (browser bundle lives outside the repo at `~/AppData/Local/ms-playwright/chromium_headless_shell-1217/`).
- **Note:** documented in `User Setup Required` below — fresh checkouts will need the same one-time install.

**3. [Rule 1 - Bug] Toast strict-mode locator violation in chunking-config test**
- **Found during:** First full run of admin tests
- **Issue:** `page.getByText(/Chunking settings saved/i).toBeVisible()` resolved to two elements — the visible toast `<div>` body AND an `aria-live="assertive"` `<span>` sibling that shadcn Toast renders for screen-reader announcements. Playwright's strict-mode flagged the ambiguity.
- **Fix:** Narrowed to `.first()` (the visible toast body is rendered first in DOM order). Documented in the test as a comment.
- **Files modified:** `frontend/tests/admin.spec.ts` line 268.
- **Commit:** `79f100d`

### Adds Beyond Plan (Critical Functionality, Rule 2)

**4. [Rule 2 - Critical] `.gitignore` Playwright runtime artifacts**
- **Found during:** Pre-commit `git status` cleanup
- **Issue:** Running `npx playwright test` creates `frontend/test-results/` and (on failures) `frontend/playwright-report/`. These were untracked and accumulating in `git status`. Without ignoring them, future runs would either pollute commits or trigger spurious 'untracked files' on every CI run.
- **Fix:** Added `frontend/test-results/`, `frontend/playwright-report/`, `frontend/.playwright/` to `.gitignore`.
- **Commit:** `79f100d`

## Issues Encountered

- **None blocking.** The three auto-fixes above were resolved within the same task; no checkpoint or human action required. Auto mode: all fixes applied without prompting.

## Threat Mitigations Applied

| Threat ID | Status | Where |
|-----------|--------|-------|
| T-03-09-01 (Tampering — UrlIngestForm client-side regex bypass) | Mitigated (defense in depth) | `UrlIngestForm.tsx` regex `/^https?:\/\//` is UX-only; Plan 01 server-side `IngestUrlsRequest.urls` field_validator re-applies the same regex. Witness: `tests/admin.spec.ts::test_url_ingest_validates` (client-side surface) + `tests/test_admin_routes.py::test_post_ingest_invalid_url` (server-side; Plan 07). |
| T-03-09-02 (Information Disclosure — DocList source_url) | Accepted (documented) | Local-dev only; the operator IS the audience. Source URL truncation prevents accidental layout leaks but isn't a security boundary. `target="_blank" rel="noreferrer"` on every external link defends against window.opener tampering. |
| T-03-09-03 (Spoofing — /admin/* unauthenticated) | Accepted (inherited) | v1 single-user local-dev only (ADR 009). Inherited from Plan 07. The frontend doesn't add or weaken the boundary. |
| T-03-09-04 (DoS — ReindexButton spam-click) | Mitigated | Two-tap confirm pattern (3s revert timer); `disabled` while running; server-side 409 from Plan 07's single-flight asyncio.Lock prevents concurrent ingests even if the UI fails to gate. Three layers. Witness: `tests/admin.spec.ts::re-index button is two-tap and starts polling`. |
| T-03-09-05 (Tampering — ChunkingConfigForm out-of-range) | Mitigated (defense in depth) | shadcn `Input min={100} max={4000} step={50}` (browser-level) + `setFieldError` on submit-time bounds check (component-level) + Plan 01 `ChunkingConfigPatch` field bounds (server-level) + Plan 02 `MarkdownHeaderChunker.__init__` re-validation (chunker-level). Four layers. |
| T-03-09-06 (Information Disclosure — error toast leakage) | Mitigated | All toasts surface `err.message` only (e.g., `postIngest failed: 409`); never the full backend traceback. Plan 07 backend error field is itself bounded to `str(exc)` (T-03-07-09). Two layers. |
| T-03-09-07 (Repudiation — admin actions audit trail) | Mitigated (inherited + supplemented) | Plan 07 backend logs structured events for every mutation (`corpus_listed`, `ingest_dispatched`, `chunking_config_updated`, ...); the frontend supplements with success/failure toasts that confirm the action to the operator (UX audit). |

## Self-Check: PASSED

- File `frontend/src/components/ui/input.tsx` exists. Verified.
- File `frontend/src/components/ui/skeleton.tsx` exists. Verified.
- File `frontend/src/pages/Admin.tsx` exists; uses `useQuery`. Verified (3 useQuery occurrences, ≥1).
- File `frontend/src/components/CorpusCards.tsx` exists; imports `@tremor/react`. Verified (1 import).
- File `frontend/src/components/DocList.tsx` exists; imports from `@tremor/react`. Verified (1 import).
- File `frontend/src/components/ReindexButton.tsx` exists; uses `useMutation` + `refetchInterval`. Verified (4 occurrences combined, ≥2).
- File `frontend/src/components/IngestProgress.tsx` exists; uses `ProgressBar`. Verified (3 occurrences, ≥1).
- File `frontend/src/components/UrlIngestForm.tsx` exists; uses URL regex. Verified (2 occurrences, ≥1).
- File `frontend/src/components/ChunkingConfigForm.tsx` exists; uses `patchChunkingConfig`/`chunk_size`/`overlap`. Verified (16 occurrences, ≥2).
- File `frontend/tests/admin.spec.ts` exists.
- Pin gates: `grep -c '"react": "\^19' frontend/package.json` → 0. Verified.
- Pin gates: `grep -c '"tailwindcss": "\^4' frontend/package.json` → 0. Verified.
- Pin gates: `grep -c '"react": "\^18' frontend/package.json` → 1. Verified.
- `cd frontend && npx tsc --noEmit` exits 0. Verified.
- `cd frontend && npm run build` exits 0 (1.18MB / 337KB gzip — Tremor cost). Verified.
- `cd frontend && npx playwright test tests/admin.spec.ts` → 8 passed. Verified.
- `cd frontend && npx playwright test` (full suite) → 16 passed. Verified.
- Commit `ae2a6d3` (Task 1) exists in `git log`. Verified.
- Commit `79f100d` (Task 2) exists in `git log`. Verified.
- `git status` shows no `STATE.md` or `ROADMAP.md` modifications (per orchestrator instruction). Verified.

## User Setup Required

- **One-time:** `cd frontend && npx playwright install chromium` to download the matching browser bundle (~111MB). Required for `npx playwright test` to run; otherwise tests abort with `Executable doesn't exist at ...chromium_headless_shell-1217/chrome-headless-shell-win64.exe`.
- For end-to-end smoke against a live backend: `docker compose up` (in repo root) then `npm run dev` (in `frontend/`); visit `http://localhost:5173/admin`. Requires `ANTHROPIC_API_KEY` + `VOYAGE_API_KEY` env (per Plan 06's lifespan construction).

## Next Phase Readiness

- **Phase 3 wave 5 complete** — both Plan 08 (chat UI) and Plan 09 (admin UI) are wired against the Plan 06/07 backend. The full surface specified in `docs/api.md` is live in the browser.
- **Phase 3 manual smoke** unblocked: an operator can now `docker compose up` + `npm run dev`, visit `/admin`, see corpus state, trigger re-index, watch progress, edit chunking config — exactly the loop described in the foundation PRD.
- **Phase 4 (tracer Postgres writer)** orthogonal — the trace explorer at `/traces/:trace_id` is still the Plan 08 stub; Phase 4 EXPL-04 swaps the body in.
- **Phase 5 (eval + judge + dashboard)** unblocked. The `/dashboard` route is a future addition to `router.tsx`; the chunking-config invalidation pattern + Tremor card grid pattern from this plan are directly reusable.
- **Phase 7 (polish)** — documented v1.5+ items inherited from Plan 07 are unchanged: (a) `corpus_ingest_jobs` DB table for cross-restart job persistence, (b) /admin/* auth gate, (c) production-grade error scrubbing.

## Threat Flags

None — no new attack surface beyond the plan's `<threat_model>` register. Inventory of net-new browser-side surface introduced by this plan:

- Outbound `fetch('/admin/corpus', GET)` — bounded by Plan 07 wire schema; response strictly typed via `CorpusState`.
- Outbound `fetch('/admin/ingest', POST, JSON body)` — bounded by Plan 01 `IngestRequest` discriminated union (server re-validates each URL, caps list at 100); 409 is mapped to a UX-bounded Error.
- Outbound `fetch('/admin/ingest/{id}', GET)` — bounded by Plan 07 single-flight; `IngestStatus.error` is `str(exc)` only (T-03-07-09).
- Outbound `fetch('/admin/chunking-config', PATCH, JSON body)` — bounded by Plan 01 `ChunkingConfigPatch` field bounds + chunker constructor re-validation.
- Inline rendering of `corpus.docs[].source_url` and `corpus.docs[].id` — React text rendering escapes; `<a target="_blank" rel="noreferrer">` for external nav.

---
*Phase: 03-rag-pipeline-chat-ui-corpus-admin*
*Completed: 2026-05-05*
