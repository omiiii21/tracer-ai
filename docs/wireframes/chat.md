# Wireframe: Chat

ASCII wireframe + component inventory for the `/chat` route — the main user-facing surface of tracer-ai. Self-referential by design: the demo corpus is the Anthropic Claude API + Claude Agent SDK documentation, so a sample query like "How do I use prompt caching with Claude?" both demonstrates the system and provides ground truth for evaluation.

## Route

`/chat`

## Bound API Endpoints

- `POST /chat` — submit a query; returns `ChatResponse{answer, cited_chunks, trace_id, latency_ms, input_tokens, output_tokens, estimated_cost_usd}` (see [api.md](../api.md)).
- `POST /feedback` — record thumbs-up (rating=1) immediately, or thumbs-down (rating=-1) with optional comment + `diagnosis_tag` after the Dialog confirms.

## Component Inventory

| Region | Component | Library |
|--------|-----------|---------|
| Page shell | `Card` | shadcn/ui |
| App header (title `tracer-ai` + nav links) | `Card` (variant=ghost) + `Button` (variant=link) | shadcn/ui |
| Message list (scrollable) | `ScrollArea` | shadcn/ui |
| User bubble | `Card` (variant=primary, right-aligned) | shadcn/ui |
| Assistant bubble | `Card` + `Badge` (latency_ms) + `Badge` (input_tokens / output_tokens) + `Badge` (estimated_cost_usd) | shadcn/ui |
| Citation chip (inline `[1]`, `[2]`) | `Tooltip` over chunk excerpt | shadcn/ui |
| Trace link `[trace ↗]` | `Button` (variant=ghost) -> `/dashboard/traces/{trace_id}` | shadcn/ui |
| Thumbs up | `Button` (variant=ghost, icon=ThumbsUp) | shadcn/ui |
| Thumbs down | `Button` (variant=ghost, icon=ThumbsDown) | shadcn/ui |
| Thumbs-down comment dialog | `Dialog` containing `Textarea` (comment) + `Select` (diagnosis_tag) + Submit `Button` | shadcn/ui |
| Diagnosis tag select (Phase 5 FBCK-05) | `Select` items: Retrieval / PromptAssembly / LLM / CorpusStale / Other | shadcn/ui |
| Input bar | `Textarea` (autosize, max=4000 chars per `ChatRequest.query` constraint) | shadcn/ui |
| Send button | `Button` (variant=primary, disabled when empty or loading) | shadcn/ui |
| Inline error | `Alert` (variant=destructive) + retry `Button` | shadcn/ui |

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  tracer-ai                              [Chat] [Dashboard] [Admin]       │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                                  ┌──────────────────────────────────┐    │
│                                  │ How do I use prompt caching      │    │
│                                  │ with Claude?                     │    │
│                                  └──────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │ Prompt caching lets you reuse a stable prefix [1] across     │        │
│  │ requests, reducing input-token cost by up to 90% and         │        │
│  │ latency by ~80% on cache hits [2].                           │        │
│  │                                                              │        │
│  │ [1] cache_control on system block       [2] prompt-caching/  │        │
│  │                                                              │        │
│  │ ⏱ 2810ms   🪙 1240→96 tokens   💲 $0.00432   [trace ↗]        │        │
│  │                                              [👍]   [👎]      │        │
│  └──────────────────────────────────────────────────────────────┘        │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐  [Send]    │
│  │ Ask another question...                                  │            │
│  └──────────────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────────────┘
```

Thumbs-down opens a modal (centered, dimmed backdrop):

```text
                  ┌────────────────────────────────────────────┐
                  │  What went wrong?                       ✕  │
                  ├────────────────────────────────────────────┤
                  │  Diagnosis tag (optional):                 │
                  │  [ Retrieval ▾ ]                           │
                  │                                            │
                  │  Comment (optional):                       │
                  │  ┌────────────────────────────────────┐    │
                  │  │ Wrong chunks — answer cites prompt │    │
                  │  │ caching but I asked about auth.    │    │
                  │  └────────────────────────────────────┘    │
                  │                                            │
                  │                       [Cancel]  [Submit]   │
                  └────────────────────────────────────────────┘
```

## States

| State | What shows |
|-------|------------|
| Loading | Skeleton assistant bubble (3 grey lines + 3 placeholder badges); input `Textarea` disabled; Send button shows spinner; previous bubbles remain visible. |
| Empty | No messages yet — center-aligned hint card: "Ask a question to start. Example: How do I authenticate to the Anthropic Messages API?" with a one-click `Button` that auto-fills the input. |
| Error | Inline `Alert` (variant=destructive) above the input bar showing `error_code` + `message` from `ErrorResponse`; retry `Button` re-issues the last `POST /chat`. The user bubble that triggered the error remains visible (so retry has context). |
| Populated | Stack of alternating user / assistant bubbles, latest at bottom; `ScrollArea` auto-scrolls on new message; latency / token / cost badges populated from `ChatResponse`; `[trace ↗]` link active. |

## Interactions

- **Submit query:** clicking `[Send]` (or pressing Enter without Shift) calls `POST /chat` with `{query, session_id?}`. While in flight, render the Loading state. On success, append the assistant bubble; on error, render the Error state.
- **Trace link:** clicking `[trace ↗]` navigates to `/dashboard/traces/{trace_id}` using the `trace_id` from the assistant bubble's `ChatResponse`.
- **Thumbs up:** clicking `[👍]` calls `POST /feedback` immediately with `{trace_id, rating: 1}` — no Dialog. On 2xx, swap the icon to a filled state and disable both feedback buttons.
- **Thumbs down:** clicking `[👎]` opens the comment `Dialog`. Submitting calls `POST /feedback` with `{trace_id, rating: -1, comment?, diagnosis_tag?}`. On 2xx, close Dialog and show a `Toast`; lock the feedback row.
- **Citation tooltip:** hovering a citation chip (`[1]`, `[2]`) reveals the chunk content via `Tooltip` (sourced from `ChatResponse.cited_chunks[i].content` — no extra fetch).
- **Auto-resize input:** the `Textarea` grows up to ~6 rows then scrolls. Hard cap = 4000 chars (matches `ChatRequest.query` Pydantic max_length).
