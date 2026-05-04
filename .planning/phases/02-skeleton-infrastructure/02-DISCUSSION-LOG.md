# Phase 2: Skeleton & Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `02-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-04
**Phase:** 2-skeleton-infrastructure
**Mode:** `--auto` (Claude auto-selected the recommended option for every gray area; no AskUserQuestion calls fired)
**Areas discussed:** Repo Layout, Python Dependency Manager, Postgres Image & Extension, Docker Image Strategy, Migration Tooling at Boot, Environment Variables & Secrets, Pre-commit & Tooling, Frontend Skeleton Scope, Health Check Contract, Initial Migration Content

---

## Repo Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Flat (`tracer_ai/`, `frontend/`, `infra/` at root) | Matches `docs/architecture.md` §"Recommended Project Structure" verbatim; one less directory between root and Python imports | ✓ |
| Nested (`backend/tracer_ai/`, `frontend/`, `infra/`) | Common in monorepos with multiple backends; cleaner separation when there will be more than one Python service | |

**Auto-selected option:** Flat layout.
**Rationale:** Architecture spec already reads as flat layout; nesting introduces drift between doc and reality.

---

## Python Dependency Manager

| Option | Description | Selected |
|--------|-------------|----------|
| `uv` | Astral's fast resolver/installer; single binary; native `pyproject.toml`; `uv.lock` | ✓ |
| Poetry | Mature; familiar; slower; adds Poetry-specific `tool.poetry` sections | |
| `pip-tools` + `pip` | Minimal; `requirements.in` → `requirements.txt`; lacks workspace ergonomics | |

**Auto-selected option:** `uv`.
**Rationale:** 10–100× faster cold installs (matters for Docker layer cache + CI); deterministic locks; the `uv 0.4+` API surface used here is stable.

---

## Postgres Image & Extension Activation

| Option | Description | Selected |
|--------|-------------|----------|
| `pgvector/pgvector:pg16` | Official pgvector image; extension prebuilt; dated tags available | ✓ |
| `ankane/pgvector` | Deprecated alias; redirects to `pgvector/pgvector` | |
| `postgres:16` + manual `CREATE EXTENSION` | More control; extra failure surface; requires either `init.sql` or runtime install | |

**Auto-selected option:** `pgvector/pgvector:pg16` (digest-pinned at execute time).
**Rationale:** Official image, pinned digest = reproducibility; extension owned by Postgres init = one less migration concern.

---

## Docker Image Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Single multi-stage `Dockerfile.backend` (dev + prod targets) | One Dockerfile; bind-mount source for dev hot-reload; `prod` target reserved for v1.5 | ✓ |
| Split `Dockerfile.dev` + `Dockerfile.prod` | Cleaner per-target read; duplicates `deps` stage; drift risk | |
| Bake source for dev (no bind mount) | Faster cold start; loses hot-reload | |

**Auto-selected option:** Single multi-stage with bind-mounted source for dev.
**Rationale:** Hot-reload is critical for the build-budget; single Dockerfile keeps prod path one `--target` away.

---

## Migration Tooling at Boot

| Option | Description | Selected |
|--------|-------------|----------|
| Separate one-shot `migrate` service (`depends_on: condition: service_completed_successfully`) | Explicit ordering in compose; api blocks until migration done | ✓ |
| Bake `alembic upgrade head` into api entrypoint | Simpler compose file; ordering is implicit; harder to log/restart cleanly | |
| Manual (`docker compose run migrate`) | Full operator control; breaks "one-command boot" success criterion | |

**Auto-selected option:** Separate `migrate` service.
**Rationale:** ROADMAP success criterion 1 ("`docker compose up` boots green, no manual steps") requires automated migration; explicit service makes ordering and failure modes legible.

---

## Environment Variables & Secrets

| Option | Description | Selected |
|--------|-------------|----------|
| Compose `env_file: .env` + `.env.example` (gitignored / committed) | Standard local-dev pattern; familiar; `.env.example` is the "what to set" contract | ✓ |
| Docker secrets (`secrets:` directive + secret files) | Production-grade; v1 deferred per ADR 009 | |
| Inline `environment:` only (no `.env`) | No file artifact; operator must remember every var | |

**Auto-selected option:** `env_file` + committed `.env.example`.
**Rationale:** ADR 009 explicitly defers production hardening; v1 target is single-user local Compose.

