# ADR 009: Auth and Deployment — Direction-Only (No v1 Implementation)

## Status

Accepted — 2026-05-04

## Context

The foundation PRD describes a **single-user, local Docker Compose deployment** as the v1 target — the operator runs the stack on their own laptop, exposes nothing to the internet, and is the sole consumer of the chat and dashboard surfaces. Authentication and multi-tenant isolation are explicitly out of scope per `PROJECT.md` "Out of Scope" and `REQUIREMENTS.md §V2-AUTH-*`. However, leaving the auth/deployment direction undocumented invites accidental design choices that would force a v2 redesign — for example, hard-coding global state where a tenant key would later be required, or building deployment scripts that assume single-host forever.

This ADR captures the v1.5/v2 *direction* so the v1 codebase's import graph and configuration model do not preclude future implementation. It deliberately produces **no code, no tests, and no environment variables** — direction only.

This decision resolves [GSD-OPEN-9](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **ADR-only direction; no v1 code (chosen):** Document the future shape (single-tenant API-key middleware in front of FastAPI; single-node cloud host using the same Compose file). Zero v1 surface area, zero v1 cost.
- **Implement minimal API-key middleware now (rejected):** Out of v1 scope. PROJECT.md explicitly excludes auth from v1; building it speculatively burns budget on a feature with no v1 user.
- **Don't write the ADR (rejected):** Leaves an undocumented gap. v2 designers would lack context for why v1 has no `tenant_id` plumbing — risking either premature speculative design or confused redesign.

## Decision

tracer-ai v1 ships with **no authentication and no multi-tenant isolation**. The future direction (v1.5+) is a single-tenant **API-key middleware in front of FastAPI** — a simple `Depends(...)` extractor that reads an `Authorization: Bearer <key>` header, compares it against a configured key, and 401s on mismatch. Future deployment is a single-node cloud host (e.g., Fly, Render, a personal VPS) using the **same `infra/docker-compose.yml`** that drives local dev — no separate Kubernetes manifests, no Terraform.

**This ADR is ADR-only. It adds no v1 code, no v1 tests, and no v1 environment variables.** v1 trace storage and pipeline code do not include `tenant_id` columns or `user_id` parameters; multi-tenant becomes a schema migration in v2 if needed.

## Consequences

**Positive:**
- Zero v1 surface area for auth — the v1 codebase stays small and focused on the observability thesis.
- Future direction is documented, so v2 designers inherit context rather than guessing.
- Deployment story remains simple — `docker compose up` works locally and on a single-node cloud host alike.

**Negative:**
- External access to the locally-running API is **unauthenticated**. The operator must firewall, VPN, or proxy the service if they expose it beyond `localhost`. This limitation is documented in the README (DEMO-01 follow-up).
- Multi-tenant is a v2 schema change, not a v1 schema-already-supports-it bonus. Acceptable given v1 has no multi-tenant user.

**Mandatory follow-ups:**
- [ ] README documents the "v1 is single-user / no auth — firewall before exposing" guidance (Phase 5 DEMO-01).
- [ ] No code, no tests, no env vars added by this ADR (intentional — re-stated for verification).

## References

- [.planning/PROJECT.md §"Out of Scope"](../../.planning/PROJECT.md)
- [.planning/REQUIREMENTS.md §"V2-AUTH-01" and "V2-AUTH-02"](../../.planning/REQUIREMENTS.md) — v2 deferral entries.
- [ADR 010: Scope-Trim Plan](./010-scope-trim.md) — sibling operational ADR.
