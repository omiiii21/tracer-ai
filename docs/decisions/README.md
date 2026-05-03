# Architecture Decision Records (ADRs)

These ADRs codify decisions made during Phase 1 of tracer-ai. Each ADR is a one-page MADR-lite document with the sections `## Status`, `## Context`, `## Options Considered`, `## Decision`, `## Consequences`, and `## References`. ADRs **001–009** resolve the GSD-OPEN-N items from the foundation PRD §10. ADR **010** is the operational scope-trim playbook (DSGN-09).

## Index

| ADR                                         | Decision                                                                                  | Resolves    | Status   |
|---------------------------------------------|-------------------------------------------------------------------------------------------|-------------|----------|
| [001](./001-charting-library.md)            | Tremor v3 for dashboard charts; raw Recharts as the escape hatch                          | GSD-OPEN-1  | Accepted |
| [002](./002-vector-store.md)                | pgvector on the same Postgres 16 instance as the trace store                              | GSD-OPEN-2  | Accepted |
| [003](./003-embedding-provider.md)          | Voyage AI `voyage-code-3` primary; sentence-transformers `nomic-embed-text-v1.5` fallback | GSD-OPEN-3  | Accepted |
| [004](./004-trace-storage.md)               | Postgres 16 + JSONB; `spans` table partitioned by month; `span_payloads` side table       | GSD-OPEN-4  | Accepted |
| [005](./005-observability-strategy.md)      | Custom tracer with OTel GenAI attribute names as constants; no `opentelemetry-sdk` runtime dep | GSD-OPEN-5 | Accepted |
| [006](./006-chunking-strategy.md)           | Markdown-header-aware chunker; defaults `chunk_size=900` / `overlap=100`; admin-tunable   | GSD-OPEN-6  | Accepted |
| [007](./007-reranking.md)                   | No re-ranker in v1; `ENABLE_RERANKER` flag reserved for v2                                | GSD-OPEN-7  | Accepted |
| [008](./008-judge-prompts-thresholds.md)    | RAGAS-style judge prompts with XML-delimited untrusted content; Haiku pinned to dated snapshot | GSD-OPEN-8 | Accepted |
| [009](./009-auth-deployment-direction.md)   | ADR-only direction for v1.5 single-tenant API-key middleware; no v1 implementation        | GSD-OPEN-9  | Accepted |
| [010](./010-scope-trim.md)                  | Cut order on >25% budget slip: DEMO-02/03/04 → DASH-04 → FBCK-05 UI → CLI-04 → EVAL-06 30→15 | DSGN-09  | Accepted |

## Authoring Conventions

- **Format:** MADR-lite (one page; sections listed above).
- **Filename:** `NNN-<slug>.md` with three-digit zero-padded number; slug is hyphen-case noun phrase.
- **Cross-links:** Relative markdown paths (`./002-vector-store.md`); never absolute paths.
- **Inline rationale:** Every ADR Context section embeds enough rationale to be comprehensible *without* reading `.planning/research/` files. Research is cited as a deeper-dive pointer, not the load-bearing explanation.

ADRs are **immutable once Accepted**. Superseding decisions create a new ADR (e.g., `011-supersedes-007-add-reranker.md`) rather than editing in place — the immutability is what makes the ADR series a faithful history of why the system is shaped the way it is.