**Validation strategy:** monolithic `Settings(BaseSettings)` in `tracer_ai/config.py`, fail-fast at import. Nested namespaces via nested `BaseModel` fields keep the import surface flat.

---

## Pre-commit & Tooling

| Option | Description | Selected |
|--------|-------------|----------|
| All four hooks every commit (ruff + mypy + tsc + pytest changed-only) + import-cycle guard | Maximum safety; ~5–15s per commit | ✓ |
| Tiered (only ruff on commit, full check on CI) | Faster commits; weaker local feedback | |
| Minimal (ruff format only on commit) | Fastest commits; defers all real checks | |

**Auto-selected option:** All four hooks every commit + import-cycle guard.
**Rationale:** Module-deps DAG (D-45 from Phase 1) only earns its keep when Phase 2 enforces it at commit time; the cost (~5–15s) is acceptable for the build budget.

---

## Frontend Skeleton Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Vite + TS + Tailwind v3 + shadcn init + one `/` route with `Card` | Matches Phase 3 starting point exactly; no rework | ✓ |
| Vite hello-world only (no Tailwind/shadcn yet) | Minimal Phase 2 footprint; Phase 3 has to redo init | |
| Full route shell (chat + dashboard + admin stubs) | Over-investing in scaffolding before features exist | |

**Auto-selected option:** Vite + TS + Tailwind v3 + shadcn init + one `/` route.
**Rationale:** Tailwind v3 pin and `shadcn init` are infrastructure decisions, not feature decisions; doing them now stops Phase 3 from re-doing infra work.

---

## Health Check Contract

| Option | Description | Selected |
|--------|-------------|----------|
| `GET /healthz` returns `{"status":"ok","version":...,"db":"ok"\|"unreachable"}` with 200/503 | Standard idiom; informs container orchestration; minimal | ✓ |
| `GET /` returns hello-world only | Easier; loses the orchestration signal | |
| Multiple endpoints (`/healthz` + `/readyz` Kubernetes-style) | Overkill for single-host Compose | |

**Auto-selected option:** Single `/healthz`.
**Rationale:** Compose `healthcheck` directive needs exactly this; future v1.5 deploy can split into `/healthz` (liveness) + `/readyz` (readiness) without breaking the contract.

---

## Initial Alembic Migration Content

| Option | Description | Selected |
|--------|-------------|----------|
| Full DDL from `docs/data-model.md` (5 trace tables + chunks + 3 monthly partitions) | Phase 2 boot brings up the full schema; Phase 3 ingestion has tables ready | ✓ |
| Extension-only bootstrap (Phase 3 adds tables) | Smaller Phase 2 footprint; Phase 3 has to ship migrations + RAG together | |
| Per-table revisions (one revision per table) | Cleaner history; more authoring effort; harder to read in `alembic history` | |

**Auto-selected option:** Full DDL in single initial revision.
**Rationale:** `docs/data-model.md` IS the contract; translating it now means Phase 3 just inserts data. Per-table revisions are a future-rebase concern that does not exist yet.

---

## Claude's Discretion (decisions where the user retains override authority during plan-phase)

- **D-2.05** (`uv` vs Poetry vs pip-tools) — if the operator already has Poetry muscle memory, switching is a one-day cost
- **D-2.15** (separate `migrate` service vs entrypoint-baked migrations) — ergonomics tradeoff
- **D-2.29** (frontend skeleton scope) — could shrink to vite-hello-world only if Phase 3 budget is tighter than expected
- **D-2.41** (number and order of plans) — planner authority; the only hard dependency is `(a)→(b)→(c)→(d)` and `(a)→(e)`

## Deferred Ideas

- CI / GitHub Actions workflow (Phase 7 polish)
- Docker secrets / production env hardening (Phase 1.5+ per ADR 009)
- Multi-arch image builds (`linux/amd64` only in v1)
- Cron / scheduled task for monthly partition rotation (helper installed; not scheduled)
- `tracer/exporters/postgres.py` async-queue body (Phase 4 TRCR-06)
- Real `/healthz` DB probe via SQLAlchemy pool (Phase 3+; Phase 2 uses direct `asyncpg.connect()`)
- Frontend Tremor chart rendering (installed in package.json; first usage in Phase 5)
- Voyage AI pricing verification (Phase 2 INFRA-01 prereq checkbox; the plan that creates `pyproject.toml` exercises it)
