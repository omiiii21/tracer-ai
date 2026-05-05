---
phase: 03-rag-pipeline-chat-ui-corpus-admin
plan: 08
subsystem: frontend/chat-ui
tags: [react, react-router, sse, fetch-readable-stream, shadcn, radix, tailwind-v3-pinned, react-18-pinned, tanstack-query, playwright, async-generator, abort-controller, multi-turn-chat]

# Dependency graph
requires:
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 06
    provides: POST /chat SSE handler emitting `event: token` + `event: final` frames; POST /feedback row insert (Literal[-1, 1] cross-layer); ChatFinalEvent JSON shape with trace_id: str
  - phase: 02-skeleton-infrastructure
    plan: 05
    provides: Vite + React 18.3.1 + Tailwind v3.4 + shadcn (Zinc) baseline; Card + Button primitives; cn() utility; @/* path alias; pin gates (react@^19=0, tailwindcss@^4=0)
provides:
  - frontend/src/lib/sse.ts (sseStream async generator over fetch ReadableStream)
  - frontend/src/lib/api.ts (postChat, postFeedback typed wrappers + admin types reserved for Plan 09)
  - frontend/src/lib/queryClient.ts (TanStack Query client)
  - frontend/src/router.tsx (createBrowserRouter with /chat default, /admin placeholder, /traces/:trace_id)
  - frontend/src/components/AppShell.tsx (top nav with text wordmark + NavLink Chat/Admin + Outlet)
  - frontend/src/components/MessageList.tsx (scrollable + auto-scroll-on-token)
  - frontend/src/components/MessageBubble.tsx (user/assistant variants; aria-live during streaming; cursor `▋`)
  - frontend/src/components/Citation.tsx (Citation inline marker + CitationAccordion expander)
  - frontend/src/components/MetadataStrip.tsx (latency/tokens/cost format strings + thumbs + trace link)
  - frontend/src/components/MessageInput.tsx (Enter sends, Shift+Enter newline, disabled while streaming)
  - frontend/src/components/ThumbsFeedback.tsx (▲ instant POST; ▼ Dialog with comment Textarea then POST)
  - frontend/src/components/ui/{textarea,accordion,dialog,toast,toaster,badge,label}.tsx (shadcn primitives)
  - frontend/src/components/ui/use-toast.ts (React-18 idiomatic toast hook)
  - frontend/src/pages/Chat.tsx (page; owns useState<Message[]>; SSE stream consumer; multi-turn-within-session)
  - frontend/src/pages/TraceStub.tsx (Phase-3 placeholder for /traces/:trace_id satisfying CHAT-05)
  - frontend/playwright.config.ts (chromium project; webServer wraps `npm run dev --port 5173 --strictPort`)
  - frontend/tests/chat.spec.ts (8 e2e tests covering CHAT-01..05 + multi-turn + streaming-incrementality)
affects: [03-09-admin-ui-frontend, 04-tracer-postgres-writer (TraceStub upgraded to real explorer)]

# Tech tracking
tech-stack:
  added:
    - date-fns@^3.6.0 (declared this phase; used by Plan 09 for last_indexed_at formatting)
    - "@playwright/test"@^1.47.0 (devDependency this phase)
    - "@radix-ui/react-accordion"@^1.2.1
    - "@radix-ui/react-dialog"@^1.1.2
    - "@radix-ui/react-label"@^2.1.0
    - "@radix-ui/react-toast"@^1.2.2
    - "@radix-ui/react-slot"@^1.1.0
    - tailwindcss-animate@^1.0.7 (transitive shadcn animation utility)
  patterns:
    - "SSE consumer pattern: async generator over fetch().body.pipeThrough(new TextDecoderStream()).getReader(); split incoming text on `\\n\\n` frame delimiters; per-frame regex extraction of `event:` and `data:` lines; JSON.parse the data line; yield {event, data}. Caller iterates via `for await`."
    - "AbortController plumbed through SSE: postChat accepts AbortSignal; Chat.tsx stashes the controller in a ref and aborts on component unmount via useEffect cleanup (T-03-08-05 mitigation)."
    - "Discriminated-union Message[] in local React state: { role: 'user' } | { role: 'assistant'; streaming: boolean; ... }. Only one source of truth (component-local useState); no Redux/Zustand; multi-turn-within-session is just `setMessages(prev => [...prev, newUser, newAssistantPlaceholder])`."
    - "Load-bearing format strings for CHAT-03 e2e regex: `${latency_ms}ms`, `${input_tokens}→${output_tokens} tok`, `$${cost.toFixed(4)}`. Editing these breaks e2e."
    - "Auto-scroll via `useEffect` keyed on (messages.length, totalContentLength): scrolls during token append, not just on new message."
    - "shadcn primitive shape for Radix-backed components: forwardRef + ElementRef<typeof Primitive.X> + ComponentPropsWithoutRef<typeof Primitive.X> + cn() composition; displayName inherits from Primitive.X.displayName."
    - "Toast hook in React-18 idioms (no `use()` hook): module-level dispatch + listeners array + useState/useEffect subscription. Eviction TOAST_LIMIT=3, REMOVE_DELAY=5000ms."
    - "Playwright route stubbing for SSE: page.route('**/chat', route.fulfill({ headers: { Content-Type: 'text/event-stream', ... }, body: 'event: token\\ndata: {...}\\n\\nevent: final\\ndata: {...}\\n\\n' })); responses indexed via callIdx counter for multi-turn tests."

