---
phase: 03-rag-pipeline-chat-ui-corpus-admin
artifact: UI-SPEC
status: draft
authored: 2026-05-04
inputs:
  - .planning/phases/03-rag-pipeline-chat-ui-corpus-admin/03-RESEARCH.md
  - .planning/phases/02-skeleton-infrastructure/02-05-SUMMARY.md
  - .planning/REQUIREMENTS.md
  - CLAUDE.md
covers-requirements:
  - CHAT-01
  - CHAT-02
  - CHAT-03
  - CHAT-04
  - CHAT-05
  - ADMN-01
  - ADMN-02
  - ADMN-03
  - ADMN-04
---

# Phase 3 UI Design Contract

**Goal:** A streaming chat page with citations, per-message metadata, and thumbs feedback; an admin page that surfaces corpus state and triggers re-indexing — all built on the Phase 2 Vite + React 18 + Tailwind v3 + shadcn/ui (Zinc) skeleton with Tremor v3 added for KPI cards and tables.

This contract is authoritative for executor implementation in Phase 3. Where research and the orchestrator brief disagreed (chat at `/` vs `/chat`), the research doc wins (`/chat`) because it is the contract the backend `POST /chat` handler is written against. The root `/` route redirects to `/chat`.

---

## 1. Scope & Pages

**Pages added this phase:**

| Path              | Page                  | Requirement(s) | File                                   |
|-------------------|-----------------------|----------------|----------------------------------------|
| `/`               | Redirect → `/chat`    | (none — UX)    | `frontend/src/router.tsx`              |
| `/chat`           | Chat (streaming)      | CHAT-01..05    | `frontend/src/pages/Chat.tsx`          |
| `/admin`          | Corpus admin          | ADMN-01..04    | `frontend/src/pages/Admin.tsx`         |
| `/traces/:trace_id` | Trace stub          | CHAT-05 (link target) | `frontend/src/pages/TraceStub.tsx` |

**Routing:** `react-router-dom@^6.27` (already installed in Phase 2; first use this phase). `BrowserRouter` lives in `main.tsx`; route table in `frontend/src/router.tsx`. `App.tsx` is replaced — the Phase-2 hello Card moves to `/chat`'s empty state (see §3 Empty state).

