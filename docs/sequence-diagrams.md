# Sequence Diagrams

**Source-of-truth:** [`.planning/research/ARCHITECTURE.md`](../.planning/research/ARCHITECTURE.md) §"System Overview" (sync request path) and §"Anti-Patterns" (Pitfall #1, #3, #4).
**Resolves:** DSGN-03 (chat-request sequence diagram).
**Authored:** 2026-05-04. **Renderer:** GitHub-native Mermaid — no `autonumber`, uniform `participant` declarations only (mixing `actor` and `participant` causes silent render failure on GitHub per `01-RESEARCH.md` Artifact 4 gotchas).

This document shows the runtime data flow for a single `POST /chat` request — both the synchronous request path that returns the answer to the browser, AND the asynchronous evaluation branch dispatched via FastAPI `BackgroundTasks` after response flush. The two phases are visually separated by `Note over` blocks. **Critical design contract** (Pitfall #1): the OTel context snapshot must be captured **before** `root.end()`, otherwise the `rag.eval` span orphans as a new trace root rather than attaching as a child of `rag.request`. This is encoded as a `Note over FastAPI,Tracer` callout in the diagram and **must be honored** by Phase 4 TRCR-04 wiring.

## POST /chat — sync request path + async eval branch

```mermaid
sequenceDiagram
  participant Browser
  participant FastAPI
  participant Pipeline
  participant Tracer
  participant Anthropic
  participant BackgroundTasks
  participant Judge
  participant Postgres

  Note over Browser,Postgres: Phase 1 — sync request path

  Browser->>FastAPI: POST /chat {query}
  FastAPI->>Tracer: start_span("rag.request") -> root
  FastAPI->>Pipeline: run(query, root_ctx)

  Pipeline->>Tracer: start_span("rag.retrieve")
  Pipeline->>Postgres: vector_search(query_embedding, top_k=5)
  Postgres-->>Pipeline: chunks[5]
  Pipeline->>Tracer: end_span("rag.retrieve") + write attrs

  Pipeline->>Tracer: start_span("rag.prompt_assemble")
  Pipeline->>Pipeline: assemble_prompt(chunks, query)
  Pipeline->>Tracer: end_span("rag.prompt_assemble") + payload

  Pipeline->>Tracer: start_span("rag.llm_call")
  activate Anthropic
  Pipeline->>Anthropic: messages.create(model="claude-sonnet-4-5-20250929", prompt)
  Anthropic-->>Pipeline: answer + usage
  deactivate Anthropic
  Pipeline->>Tracer: end_span("rag.llm_call") + payload

  Pipeline-->>FastAPI: ChatResponse{answer, cited_chunks, trace_id, ...}

  Note over FastAPI,Tracer: Snapshot otel_context.get_current() BEFORE root.end() — omitting this orphans the rag.eval span (Pitfall #1, D-48)

  FastAPI->>Tracer: ctx_snapshot = capture_context()
  FastAPI->>Tracer: end_span("rag.request") -> root.end()
  FastAPI-->>Browser: 200 ChatResponse

  Note over FastAPI,BackgroundTasks: Phase 2 — async eval branch (fire-and-forget; never raises to user)

  FastAPI-)BackgroundTasks: add_task(run_eval, trace_id, answer, chunks, ctx_snapshot)

  Note over BackgroundTasks,Judge: Phase 3 — judge runs as child of rag.request via ctx_snapshot

  BackgroundTasks->>Tracer: attach_context(ctx_snapshot)
  BackgroundTasks->>Tracer: start_span("rag.eval", parent=root)
  BackgroundTasks->>Judge: score(answer, chunks)
  activate Judge
  Judge->>Anthropic: messages.create(model="claude-haiku-4-5-20251001", judge_prompt)
  Anthropic-->>Judge: faithfulness, relevance
  deactivate Judge
  Judge-->>BackgroundTasks: scores

  alt eval succeeds
    BackgroundTasks->>Postgres: write_span(rag.eval, scores, judge_payload)
    BackgroundTasks->>Tracer: end_span("rag.eval")
  else eval fails (timeout/exception)
    BackgroundTasks->>Tracer: log_error + end_span("rag.eval", status=error)
    Note over BackgroundTasks,Tracer: NEVER re-raise — Pitfall #3 (eval failures must not fail user requests)
  end
```

## Design Contracts Encoded

The Mermaid diagram above encodes four normative contracts that downstream phases (especially Phase 4 TRCR-04) **must** honor verbatim:

- **Context snapshot before root.end():** `ctx_snapshot = capture_context()` runs **BEFORE root.end()**. Capturing after `root.end()` yields a snapshot with no active span — `rag.eval` then orphans as a new trace root rather than attaching as a child of `rag.request`. This is **Pitfall #1** (D-48) and the most subtle of the four contracts. The `Note over FastAPI,Tracer` block in the diagram is the canonical statement of this rule.
- **Fire-and-forget eval branch:** `BackgroundTasks.add_task(...)` dispatches the eval branch with no awaitable return; the eval coroutine wraps its body in a try/except that logs the failure to the tracer (with `status=error`) but **never re-raises**. This is **Pitfall #3** — eval failures must not turn a successful user request into a failed one. The `alt eval succeeds / else eval fails` Mermaid block is the canonical encoding.
- **Dated model snapshots, not aliases:** `rag.llm_call` pins `claude-sonnet-4-5-20250929` (bot); `rag.eval` pins `claude-haiku-4-5-20251001` (judge). Neither uses the floating alias (`claude-sonnet-4-5`, `claude-haiku`) because alias drift silently invalidates calibrated faithfulness/relevance thresholds. This is **Pitfall #4** (D-50). The dated snapshots are written into the diagram body so reviewers see them at-a-glance.
- **`rag.eval` is a child of `rag.request`, not a new root:** Achieved via `attach_context(ctx_snapshot)` immediately before `start_span("rag.eval", parent=root)` inside the BackgroundTasks coroutine. Without `attach_context`, the new asyncio task starts in a fresh context with no active span, and the `parent=root` argument is the only thing keeping the parentage — but `parent=root` alone does not propagate the trace_id correctly through the tracer's context-keyed storage. Both pieces (snapshot capture + attach in the worker) are required.

## Cross-References

- [Architecture](./architecture.md)
- [API Contract](./api.md)
- [Trace Schema](./trace-schema.md)
- [ADR 005 — Observability Strategy](./decisions/005-observability-strategy.md)