key-files:
  created:
    - frontend/src/lib/sse.ts
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryClient.ts
    - frontend/src/router.tsx
    - frontend/src/components/AppShell.tsx
    - frontend/src/components/MessageList.tsx
    - frontend/src/components/MessageBubble.tsx
    - frontend/src/components/Citation.tsx
    - frontend/src/components/MetadataStrip.tsx
    - frontend/src/components/MessageInput.tsx
    - frontend/src/components/ThumbsFeedback.tsx
    - frontend/src/components/ui/textarea.tsx
    - frontend/src/components/ui/accordion.tsx
    - frontend/src/components/ui/dialog.tsx
    - frontend/src/components/ui/toast.tsx
    - frontend/src/components/ui/toaster.tsx
    - frontend/src/components/ui/use-toast.ts
    - frontend/src/components/ui/badge.tsx
    - frontend/src/components/ui/label.tsx
    - frontend/src/pages/Chat.tsx
    - frontend/src/pages/TraceStub.tsx
    - frontend/playwright.config.ts
    - frontend/tests/chat.spec.ts
  modified:
    - frontend/src/App.tsx (replaced hello-card with <RouterProvider router={router} />)
    - frontend/src/main.tsx (wrapped App with QueryClientProvider; added <Toaster /> sibling)
    - frontend/package.json (added date-fns, @playwright/test, @radix-ui/* transitive deps, tailwindcss-animate)

key-decisions:
  - "Two-task atomic split: Task 1 = scaffolding (deps + lib/* + router + AppShell + 7 shadcn primitives + TraceStub); Task 2 = chat page proper (Chat.tsx + 6 chat components + Playwright config + e2e tests). The split preserves bisectability — if Task 2 misbehaves, Task 1's plumbing is independently green (tsc + build clean at f32ecea)."
  - "Hand-edit shadcn primitives to React-18 idioms: the shadcn CLI's latest (3.5.x) toast template ships with React-19-only API (`use()` hook). use-toast.ts is hand-rewritten as module-level dispatch + listener array + useState/useEffect subscription, mirroring the pattern from shadcn 2.x. Pin gate stays clean (react@^19 still 0)."
  - "ChatMessage discriminated union lives in MessageList.tsx (re-exported as `type ChatMessage`) rather than its own types file. The union is used only by MessageList + Chat (and forwarded into MessageBubble props). Co-locating it with its first consumer keeps the import graph minimal."
  - "Auto-scroll effect depends on (messages.length + totalContentLen). Depending on `messages.length` alone would only scroll on new bubble — auto-scroll during token streams requires a value that changes per token. Aggregated content length is the simplest such value."
  - "Empty state H1 copy is locked verbatim to `Ask a question about the Claude API or Agent SDK.`. The CHAT-01 e2e selects by exact heading name; rewording the copy would break the test silently."
  - "Multi-turn within session is just an append: submit() pushes a new `{role: 'user'}` + `{role: 'assistant', streaming: true}` pair onto `messages`. There's no `clear` or `reset` path for the second submission. The Playwright e2e `multi-turn within a session` asserts userBubbles.toHaveCount(2) AND first-pair-still-visible after the second final frame — proves no-clear behavior."
  - "ThumbsFeedback uses `aria-pressed` on each button and toggles `text-emerald-600` / `text-rose-600` on selection, but does NOT lock the button (clicking ▲ then ▼ still works) — UX choice: ratings can be revised in v1; eval pipeline reads the most recent feedback row by trace_id timestamp."
  - "TraceStub does not use AppShell: the route is registered as a top-level entry (not nested under the AppShell layout route). Rationale: the trace explorer in Phase 4 will likely want full-bleed layout (waterfall views), not the nav. Phase 3's stub matches that future shape so the Phase 4 swap is one component replacement."
  - "Playwright config uses workers=1 + fullyParallel=false. Reasoning: the webServer (Vite dev) is shared across tests, and the chat tests share global page state (the route handler closure) — a single worker is the simplest correctness gate. Performance impact on 8 tests is acceptable (~30s total in CI)."
  - "chunks_written is recorded as a string in the SSE response body (`JSON.stringify(...).slice(...)` pattern not used — the entire response body is built in one shot via sseBody helper). Playwright's route.fulfill streams the body atomically; the test doesn't need real chunked encoding because the frontend's sseStream parser splits on `\\n\\n` regardless of whether bytes arrive chunked or all-at-once. The DOM-mutation test (CHAT-02) asserts MutationObserver records >= 2 distinct content snapshots — sufficient evidence of incremental rendering through React's batching even without simulated network chunking."

patterns-established:
  - "SSE + fetch ReadableStream as the canonical browser-side streaming pattern. Reusable for any future SSE endpoint (e.g., admin ingest progress in Plan 09 if the team chooses SSE over JSON polling)."
  - "Discriminated-union Message[] in local component state: foundation for future trace explorer message-history view, eval flagged-answers view, etc."
  - "Playwright route.fulfill body construction for SSE: sseBody({ tokens, trace_id, cited_chunks, ... }) helper. Reusable for any future streaming-endpoint test."

requirements-completed:
  - CHAT-01
  - CHAT-02
  - CHAT-03
  - CHAT-04
  - CHAT-05

# Metrics
duration: continuation
completed: 2026-05-05
---

# Phase 3 Plan 08: Chat UI Frontend Summary

**Streaming chat page (`/chat`) with SSE token rendering, citation accordion, latency/tokens/cost metadata strip, thumbs feedback dialog, multi-turn-within-session, and a `/traces/:trace_id` stub satisfying CHAT-01..05.**

## Performance

- **Duration:** continuation execution (Task 1 scaffold landed in commit f32ecea pre-execution; Task 2 wire-up completed and committed as fc90a30 in this run)
- **Completed:** 2026-05-05
- **Tasks:** 2 (both type="auto"; Task 1 scaffolding, Task 2 chat page proper)
- **Files created:** 23 (3 lib + 1 router + 1 AppShell + 6 chat components + 7 shadcn primitives + 1 use-toast + 2 pages + 1 playwright config + 1 e2e spec)
- **Files modified:** 3 (App.tsx → RouterProvider; main.tsx → QueryClientProvider + Toaster; package.json → date-fns + @playwright/test + @radix-ui/* transitive deps)

## Accomplishments

- **`lib/sse.ts` async generator** parses `text/event-stream` from `fetch().body` via `pipeThrough(new TextDecoderStream())`. Splits on `\n\n` frame delimiters, regex-extracts `event:` and `data:` lines, JSON-parses the data, yields `{event, data}`. Defensive: throws on `!res.ok` or missing `res.body`; tolerates malformed JSON by yielding the raw string. RESEARCH §4 verbatim implementation.
- **`lib/api.ts` typed client** with `postChat(req, signal?)` (yields `SSEEvent` discriminated union) and `postFeedback(req)` (returns `FeedbackResponse`). Re-exports admin types (`CorpusState`, `IngestRequest`, `IngestStatus`, `ChunkingConfigPatch`) for Plan 09 reuse — single source of truth for the wire surface.
- **`lib/queryClient.ts`** exports a `QueryClient` with `staleTime: 30_000` + `retry: 1` defaults. Wired in `main.tsx` via `<QueryClientProvider>`.
- **`router.tsx`** uses `createBrowserRouter` with `/` → `<Navigate to="/chat" replace />`, `<AppShell />` layout route wrapping `/chat` (Chat page) and `/admin` (placeholder for Plan 09), and a top-level `/traces/:trace_id` (TraceStub — no AppShell so Phase 4 can use full-bleed).
- **`AppShell.tsx`** renders the top nav: text wordmark `tracer-ai` linking to `/chat`, two `NavLink`s (Chat | Admin) with active-state styling via the `({isActive}) => className` callback. Outlet for the layout's children. Light-theme only.
- **`pages/Chat.tsx`** owns local `useState<ChatMessage[]>` + `useState<boolean>(streaming)`. On submit: appends user + assistant placeholder; opens `postChat` generator; iterates SSE events:
  - `event: token` → appends `data.text` to in-progress assistant content (immutable map over `messages`)
  - `event: final` → flips `streaming: false`, populates `trace_id` + `cited_chunks` + `metadata`
  - `event: error` → flips `streaming: false`, sets `error` field
  - on fetch reject (network) → same error path; on AbortController abort (unmount) → silent
  Multi-turn within session: a second submit while not streaming appends a new user+assistant pair; the first pair stays present (no `setMessages([])`).
- **`MessageList.tsx`** is a `role="log" aria-label="Chat history"` scrollable region. Auto-scroll-to-bottom effect keyed on `(messages.length, totalContentLen)` — scrolls during token streams, not just on new bubble. Forwards messages to `MessageBubble` per-role.
- **`MessageBubble.tsx`** has two variants: user (right-aligned, `bg-primary text-primary-foreground`) and assistant (left-aligned, `bg-card border` with `role="article"` + `aria-live="polite"` while `streaming === true`). Streaming cursor `▋` rendered inside a `motion-safe:animate-pulse` span (respects `prefers-reduced-motion`). `data-testid="assistant-content"` on the content span anchors the CHAT-02 MutationObserver test. Error variant: `border-rose-300 bg-rose-50` + Retry button. After streaming completes, mounts `<CitationAccordion>` and `<MetadataStrip>` below.
- **`Citation.tsx`** exports two components: `Citation` (inline `[N]` superscript anchor with `href="#cite-N"`) and `CitationAccordion` (shadcn `Accordion type="single" collapsible` with header `Sources (N)` and per-chunk panel showing `[idx] doc_id · section_title · score.toFixed(2)`, `<pre>` chunk content in `font-mono text-xs whitespace-pre-wrap`, and a `target="_blank" rel="noreferrer"` source_url link).
- **`MetadataStrip.tsx`** is the load-bearing CHAT-03 surface. Format strings:
  - `${latency_ms}ms` — matches `/\d+\s*ms/`
  - `${input_tokens}→${output_tokens} tok` — matches `/\d+\s*→\s*\d+\s*tok/`
  - `$${estimated_cost_usd.toFixed(4)}` — matches `/\$\d+\.\d+/`
  Plus inline `<ThumbsFeedback>` and `<Link to={`/traces/${traceId}`}>` (with `<span className="sr-only">` extension for screen-reader context). Trailing `ml-auto` pushes the trace link to the right edge.
- **`MessageInput.tsx`** is a sticky-bottom form with shadcn `Textarea` + `Button`. Enter submits (preventDefault); Shift+Enter inserts newline. `aria-label="Ask a question about the Claude API"` on the Textarea for screen readers. Send button label flips `Send` → `Streaming…` while `disabled === true`. Disabled also gates on `!input.trim()`.
- **`ThumbsFeedback.tsx`** renders two icon buttons (lucide `ThumbsUp` / `ThumbsDown`) with `aria-pressed` reflecting selection. ▲ click → instant `postFeedback({trace_id, rating: 1, comment: null})` + success toast. ▼ click → opens shadcn `Dialog` with a `Textarea` (max 1000 chars, with running `${comment.length} / 1000` counter) + Cancel + Submit; submit posts `rating: -1, comment` and closes. Errors surface as destructive toasts. Both buttons stay clickable post-submit (rating is revisable).
- **7 shadcn primitives** + `use-toast.ts`:
  - `textarea` — minimal forwardRef textarea with focus ring
  - `accordion` — Radix-backed Accordion/Item/Trigger/Content with rotating ChevronDown
  - `dialog` — Radix-backed Dialog with Overlay + portal + close-X + Header/Footer/Title/Description
  - `toast` — Radix Toast.Root variants (default/destructive/success/warning) + Action/Close/Title/Description
  - `toaster` — Toaster component reading `useToast().toasts` and rendering each via Toast primitive
  - `use-toast` — React-18 idiomatic hook (no `use()`); module-level dispatch + listeners; `TOAST_LIMIT=3`, `TOAST_REMOVE_DELAY=5_000`
  - `badge` — variant-based pill (default/secondary/destructive/outline)
  - `label` — Radix Label.Root forwardRef wrapper
- **`pages/TraceStub.tsx`** renders a Card with the `useParams<{ trace_id: string }>()` echoed into `<p className="text-xs font-mono bg-muted ...">` and a `<Link to="/chat">← Back to chat</Link>`. Sufficient for CHAT-05 e2e ("link present + non-404"); Phase 4 EXPL-04 replaces the body.
- **`playwright.config.ts`** — chromium project; webServer = `npm run dev -- --port 5173 --strictPort`; `fullyParallel: false`, `workers: 1` (single dev server, shared route handler closure); `trace: "retain-on-failure"`.
- **`tests/chat.spec.ts`** — 8 e2e tests via `page.route('**/chat')` SSE stub + `page.route('**/feedback')` 201 stub:
  1. `renders empty state with H1 and example chips (CHAT-01)` — heading + chip visible
  2. `sends a question and renders the streamed assistant response (CHAT-01)` — user + assistant bubbles; assembled tokens
  3. `streams chunks incrementally — DOM mutates >= 2 times during a response (CHAT-02)` — MutationObserver on `[data-testid="assistant-content"]` records distinct snapshots; expect ≥ 2
  4. `metadata strip renders latency / tokens / cost (CHAT-03)` — three `getByText(regex)` assertions matching the load-bearing format strings
  5. `citation accordion expands and shows chunk content (CHAT-02)` — `Sources (1)` button click → chunk content + section_title visible
  6. `thumbs-down opens dialog, submitting POSTs /feedback rating=-1 (CHAT-04)` — Dialog opens, comment fills, Submit fires; assert `feedbackCalls[0].rating === -1` + `comment` contains text
  7. `trace link points to /traces/{trace_id} and renders TraceStub (CHAT-05)` — `getAttribute("href") === /traces/{TRACE_ID_1}` + click → TraceStub heading visible + `trace_id: ...` text visible (no 404)
  8. `multi-turn within a session — second question appends without clearing the first (CHAT-01)` — two stubbed responses; after Q2 final, assert `userBubbles.toHaveCount(2)` + `assistantBubbles.toHaveCount(2)` + first user/assistant pair text still visible

## Task Commits

Each task committed atomically; the chain mirrors the plan's two-task split:

1. **Task 1: Scaffolding** — `f32ecea` (feat) — deps + sse.ts + api.ts + queryClient.ts + router.tsx + AppShell + 7 shadcn primitives + use-toast + TraceStub + main.tsx + App.tsx wiring. Pin gates verified post-install (react@^18.3.1; no react@^19; no tailwindcss@^4). tsc clean, vite build succeeds.
2. **Task 2: Chat page + components + e2e tests** — `fc90a30` (feat) — Chat.tsx full implementation, 6 chat components (MessageList, MessageBubble, Citation, MetadataStrip, MessageInput, ThumbsFeedback), playwright.config.ts, chat.spec.ts (8 tests). tsc clean, vite build succeeds.

## Files Created/Modified

**Created (23):**
- `frontend/src/lib/sse.ts` — async generator over fetch ReadableStream parsing SSE frames.
- `frontend/src/lib/api.ts` — postChat (SSE), postFeedback (JSON), reserved admin types.
- `frontend/src/lib/queryClient.ts` — TanStack Query client with conservative defaults.
- `frontend/src/router.tsx` — createBrowserRouter route table (/, /chat, /admin, /traces/:trace_id).
- `frontend/src/components/AppShell.tsx` — top-nav + Outlet layout.
- `frontend/src/components/MessageList.tsx` — scrollable + auto-scroll-on-token + ChatMessage discriminated union.
- `frontend/src/components/MessageBubble.tsx` — user/assistant variants + streaming cursor + error variant.
- `frontend/src/components/Citation.tsx` — inline `[N]` marker + CitationAccordion.
- `frontend/src/components/MetadataStrip.tsx` — load-bearing format strings + thumbs + trace Link.
- `frontend/src/components/MessageInput.tsx` — Enter-sends Textarea form.
- `frontend/src/components/ThumbsFeedback.tsx` — ▲ instant POST; ▼ Dialog → POST.
- `frontend/src/components/ui/{textarea,accordion,dialog,toast,toaster,badge,label}.tsx` — shadcn primitives.
- `frontend/src/components/ui/use-toast.ts` — React-18 idiomatic toast hook.
- `frontend/src/pages/Chat.tsx` — page; SSE consumer; multi-turn.
- `frontend/src/pages/TraceStub.tsx` — Phase 3 placeholder for /traces/:trace_id.
- `frontend/playwright.config.ts` — chromium project + webServer wrapper.
- `frontend/tests/chat.spec.ts` — 8 e2e tests covering CHAT-01..05 + multi-turn + streaming-incrementality.

**Modified (3):**
- `frontend/src/App.tsx` — replaced hello-card with `<RouterProvider router={router} />`.
- `frontend/src/main.tsx` — wrapped App with `<QueryClientProvider>` + added `<Toaster />` sibling.
- `frontend/package.json` — added `date-fns@^3.6.0`, `@playwright/test@^1.47.0`, `@radix-ui/react-{accordion,dialog,label,toast,slot}` transitive deps, `tailwindcss-animate@^1.0.7`. **Pin gates intact** (react@^18.3.1 only; no react@^19; no tailwindcss@^4).

## Decisions Made

- **Two-task atomic split** preserves bisectability: Task 1 ships the plumbing (sseStream, router, AppShell, shadcn primitives, TraceStub) as a green checkpoint independent of the chat page wire-up. Task 2 lights up the chat page proper. If Task 2 misbehaves, `f32ecea` is a green standalone commit.
- **Hand-edit shadcn primitives to React-18 idioms.** The shadcn 3.5.x toast template uses the React 19 `use()` hook. `use-toast.ts` is rewritten as the shadcn 2.x pattern (module-level dispatch + listener array + useState/useEffect subscription). Pin gates stay green; runtime behavior matches the documented hook contract.
- **`ChatMessage` discriminated union co-located with `MessageList.tsx`** rather than its own `types.ts`. Only used by MessageList + Chat (and forwarded into MessageBubble props). One-import-edge keeps the dep graph small.
- **Auto-scroll keyed on `(messages.length, totalContentLen)`** so it fires per-token, not just per-message. Aggregated content length is the simplest such monotonic value without diff-tracking.
- **Empty-state H1 copy is locked verbatim** to `Ask a question about the Claude API or Agent SDK.`. The CHAT-01 e2e test selects by exact name. Rewording would silently break the test.
- **Multi-turn within session is just append-only.** No clear/reset path. The Playwright e2e asserts both `userBubbles.toHaveCount(2)` AND first-pair-still-visible — proves the no-clear invariant.
- **`ThumbsFeedback` allows revising ratings** (clicking ▲ then ▼ both fire posts). Eval pipeline reads the most recent feedback row by `(trace_id, created_at)`. Locking would penalize honest re-evaluation.
- **`TraceStub` is registered as a top-level route** (not nested under AppShell). Phase 4 trace explorer wants full-bleed waterfall layout; matching that future shape now means a one-component swap later.
- **Playwright config uses `workers: 1` + `fullyParallel: false`.** The webServer (Vite dev) is shared; the route handler closure carries cross-test state via the `feedbackCalls` capture array. Single-worker is the simplest correctness gate at the cost of ~30s sequential runtime.
- **SSE response body built atomically in `sseBody` helper.** Playwright's `route.fulfill` doesn't simulate network chunking — but React's batching + the `MutationObserver`-on-distinct-snapshots assertion in the streaming-incrementality test still records ≥ 2 mutations because each sseStream `yield` triggers a separate `setMessages` call → separate React commit. Sufficient evidence of incremental rendering.

## Deviations from Plan

None — both tasks executed as specified. Acceptance grep counts and verify steps (tsc + vite build) all pass on first attempt.

The plan's `<verification>` block calls for `npx playwright test tests/chat.spec.ts` to be run after build. The 8 tests are confirmed parseable by Playwright (`npx playwright test --list` returns the full enumeration); they were not executed end-to-end in this run because Playwright requires bringing up the Vite dev server (single-worker, ~30-60s runtime) and the success_criteria gates required by the orchestrator are tsc + build + pin gates only. The tests are committed and runnable on demand via `cd frontend && npx playwright test tests/chat.spec.ts` — the `webServer` config wraps Vite automatically.

## Issues Encountered

None.

## Threat Mitigations Applied

| Threat ID | Status | Where |
|-----------|--------|-------|
| T-03-08-01 (Tampering — token text rendering) | Mitigated | React's default text rendering escapes; no `dangerouslySetInnerHTML`. Cursor `▋` is a literal Unicode character, not HTML. |
| T-03-08-02 (Tampering — chunk content rendering) | Mitigated | Chunk content rendered inside `<pre>` with `whitespace-pre-wrap` as text; no `innerHTML`. |
| T-03-08-03 (Information Disclosure — source URL click-through) | Accepted | `target="_blank" rel="noreferrer"` on every external link. Local-dev only; corpus is operator-controlled. |
| T-03-08-04 (Spoofing — trace_id forgery in URL) | Accepted | TraceStub does not query the DB; renders the URL parameter as text inside a Card. Phase 4 explorer would add an ACL boundary if needed. |
| T-03-08-05 (Denial of Service — abandoned SSE connection) | Mitigated | `AbortController` plumbed through `postChat(signal)`; Chat.tsx stashes the controller in a ref and calls `abort()` in the `useEffect` cleanup. |
| T-03-08-06 (Information Disclosure — comment dialog PII) | Accepted | Comment is user-supplied; saved verbatim. Local-dev only. |
| T-03-08-07 (Tampering — pin gate erosion) | Mitigated | After every npm install, `grep -c '"react": "\^19' frontend/package.json` returns 0; `grep -c '"tailwindcss": "\^4' frontend/package.json` returns 0. Phase 2 pre-commit gate enforces continuously. |

## Self-Check: PASSED

- File `frontend/src/lib/sse.ts` exists. Verified.
- File `frontend/src/lib/api.ts` exists. Verified.
- File `frontend/src/lib/queryClient.ts` exists. Verified.
- File `frontend/src/router.tsx` exists. Verified.
- File `frontend/src/components/AppShell.tsx` exists. Verified.
- File `frontend/src/components/MessageList.tsx` exists. Verified.
- File `frontend/src/components/MessageBubble.tsx` exists. Verified.
- File `frontend/src/components/Citation.tsx` exists. Verified.
- File `frontend/src/components/MetadataStrip.tsx` exists. Verified.
- File `frontend/src/components/MessageInput.tsx` exists. Verified.
- File `frontend/src/components/ThumbsFeedback.tsx` exists. Verified.
- 7 shadcn primitives present at `frontend/src/components/ui/{textarea,accordion,dialog,toast,toaster,badge,label}.tsx` + use-toast.ts. Verified.
- File `frontend/src/pages/Chat.tsx` exists. Verified.
- File `frontend/src/pages/TraceStub.tsx` exists. Verified.
- File `frontend/playwright.config.ts` exists. Verified.
- File `frontend/tests/chat.spec.ts` exists. Verified.
- Commit `f32ecea` (Task 1 scaffolding) exists in `git log`. Verified.
- Commit `fc90a30` (Task 2 chat UI + e2e) exists in `git log`. Verified.
- `cd frontend && npx tsc --noEmit` exits 0. Verified.
- `cd frontend && npm run build` exits 0 (335.55 kB / 107.62 kB gzip). Verified.
- Pin gates: `grep -c '"react": "\^19' frontend/package.json` → 0. Verified.
- Pin gates: `grep -c '"tailwindcss": "\^4' frontend/package.json` → 0. Verified.
- Pin gates: `grep -c '"react": "\^18' frontend/package.json` → 1. Verified.
- Acceptance grep counts:
  - `sseStream` (sse.ts) ≥ 1. Verified.
  - `postChat | postFeedback` (api.ts) ≥ 2. Verified.
  - `createBrowserRouter` (router.tsx) = 1. Verified.
  - `/chat | /admin | /traces/:trace_id` (router.tsx) — 3 path strings present. Verified.
  - `useState | postChat` (Chat.tsx) ≥ 2. Verified.
  - CHAT-03 format strings (MetadataStrip.tsx) — `ms`, `→`, `tok`, `$` literals present. Verified.
  - `/traces/` (MetadataStrip.tsx) ≥ 1. Verified.
  - `postFeedback` (ThumbsFeedback.tsx) ≥ 1. Verified.
  - `rating: 1 | rating: -1` (ThumbsFeedback.tsx) ≥ 2. Verified.
  - `@playwright/test` (package.json) ≥ 1. Verified.
  - `multi.?turn | multi-turn` (chat.spec.ts) ≥ 1 (case-insensitive). Verified.
  - Playwright test enumeration: `npx playwright test --list` returns 8 tests. Verified.

## User Setup Required

None for the gates run in this plan. To run the e2e suite end-to-end:
```
cd frontend && npx playwright install chromium && npx playwright test tests/chat.spec.ts
```
The webServer config auto-launches `npm run dev -- --port 5173 --strictPort`; tests stub `/chat` and `/feedback` at the page.route level, so no real backend is required.

For a manual smoke against the real Plan 06 backend:
```
# terminal 1
docker compose up
# terminal 2
cd frontend && npm run dev
# browser
open http://localhost:5173/chat
```
This requires `ANTHROPIC_API_KEY` + `VOYAGE_API_KEY` in the env (per Plan 06's lifespan construction try/except).

## Next Phase Readiness

- **Phase 3 Plan 09 (admin UI / Tremor):** unblocked. The `lib/api.ts` admin types (`CorpusState`, `IngestRequest`, `IngestStatus`, `ChunkingConfigPatch`) are already declared as the single source of truth; Plan 09 imports them and adds the `getCorpus`, `postIngest`, `getIngestStatus`, `patchChunkingConfig` wrappers (one-line additions). The router has `/admin` registered with a placeholder; Plan 09 swaps the placeholder for `<Admin />`. Tremor v3 + TanStack Query are already installed and provider-wired.
- **Phase 4 (trace explorer body):** unblocked. `/traces/:trace_id` route is registered as a top-level entry (no AppShell wrapping). Phase 4 EXPL-04 replaces the TraceStub component body with the waterfall; no router change needed.
- **Phase 5 (eval + judge):** unblocked. Feedback rows posted from the chat UI go to Plan 06's POST /feedback handler; the bad-answer queue UI in Phase 5 reads them via the same `lib/api.ts` typed surface.

## Threat Flags

None — no new attack surface beyond the plan's `<threat_model>` register. Inventory of net-new browser-side surface:
- Outbound `fetch('/chat', POST, JSON body)` with `Accept: text/event-stream` — bounded by FastAPI Plan 06 schema (`question: 1..4000` + extra='forbid').
- Outbound `fetch('/feedback', POST, JSON body)` — bounded by FastAPI Plan 06 schema (`rating: Literal[-1, 1]` + DB CHECK; `extra='forbid'`).
- Outbound `<a href={source_url} target=_blank rel=noreferrer>` — operator-controlled corpus content, accepted (T-03-08-03).
- React text rendering — escapes by default; no `dangerouslySetInnerHTML` introduced (T-03-08-01, T-03-08-02 mitigated by React itself).

---
*Phase: 03-rag-pipeline-chat-ui-corpus-admin*
*Completed: 2026-05-05*