**Layout shell:** `AppShell` component (`frontend/src/components/AppShell.tsx`) renders the top nav and an `<Outlet />`. Used as the layout route wrapping `/chat` and `/admin`; the trace stub does not use the shell (it's a destination page with its own minimal layout).

**Out of scope this phase:** dark mode, mobile-first responsive polish, multi-thread persistence, drag-and-drop URL ingest, trace explorer body, dashboard, bad-answer queue. See §12.

---

## 2. Design System

### 2.1 Foundation (already wired in Phase 2)

| Element        | Source                                | Status                            |
|----------------|---------------------------------------|-----------------------------------|
| shadcn baseColor | `frontend/components.json` `"baseColor": "zinc"` | Wired, do not change       |
| CSS variables  | `frontend/src/index.css` (Zinc light palette) | Wired                       |
| `cn()` helper  | `frontend/src/lib/utils.ts`           | Wired (twMerge + clsx)            |
| Path alias     | `@/*` → `frontend/src/`                | Wired (tsconfig + vite.config)    |
| Type scale     | shadcn defaults via Tailwind          | Adopt as-is, no overrides         |
| Spacing scale  | Tailwind defaults (4px base, multiples of 4) | Adopt as-is, no overrides    |
| Radius         | shadcn `--radius: 0.5rem`              | Adopt as-is                       |
| Icons          | `lucide-react@^0.460`                 | Wired, use throughout             |

### 2.2 New libraries this phase

| Library                 | Version   | Status                    | Use                                   |
|-------------------------|-----------|---------------------------|---------------------------------------|
| `@tremor/react`         | `^3.18`   | Installed Phase 2; first use | KPI Cards, Metric, Table on `/admin` |
| `@tanstack/react-query` | `^5`      | Installed Phase 2; first use | Server state for `/admin` GETs + ingest polling |
| `react-router-dom`      | `^6.27`   | Installed Phase 2; first use | Multi-route                          |
| `date-fns`              | `^3` (add) | New dep this phase        | `formatRelative`, `format` for `last_indexed_at` |

No Zustand / Redux / Jotai / axios / ky additions — local React state for chat streaming, native `fetch` for the SSE call, TanStack Query for admin GETs.

### 2.3 Color contract (60 / 30 / 10)

The Zinc palette gives us a near-monochrome base. Tremor color tokens supply state hues. We use them sparingly and reservedly.

| Role             | Share | Token / Class                          | Reserved for                                                 |
|------------------|------:|----------------------------------------|--------------------------------------------------------------|
| Dominant surface | 60%   | `bg-background` (`zinc-50` light)      | Page background, body region, scroll region                  |
| Secondary surface | 30%  | `bg-card` / `bg-muted` (`white` / `zinc-100`) | Cards, message bubbles, nav bar, table rows           |
| Accent           | 10%   | `bg-primary` (`zinc-900`) + `text-primary-foreground` | Primary CTA only: "Send" button, "Re-index corpus" button |
| Success          | trace | Tremor `emerald`                       | Reindex success toast border, "succeeded" status badge       |
| Warning          | trace | Tremor `amber`                         | Empty-corpus banner border, "running" ingest progress bar    |
| Destructive      | trace | Tremor `rose` / shadcn `destructive`   | Error toast, "failed" ingest status, retry-button border     |
| Info             | trace | Tremor `blue`                          | Citation chip background, "queued" badge                     |
| Neutral text     | base  | `text-foreground` / `text-muted-foreground` | All body and label text                                 |

**Rules:**
- Accent (`bg-primary`) is **only** on primary CTAs ("Send", "Re-index corpus", "Submit feedback"). Secondary actions use `variant="outline"` or `variant="ghost"` on shadcn `Button`.
- State colors (emerald/amber/rose/blue) appear **only** in status badges, toast borders, and Tremor chart tokens — never as page-level surfaces.
- Dark mode is deferred (Phase 7 polish). The Zinc CSS variables in `index.css` already include the dark palette; we simply do not add a theme toggle this phase.

### 2.4 Typography contract

shadcn defaults are sufficient. We declare explicit roles for executor reference:

| Role          | Class                                | Pixel size | Weight | Line-height | Used in                               |
|---------------|--------------------------------------|-----------:|-------:|------------:|---------------------------------------|
| H1 (page)     | `text-2xl font-semibold tracking-tight` | 24px | 600 | 1.25 | Admin page heading: "Corpus"          |
| H2 (section)  | `text-lg font-semibold`              | 18px | 600 | 1.4  | Card group label, "Cited sources"     |
| Body          | `text-sm`                            | 14px | 400 | 1.5  | Message text, table cells, form inputs|
| Label         | `text-xs font-medium uppercase tracking-wide text-muted-foreground` | 12px | 500 | 1.4 | KPI card titles, metadata strip labels |
| Code (chunks) | `font-mono text-xs`                  | 12px | 400 | 1.6 | Citation accordion chunk content      |

**Two weight rule:** 400 (regular) and 600 (semibold) only. No 500 except in micro-Label role above (uppercase tracking compensates). No 700/800.

### 2.5 Spacing contract

Tailwind defaults — strict multiples of 4. Common values:

| Use                  | Class    | px |
|----------------------|----------|---:|
| Tight in-component   | `p-2` / `gap-2` | 8 |
| Component padding    | `p-4` / `gap-4` | 16 |
| Section gap          | `space-y-6` | 24 |
| Page outer padding   | `p-8`     | 32 |
| Page max-width       | `max-w-4xl mx-auto` | 56rem (chat); `max-w-7xl` for admin grid |

---

## 3. Chat Page (`/chat`) — CHAT-01..05

### 3.1 Wireframe

```
┌──────────────────────────────────────────────────────────────────┐
│  tracer-ai                              Chat │ Admin             │  ← AppShell nav
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Ask a question about the Claude API or Agent SDK.               │  ← H1 + sub
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                       [user]               │  │  ← right-aligned
│  │  How does Claude tool use work?                            │  │     user bubble
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │  ← left-aligned
│  │ [bot]  Claude tool use lets the model call functions [1]   │  │     assistant bubble
│  │        you define. The model decides when to invoke a tool │  │
│  │        based on the conversation [2]. ▋                    │  │  ← streaming cursor
│  │                                                            │  │
│  │  ▾ Sources (2)                                             │  │  ← Accordion (closed)
│  │                                                            │  │
│  │  • 2810ms  • 1240→96 tok  • $0.0043  ▲ ▼  trace ↗         │  │  ← MetadataStrip
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Ask a question…                                            │  │  ← Textarea
│  │                                                            │  │     auto-grow 2-6 rows
│  └────────────────────────────────────────────────────────────┘  │
│                                                  [    Send    ]  │  ← primary Button
└──────────────────────────────────────────────────────────────────┘
```

When Sources accordion is open:

```
│  ▾ Sources (2)                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ [1] claude-docs/tool-use · Tool use overview · 0.87      │    │  ← header row
│  │     Tool use lets you give Claude access to client-side  │    │
│  │     functions. When Claude decides a tool would help,    │    │  ← chunk content
│  │     it returns a tool_use block with arguments…          │    │     (font-mono text-xs)
│  │     ↗ docs.anthropic.com/en/api/tool-use                 │    │  ← source_url link
│  └──────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ [2] claude-docs/messages · Tool result blocks · 0.81     │    │
│  │     ...                                                  │    │
│  └──────────────────────────────────────────────────────────┘    │
```

### 3.2 Component inventory

| Component                  | File                                              | Purpose                                                                 |
|----------------------------|---------------------------------------------------|-------------------------------------------------------------------------|
| `Chat`                     | `frontend/src/pages/Chat.tsx`                     | Page; owns `messages: Message[]`; opens SSE on submit                   |
| `MessageList`              | `frontend/src/components/MessageList.tsx`         | Scrollable region, auto-scroll-to-bottom on new content                 |
| `MessageBubble`            | `frontend/src/components/MessageBubble.tsx`       | One bubble; `role: "user" | "assistant"`; renders streaming cursor      |
| `Citation` (inline)        | `frontend/src/components/Citation.tsx`            | Inline `[N]` superscript marker, click scrolls to accordion entry       |
| `CitationAccordion`        | `frontend/src/components/Citation.tsx` (same file) | shadcn Accordion listing each cited chunk (header + content + link)    |
| `MetadataStrip`            | `frontend/src/components/MetadataStrip.tsx`       | Small badges: latency, tokens, cost, thumbs, trace link                 |
| `ThumbsFeedback`           | `frontend/src/components/ThumbsFeedback.tsx`      | ▲ ▼ buttons; ▼ opens shadcn Dialog with comment Textarea                |
| `MessageInput`             | `frontend/src/components/MessageInput.tsx`        | Textarea + Send button; Enter sends, Shift+Enter newline; disabled while streaming |
| `EmptyState`               | inline in `Chat.tsx`                              | Subtitle + 3 example chips                                              |
| `lib/sse.ts`               | `frontend/src/lib/sse.ts`                         | `sseStream()` async generator over fetch ReadableStream                 |
| `lib/api.ts`               | `frontend/src/lib/api.ts`                         | `postChat`, `postFeedback` typed wrappers                               |

### 3.3 Streaming protocol (CHAT-02)

The frontend sends `POST /chat` with a JSON body and consumes a `text/event-stream` response. SSE events match the research-doc wire (§3 / `lib/sse.ts`):

| Event name | Data shape (JSON)                                                                             | Frontend behavior                                          |
|------------|------------------------------------------------------------------------------------------------|------------------------------------------------------------|
| `token`    | `{ "text": string }`                                                                           | Append `text` to in-progress assistant message content     |
| `final`    | `{ trace_id, cited_chunks, latency_ms, input_tokens, output_tokens, estimated_cost_usd }`      | Close the message; populate Sources + MetadataStrip; remove cursor |
| `error`    | `{ message: string }` (proposed; if backend doesn't emit, surface via fetch reject)            | Convert message to error variant, show retry              |

**Backend wire (research-authoritative):** the backend emits `event: token` and `event: final`. The optional `error` event is added if/when the backend signals mid-stream errors; otherwise frontend treats fetch network errors and `!res.ok` as the failure path.

**Cursor:** while streaming, `MessageBubble` appends `▋` (`▋`) to the rendered text, animated via `motion-safe:animate-pulse`. Removed when `final` arrives.

### 3.4 Component contracts

#### `Chat.tsx`

```tsx
type Message =
  | { role: "user"; id: string; content: string }
  | {
      role: "assistant";
      id: string;
      content: string;        // streamed; updated as token events arrive
      streaming: boolean;     // true until final event arrives
      trace_id?: string;
      cited_chunks?: Citation[];
      metadata?: { latency_ms: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number };
      error?: string;
    };

// Owns local state — NO TanStack Query for the chat stream itself
const [messages, setMessages] = useState<Message[]>([]);
const [streaming, setStreaming] = useState(false);
```

Layout: `<div className="flex flex-col h-[calc(100vh-4rem)] max-w-4xl mx-auto px-4">` — header, scrollable list, sticky input. The `4rem` reserves the AppShell nav.

#### `MessageBubble.tsx`

User bubble:
```tsx
<div className="flex justify-end mb-4">
  <div className="bg-primary text-primary-foreground rounded-lg px-4 py-2 max-w-[80%] text-sm">
    {content}
  </div>
</div>
```

Assistant bubble:
```tsx
<div
  role="article"
  aria-live={streaming ? "polite" : undefined}
  className="flex justify-start mb-6"
>
  <div className="bg-card border border-border rounded-lg px-4 py-3 max-w-[85%] w-full text-sm">
    <div className="prose prose-sm prose-zinc max-w-none">
      {/* streamed content with inline [N] markers */}
    </div>
    {!streaming && cited_chunks?.length > 0 && <CitationAccordion chunks={cited_chunks} />}
    {!streaming && metadata && <MetadataStrip {...metadata} traceId={trace_id} />}
  </div>
</div>
```

Error variant: same skeleton, `border-rose-300 bg-rose-50` and a "Retry" button that re-submits the last user message.

#### `Citation.tsx` — inline marker + accordion

Inline:
```tsx
<sup>
  <a href={`#cite-${idx}`} className="text-blue-600 hover:underline px-0.5">
    [{idx}]
  </a>
</sup>
```

Accordion (uses shadcn `Accordion` — added this phase, see §11):
```tsx
<Accordion type="single" collapsible className="mt-3 border-t border-border pt-2">
  <AccordionItem value="sources">
    <AccordionTrigger className="text-xs font-medium uppercase tracking-wide">
      Sources ({chunks.length})
    </AccordionTrigger>
    <AccordionContent>
      {chunks.map((c) => (
        <div id={`cite-${c.idx}`} key={c.idx} className="mb-3 p-3 bg-muted rounded border border-border">
          <div className="text-xs font-medium mb-1">
            [{c.idx}] {c.doc_id} · {c.section_title} · {c.score.toFixed(2)}
          </div>
          <pre className="font-mono text-xs whitespace-pre-wrap text-muted-foreground">{c.content}</pre>
          {c.source_url && (
            <a href={c.source_url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 hover:underline mt-1 inline-block">
              ↗ {c.source_url}
            </a>
          )}
        </div>
      ))}
    </AccordionContent>
  </AccordionItem>
</Accordion>
```

#### `MetadataStrip.tsx`

```tsx
<div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 pt-2 border-t border-border text-xs text-muted-foreground">
  <span>{latency_ms}ms</span>
  <span>·</span>
  <span>{input_tokens}→{output_tokens} tok</span>
  <span>·</span>
  <span>${estimated_cost_usd.toFixed(4)}</span>
  <ThumbsFeedback traceId={traceId} />
  <Link to={`/traces/${traceId}`} className="hover:underline ml-auto">trace ↗</Link>
</div>
```

The latency / token / cost text strings exactly match CHAT-03's e2e regex assertions:
- `/\d+\s*ms/` ← `2810ms`
- `/\d+\s*→\s*\d+\s*tok/` ← `1240→96 tok`
- `/\$\d+\.\d+/` ← `$0.0043`

#### `ThumbsFeedback.tsx`

▲ button: `POST /feedback` with `{trace_id, rating: 1, comment: null}` immediately. Visual state: filled vs hollow.

▼ button: opens shadcn `Dialog` with title "What went wrong?", a Textarea (max 1000 chars, `text-sm`), Cancel + Submit buttons. Submit `POST /feedback` with `{trace_id, rating: -1, comment}`. Both rating and comment are required by FBCK-01's schema.

State after submit: thumbs button stays in selected state; show `Toast` "Feedback recorded — thanks!"

#### `MessageInput.tsx`

```tsx
<form onSubmit={handleSubmit} className="sticky bottom-0 bg-background border-t border-border p-4">
  <div className="flex gap-2 items-end max-w-4xl mx-auto">
    <Textarea
      value={input}
      onChange={(e) => setInput(e.target.value)}
      onKeyDown={handleKeyDown}  // Enter submits, Shift+Enter inserts newline
      placeholder="Ask a question…"
      rows={2}
      className="resize-none flex-1"
      disabled={streaming}
      aria-label="Ask a question about the Claude API"
    />
    <Button type="submit" disabled={streaming || !input.trim()} className="self-end">
      {streaming ? "Streaming…" : "Send"}
    </Button>
  </div>
</form>
```

`Textarea` is a new shadcn component added this phase (§11).

### 3.5 Empty state

When `messages.length === 0`:

```tsx
<div className="flex flex-col items-center justify-center text-center py-16">
  <h1 className="text-2xl font-semibold tracking-tight mb-2">
    Ask a question about the Claude API or Agent SDK.
  </h1>
  <p className="text-sm text-muted-foreground mb-6">
    Powered by retrieval over the official Claude API + Agent SDK docs.
  </p>
  <div className="flex flex-wrap gap-2 justify-center max-w-2xl">
    {EXAMPLES.map((q) => (
      <Button
        key={q}
        variant="outline"
        size="sm"
        onClick={() => submit(q)}
      >
        {q}
      </Button>
    ))}
  </div>
</div>
```

Examples (copywriting locked):
1. `How does prompt caching work?`
2. `What is tool use?`
3. `Show me a streaming example.`

### 3.6 Loading + Error states

| State                         | Rendering                                                                               |
|-------------------------------|-----------------------------------------------------------------------------------------|
| Idle (no messages)            | Empty state above                                                                       |
| Streaming (first token)       | Assistant bubble with cursor `▋` only (no metadata yet)                                |
| Streaming (mid-response)      | Assistant bubble with content so far + cursor                                          |
| Stream complete               | Bubble drops cursor, accordion + metadata strip render in                              |
| Network error / 500           | Error variant bubble (rose-tinted), Retry button, error message text below             |
| `POST /feedback` failure      | Toast: "Couldn't record feedback. Please retry." (rose toast variant)                  |

---

## 4. Admin Page (`/admin`) — ADMN-01..04

### 4.1 Wireframe

```
┌──────────────────────────────────────────────────────────────────┐
│  tracer-ai                              Chat │ Admin             │
├──────────────────────────────────────────────────────────────────┤
│  Corpus                                                          │  ← H1
│                                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │ DOCS    │ │ CHUNKS  │ │ EMBEDDING MODEL │ │ LAST INDEXED    │ │  ← 4× Tremor Card
│  │   52    │ │ 4,381   │ │ voyage-code-3   │ │ 12 minutes ago  │ │
│  │ documents│ │ chunks  │ │ @2025-09        │ │ May 4, 2026 at  │ │
│  │ indexed │ │         │ │                 │ │ 11:42 AM        │ │
│  └─────────┘ └─────────┘ └─────────────────┘ └─────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────┐  ┌────────────────┐  │
│  │ Documents                              │  │ Actions        │  │
│  │ ┌───────────┬──────────┬────────┬────┐ │  │ ┌────────────┐ │  │
│  │ │ Doc       │ Section  │ Chunks │... │ │  │ │ Re-index   │ │  │
│  │ ├───────────┼──────────┼────────┼────┤ │  │ │  corpus    │ │  │  ← primary
│  │ │ auth      │ auth     │ 84     │... │ │  │ └────────────┘ │  │
│  │ │ messages  │ messages │ 211    │... │ │  │                │  │
│  │ │ tool-use  │ tools    │ 92     │... │ │  │ Ingest URLs    │  │
│  │ │ ...                                │ │  │ ┌────────────┐ │  │
│  │ └────────────────────────────────────┘ │  │ │ url 1…     │ │  │
│  └────────────────────────────────────────┘  │ │ url 2…     │ │  │
│                                              │ └────────────┘ │  │
│                                              │ [ Add URLs   ] │  │
│                                              │                │  │
│                                              │ Chunking       │  │
│                                              │ size:    [900] │  │
│                                              │ overlap: [100] │  │
│                                              │ [Save settings]│  │
│                                              └────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

When ingest is running:

```
│  Re-index running…                                              │
│  ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░  35%                            │  ← Tremor ProgressBar
│  18 / 52 docs · 1,243 chunks written · 45s elapsed              │
│  [Cancel] (disabled in v1; informational)                       │
```

### 4.2 Component inventory

| Component                  | File                                                      | Purpose                                            |
|----------------------------|-----------------------------------------------------------|----------------------------------------------------|
| `Admin`                    | `frontend/src/pages/Admin.tsx`                            | Page orchestrator                                  |
| `CorpusCards`              | `frontend/src/components/CorpusCards.tsx`                 | 4-up Tremor Card grid (KPIs)                       |
| `DocList`                  | `frontend/src/components/DocList.tsx`                     | Tremor Table of docs                               |
| `ReindexButton`            | `frontend/src/components/ReindexButton.tsx`               | Triggers + polls ingest job                        |
| `IngestProgress`           | `frontend/src/components/IngestProgress.tsx`              | Tremor ProgressBar + counter row                   |
| `UrlIngestForm`            | `frontend/src/components/UrlIngestForm.tsx`               | Textarea (one URL per line) + submit               |
| `ChunkingConfigForm`       | `frontend/src/components/ChunkingConfigForm.tsx`          | Two number inputs + save button                    |
| `lib/api.ts` (extended)    | `frontend/src/lib/api.ts`                                 | `getCorpus`, `postIngest`, `getIngestStatus`, `patchChunkingConfig` |
| `lib/queryClient.ts`       | `frontend/src/lib/queryClient.ts`                         | TanStack Query client + `<QueryClientProvider>`    |

### 4.3 KPI cards (ADMN-01)

Tremor `Card` + `Metric` + `Text`. Grid: `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4`.

| Card               | Metric (top)                                  | Text (sub)                                                           |
|--------------------|-----------------------------------------------|----------------------------------------------------------------------|
| Documents          | `{doc_count}`                                  | `documents indexed` (or `no documents yet — run re-index` if 0)      |
| Chunks             | `{chunk_count.toLocaleString()}`               | `chunks` (or `—` if 0)                                               |
| Embedding model    | `{embedding_model}` (text-base override)       | `{embedding_model_version}` (or `—` if no corpus)                    |
| Last indexed       | `{formatRelative(last_indexed_at, new Date())}` | `{format(last_indexed_at, "PPpp")}` (or `never indexed` if null)    |

Card titles are `<Title>` (Tremor) — uppercase tracking-wide muted text.

### 4.4 Doc list (ADMN-01)

Tremor `Table` (zebra rows native via `striped`). Columns:

| Column          | Source                       | Format                       |
|-----------------|------------------------------|------------------------------|
| Doc ID          | `doc.id`                     | `text-sm font-mono`          |
| Section         | `doc.doc_section`            | shadcn `Badge` variant=`secondary` |
| Chunks          | `doc.chunk_count`            | right-aligned number         |
| Source          | `doc.source_url`             | external-link icon + truncated URL on hover |
| Last ingested   | `doc.ingested_at`            | `formatRelative()`           |

Sort: default by `doc.id` ascending. No client-side filter / search this phase (defer to Phase 7 polish if needed).

### 4.5 Re-index button (ADMN-02)

States — encoded as the `ReindexButton`'s internal state machine fed by TanStack Query:

| State        | Button label              | Disabled? | Variant                |
|--------------|---------------------------|-----------|------------------------|
| `idle`       | `Re-index corpus`         | no        | `default` (primary)    |
| `confirming` | `Click again to confirm`  | no        | `default` + 3s timeout |
| `running`    | `Indexing…`               | yes       | `default` + Loader icon spinning |
| `done`       | `Re-index complete`       | no (re-arm to idle in 3s) | `default`        |
| `error`      | `Re-index failed — retry` | no        | `destructive`          |

**Confirmation:** the `confirming` state guards against accidental clicks. First click moves to `confirming`; second click within 3s fires `POST /admin/ingest`. After 3s of no second click, returns to `idle`. **No modal dialog** for the primary re-index button — the two-tap pattern is lighter and matches research-doc intent (no auth, single-user local). The URL ingest form's submit goes straight to confirm-then-fire (single tap, since URL list itself is the deliberate input).

**Polling:** on `running`, `useQuery({ queryKey: ['ingest', jobId], queryFn: getIngestStatus, refetchInterval: 2000, enabled: !!jobId })`. Stop polling when `status ∈ {succeeded, failed}`. On done: invalidate `['corpus']` so the four cards refresh; show success toast `Reindex complete — {chunks_written} chunks written.`

**Progress UI** (`IngestProgress`): Tremor `ProgressBar value={progress * 100} color="amber"` plus a status row showing `{docs_processed} / {docs_total} docs · {chunks_written.toLocaleString()} chunks · {elapsed} elapsed`. Sits inline below the Re-index button in the action panel; not a modal.

### 4.6 URL ingest form (ADMN-04)

```tsx
<form onSubmit={handleSubmit}>
  <Label htmlFor="urls">Ingest URLs</Label>
  <Textarea
    id="urls"
    value={text}
    onChange={(e) => setText(e.target.value)}
    placeholder="https://docs.anthropic.com/en/api/messages&#10;https://docs.anthropic.com/en/api/auth"
    rows={4}
    className="font-mono text-xs"
  />
  <p className="text-xs text-muted-foreground mt-1">One URL per line. Must start with http:// or https://.</p>
  {error && <p className="text-xs text-rose-600 mt-1">{error}</p>}
  <Button type="submit" variant="outline" size="sm" className="mt-2" disabled={!text.trim()}>Add URLs</Button>
</form>
```

Validation: client-side regex `^https?://` per line; on failure surface "Line {N}: not a URL" inline (matching ADMN-04 e2e expectation). Server-side Pydantic re-validates and may return 422 — surface server message in same slot.

### 4.7 Chunking config form (ADMN-03)

Two `Input type="number"` fields with `min` / `max`:
- `chunk_size`: min 100, max 4000, step 50, default `900`
- `overlap`: min 0, max 500, step 10, default `100`

Help text: `New values apply on the next re-index.`

Submit: `PATCH /admin/chunking-config` via TanStack Query mutation. On success: success toast "Chunking settings saved. They'll apply on the next re-index." On error: form fields stay populated with attempted values; rose error text under field.

### 4.8 Empty corpus state (ADMN-01 first-boot path)

When `chunk_count === 0`:

- Banner above the cards (Tremor `Callout` color="amber"): `No corpus yet — run \`tracer-ai ingest --source claude-docs\` from the CLI, or click Re-index to ingest the default Claude docs source.`
- Cards still render (with `0`, `0`, `voyage-code-3`, `never indexed`)
- Doc list shows shadcn `Skeleton` rows (4 rows) with text "No documents indexed yet." centered

---

## 5. Trace Stub (`/traces/:trace_id`) — CHAT-05

Phase 3 ships only the route target so per-message trace links don't 404. Phase 4 replaces the body.

```tsx
// frontend/src/pages/TraceStub.tsx
export function TraceStub() {
  const { trace_id } = useParams<{ trace_id: string }>();
  return (
    <div className="max-w-2xl mx-auto p-8">
      <Link to="/chat" className="text-sm text-muted-foreground hover:underline mb-4 inline-block">
        ← Back to chat
      </Link>
      <Card>
        <CardHeader>
          <CardTitle>Trace</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-2">
            The trace explorer ships in Phase 4. This page reserves the route so chat messages can link forward.
          </p>
          <p className="text-xs font-mono bg-muted px-2 py-1 rounded inline-block">
            trace_id: {trace_id}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
```

This satisfies CHAT-05's "link present + non-404" e2e assertion. No nav (the back link is sufficient).

---

## 6. Layout shell (`AppShell`)

```tsx
// frontend/src/components/AppShell.tsx
export function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="h-16 border-b border-border bg-card">
        <div className="max-w-7xl mx-auto h-full px-4 flex items-center gap-6">
          <Link to="/chat" className="font-semibold text-base tracking-tight">tracer-ai</Link>
          <nav className="flex gap-4 text-sm">
            <NavLink to="/chat" className={({isActive}) => isActive ? "font-medium" : "text-muted-foreground hover:text-foreground"}>
              Chat
            </NavLink>
            <NavLink to="/admin" className={({isActive}) => isActive ? "font-medium" : "text-muted-foreground hover:text-foreground"}>
              Admin
            </NavLink>
          </nav>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
```

- Light theme only (dark mode deferred to Phase 7).
- No logo image (text wordmark only).
- No external nav links, search, or user menu in v1.

---

## 7. State management decisions

| Surface                       | Mechanism                          | Rationale                                                       |
|-------------------------------|------------------------------------|-----------------------------------------------------------------|
| Streaming chat messages       | Local `useState<Message[]>`        | One page, one session in v1; no cross-component sharing needed  |
| Chat input draft              | Local `useState<string>`           | Same                                                             |
| `GET /admin/corpus`           | TanStack Query (`['corpus']`)      | Cache-on-mount, invalidate on ingest done                        |
| `GET /admin/ingest/{id}`      | TanStack Query w/ `refetchInterval: 2000`, `enabled: !!jobId` | Polling pattern; auto-stops when status final |
| `POST /admin/ingest`          | TanStack Query mutation            | Standard mutation; `onSuccess` stashes `jobId` and invalidates corpus |
| `PATCH /admin/chunking-config`| TanStack Query mutation            | Same                                                             |
| `POST /feedback`              | TanStack Query mutation            | Same                                                             |
| Chunking config initial values| TanStack Query (`['corpus']`) — derive from `corpus.chunking_config` if surfaced; else hardcoded 900/100 [DEFAULT — confirmable later: backend `GET /admin/corpus` may or may not include current chunking config; if not, the form initializes from constants and the backend's `PATCH` is the source of truth on next ingest] |

No Zustand / Redux / Jotai / Recoil — all inter-component state flows through React Router params, TanStack Query cache, or component-local state.

---

## 8. API wire contracts (frontend's view)

The frontend `lib/api.ts` exposes typed wrappers; the types below are the canonical TS shapes (research §3 + §5 are authoritative for backend).

```ts
// === POST /chat — text/event-stream ===
type ChatRequest = {
  question: string;       // 1..4000 chars (matches backend Pydantic bounds)
  thread_id?: string;     // reserved for future session tracking; phase 3 omits
};

type Citation = {
  idx: number;            // 1-based citation number
  doc_id: string;         // e.g., "claude-docs/tool-use"
  doc_section: string;    // one of the 12 canonical sections
  section_title: string;  // human-readable header text
  source_url: string;     // click-through link
  content: string;        // full chunk text
  score: number;          // [0,1] cosine similarity
};

type SSEFrame =
  | { event: "token"; data: { text: string } }
  | { event: "final"; data: {
      trace_id: string;
      cited_chunks: Citation[];
      latency_ms: number;
      input_tokens: number;
      output_tokens: number;
      estimated_cost_usd: number;
    } };

// === POST /feedback ===
type FeedbackRequest = {
  trace_id: string;
  rating: 1 | -1;
  comment?: string;       // required when rating === -1 (UX), optional in schema
};

// === GET /admin/corpus ===
type CorpusState = {
  doc_count: number;
  chunk_count: number;
  embedding_model: string;       // e.g. "voyage-code-3"
  embedding_model_version: string; // e.g. "voyage-code-3@2025-09"
  last_indexed_at: string | null;  // ISO 8601 or null if empty corpus
  docs: Array<{
    id: string;
    doc_section: string;
    source_url: string;
    chunk_count: number;
    ingested_at: string;
  }>;
  chunking_config?: {              // present per backend impl [DEFAULT — confirmable]
    chunk_size: number;
    overlap: number;
  };
};

// === POST /admin/ingest ===
type IngestRequest =
  | { source: "claude-docs" }
  | { urls: string[] };
type IngestResponse = { ingest_job_id: string; status: "queued" };

// === GET /admin/ingest/{job_id} ===
type IngestStatus = {
  status: "queued" | "running" | "succeeded" | "failed";
  started_at: string | null;
  finished_at: string | null;
  docs_processed: number;
  docs_total: number;          // [DEFAULT — confirmable: backend may compute & emit this]
  chunks_written: number;
  progress: number;            // 0..1
  error?: string;
};

// === PATCH /admin/chunking-config ===
type ChunkingConfigPatch = {
  chunk_size: number;          // 100..4000
  overlap: number;             // 0..500
};
type ChunkingConfig = ChunkingConfigPatch;
```

`lib/sse.ts` is the only module that hand-parses SSE; everything else uses the typed `lib/api.ts` wrappers over `fetch`.

---

## 9. Accessibility

| Concern         | Approach                                                                                          |
|-----------------|---------------------------------------------------------------------------------------------------|
| Keyboard        | Textarea has visible focus ring (shadcn default `focus-visible:ring-2 ring-ring`). Enter sends, Shift+Enter inserts newline. Tab order: nav → input → send → past assistant bubbles (thumbs, accordion trigger, trace link). |
| ARIA live       | Streaming assistant bubble: `aria-live="polite"` while `streaming === true`; removed on final to avoid re-announcement. |
| Roles           | Each assistant bubble: `role="article"`. The MessageList container: `role="log" aria-label="Chat history"`. |
| Color contrast  | shadcn Zinc base passes WCAG AA for body text on `bg-background`; primary CTA passes AA at 14px. State badges (Tremor emerald/amber/rose) pass AA on white card surface at default sizes. |
| Reduced motion  | Streaming-cursor pulse uses `motion-safe:animate-pulse` (disabled under `prefers-reduced-motion`). Tremor ProgressBar transitions are CSS-driven and respect `prefers-reduced-motion` via Tremor's defaults. |
| Form errors     | URL ingest validation errors are inline below the field with `aria-describedby` linking the textarea to the error `<p id>`. |
| Focus trap      | shadcn Dialog (thumbs-down comment) has built-in focus trap + ESC-to-close + restored focus on close. |
| Skip nav        | Out of scope this phase; only two pages. Add in Phase 7 polish. [DEFAULT — confirmable later] |
| Screen-reader-only labels | Trace link uses `<Link>trace ↗<span className="sr-only">View full trace for this answer</span></Link>` for context. |

---

## 10. Component inventory (delta from Phase 2)

| Component / File                               | Status    | Source           | Notes                                                       |
|------------------------------------------------|-----------|------------------|-------------------------------------------------------------|
| `frontend/src/components/ui/card.tsx`          | Existing  | shadcn (Phase 2) | Reused on chat empty state, trace stub                      |
| `frontend/src/components/ui/button.tsx`        | Existing  | shadcn (Phase 2) | Reused — needs `asChild` (Radix Slot) in Phase 3? **No** — research says only when Phase 3+ requires it; we don't compose Buttons as Links yet (use `<Link>` separately) |
| `frontend/src/components/ui/textarea.tsx`      | **New**   | shadcn `add textarea` | Chat input + URL ingest + feedback comment             |
| `frontend/src/components/ui/accordion.tsx`     | **New**   | shadcn `add accordion` | Citation expander                                      |
| `frontend/src/components/ui/dialog.tsx`        | **New**   | shadcn `add dialog`  | Thumbs-down comment dialog                               |
| `frontend/src/components/ui/toast.tsx` + `toaster.tsx` + `use-toast.ts` | **New** | shadcn `add toast` | Re-index status, feedback confirmations, errors |
| `frontend/src/components/ui/skeleton.tsx`      | **New**   | shadcn `add skeleton` | Empty doc list rows                                     |
| `frontend/src/components/ui/badge.tsx`         | **New**   | shadcn `add badge` | Doc-section pill, status badges                            |
| `frontend/src/components/ui/input.tsx`         | **New**   | shadcn `add input` | Chunking config number fields                              |
| `frontend/src/components/ui/label.tsx`         | **New**   | shadcn `add label` | Form labels                                                |
| `frontend/src/components/AppShell.tsx`         | **New**   | App-level        | Top nav + Outlet                                           |
| `frontend/src/components/MessageList.tsx`      | **New**   | App-level        | Chat history region                                        |
| `frontend/src/components/MessageBubble.tsx`    | **New**   | App-level        | User vs assistant variant                                  |
| `frontend/src/components/Citation.tsx`         | **New**   | App-level        | Inline marker + Accordion (one file)                       |
| `frontend/src/components/MetadataStrip.tsx`    | **New**   | App-level        | Latency / tokens / cost / thumbs / trace                   |
| `frontend/src/components/ThumbsFeedback.tsx`   | **New**   | App-level        | ▲ ▼ + comment dialog                                       |
| `frontend/src/components/MessageInput.tsx`     | **New**   | App-level        | Sticky input form                                          |
| `frontend/src/components/CorpusCards.tsx`      | **New**   | App-level (Tremor) | 4× `Card` + `Metric` + `Text`                            |
| `frontend/src/components/DocList.tsx`          | **New**   | App-level (Tremor) | `Table`, `TableHead`, `TableRow`, `TableCell`            |
| `frontend/src/components/ReindexButton.tsx`    | **New**   | App-level        | State machine (idle/confirming/running/done/error)         |
| `frontend/src/components/IngestProgress.tsx`   | **New**   | App-level (Tremor) | `ProgressBar` + counter row                              |
| `frontend/src/components/UrlIngestForm.tsx`    | **New**   | App-level        | URL textarea + submit                                      |
| `frontend/src/components/ChunkingConfigForm.tsx` | **New** | App-level        | Two number inputs                                          |
| `frontend/src/pages/Chat.tsx`                  | **New**   | App-level        | Replaces App.tsx hello card                                |
| `frontend/src/pages/Admin.tsx`                 | **New**   | App-level        | Page orchestrator                                          |
| `frontend/src/pages/TraceStub.tsx`             | **New**   | App-level        | CHAT-05 link target                                        |
| `frontend/src/lib/sse.ts`                      | **New**   | Lib              | Async generator over fetch ReadableStream                  |
| `frontend/src/lib/api.ts`                      | **New**   | Lib              | Typed wrappers (`postChat`, `postFeedback`, `getCorpus`, `postIngest`, `getIngestStatus`, `patchChunkingConfig`) |
| `frontend/src/lib/queryClient.ts`              | **New**   | Lib              | TanStack Query client + Provider                           |
| `frontend/src/router.tsx`                      | **New**   | Lib              | Route table                                                |
| `frontend/src/App.tsx`                         | **Modified** | Phase 2 → Phase 3 | Replace hello card with `<RouterProvider>` (or import router) |
| `frontend/src/main.tsx`                        | **Modified** | Phase 2 → Phase 3 | Wrap App with `QueryClientProvider` and `Toaster`        |

---

## 11. New shadcn components to add (this phase)

To be added via `npx shadcn add <component>` against the existing `components.json` (Zinc, no-CLI-runtime model). Hand-author if the CLI command pulls in React 19 / Tailwind v4 defaults — verify each against the Phase 2 pin gates after add.

| Component | Reason                                              | Used in                                            |
|-----------|-----------------------------------------------------|----------------------------------------------------|
| accordion | Citation source expansion                           | `Citation.tsx`                                     |
| textarea  | Chat input, URL list, feedback comment              | `MessageInput.tsx`, `UrlIngestForm.tsx`, `ThumbsFeedback.tsx` |
| dialog    | Thumbs-down comment modal                           | `ThumbsFeedback.tsx`                               |
| toast     | Re-index notifications, feedback confirmation, generic errors | App-level toaster wired in `main.tsx`    |
| skeleton  | Empty-corpus doc list placeholders                  | `DocList.tsx`                                      |
| badge     | Doc-section pill, ingest status                     | `DocList.tsx`, `ReindexButton.tsx`                 |
| input     | Chunking config number fields                       | `ChunkingConfigForm.tsx`                           |
| label     | Form labels                                         | All form components                                |

**Also new:** `@radix-ui/react-accordion`, `@radix-ui/react-dialog`, `@radix-ui/react-label`, `@radix-ui/react-toast`, `@radix-ui/react-slot` will land as transitive deps from `npx shadcn add`. Pin verification: after adding, re-run the Phase-2 negative-grep gates (`react@^19` → 0, `tailwindcss@^4` → 0). If any shadcn component template ships with React-19-only API (e.g. new `use()` hook), hand-edit to React 18 idioms.

**Tooltip:** considered for cost breakdown hover, deferred — the metadata strip text is already legible at 12px and a tooltip adds a Radix dep we don't otherwise need this phase. If executor finds the breakdown ambiguous, add `@radix-ui/react-tooltip` + `tooltip.tsx` shadcn primitive in a follow-up commit.

---

## 12. Out of scope (deferred)

| Feature                                 | Defer to        |
|-----------------------------------------|------------------|
| Multi-thread / cross-session chat history | Phase 7 polish (V2-AUTH-* family)    |
| Drag-and-drop URL ingest (file/markdown drop) | Phase 7 polish     |
| Per-doc delete from `/admin`            | Phase 7 polish     |
| Trace explorer body (waterfall, payload inspector) | Phase 4 (EXPL-04) |
| Quality drift dashboard / dashboard widgets | Phase 5 (DASH-01..06) |
| Bad-answer queue UI                     | Phase 5 (FBCK-03..07) |
| Dark mode toggle                        | Phase 7 polish     |
| Mobile / small-viewport layout polish   | Phase 7 polish (basic responsive only this phase: KPI cards collapse at `sm:`, chat is single-column; no breakpoint tuning beyond Tailwind defaults) |
| Tooltip on cost breakdown               | Add when executor signals ambiguity |
| Search / filter on doc list             | Phase 7 polish     |
| Cancel-in-flight ingest                 | Out of scope (no-op / informational only — research §5 in-process job lock is single-tenant) |
| MMR / cross-encoder rerank UI controls  | Phase 5 (eval-driven) |

---

## 13. Open questions

Items marked `[DEFAULT — confirmable later]` above:

1. **Does `GET /admin/corpus` surface `chunking_config`?** Frontend assumes it may; falls back to hardcoded 900/100 defaults if absent. Backend executor should confirm and either add the field (preferred) or accept that the form initializes from constants until next mutation.
2. **Does `GET /admin/ingest/{id}` emit `docs_total`?** The frontend's progress UI shows `{processed} / {total}` if `docs_total` is present; otherwise renders just `{processed} docs · {chunks_written} chunks`.
3. **Skip-navigation link** on AppShell deferred to Phase 7 polish; add if accessibility audit flags it.

---

*UI-SPEC authored: 2026-05-04 — Phase 3 RAG Pipeline + Chat UI + Corpus Admin*
