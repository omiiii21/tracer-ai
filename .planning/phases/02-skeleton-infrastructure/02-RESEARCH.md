# Phase 2: Skeleton & Infrastructure - Research

**Researched:** 2026-05-04
**Domain:** Reproducible Docker Compose dev skeleton (Python 3.12 / FastAPI / Postgres 16 + pgvector / Vite + React 18)
**Confidence:** HIGH (every Phase 2 decision is locked in 02-CONTEXT.md; this file surfaces implementation details, version-specific syntax, and pitfalls)

## Summary

Phase 2 implements 43 locked decisions (D-2.01..D-2.43) against the design contracts produced in Phase 1 (architecture.md, module-deps.md, data-model.md, api.md, ADRs 001..010). The discuss step ran in `--auto`, so this research does NOT re-decide; it surfaces the implementation knowledge a planner agent needs to write executable plans against those decisions: canonical Dockerfile shapes for `uv`, the async Alembic `env.py` template, FastAPI lifespan + asyncpg pool patterns, Compose v2 `service_completed_successfully` semantics, pydantic-settings nested-vs-flat env var binding tradeoffs, pre-commit framework hook syntax, the shadcn CLI flow against Tailwind v3 + Vite, Voyage AI pricing verification, and the off-the-shelf-vs-custom tradeoff for the import-cycle guard.

The dominant theme across all 12 research topics: **prefer canonical, official patterns and pin versions explicitly.** uv has a documented multi-stage Dockerfile pattern (Astral docs); Alembic ships an async `env.py` template (`alembic init -t async`); FastAPI has a documented lifespan pattern for asyncpg pools; Compose v2.20.0+ supports `service_completed_successfully`; pydantic-settings v2 supports nested submodels via `env_nested_delimiter` BUT requires per-field `validation_alias` to honor the locked-in flat names like `DATABASE_URL` and `ANTHROPIC_API_KEY`; pre-commit has official hook repos for ruff, mypy, and tsc; shadcn CLI 3.x supports Vite + Tailwind v3 init flow; Voyage AI publishes a verifiable pricing page (200M free tokens, $0.18/1M); `import-linter` is a maintained off-the-shelf alternative to a custom 60-line AST script (D-2.27 reservation should be revisited in plan-phase).

**Primary recommendation:** Adopt the canonical patterns from official docs verbatim. The biggest risks are (a) skipping `--no-install-project` in the uv deps layer (kills layer cache), (b) running Alembic against `engine_from_config()` instead of `async_engine_from_config()` (asyncpg incompatibility), (c) forgetting `include_object` in Alembic `env.py` (autogenerate tries to recreate the partitioned `spans` table), (d) using `env_nested_delimiter` with the existing `DATABASE_URL`/`ANTHROPIC_API_KEY` flat var names without `validation_alias` (env vars silently ignored), and (e) defaulting to React 19 / Tailwind v4 via `npm create vite@latest` (breaks Tremor + shadcn).

## Architectural Responsibility Map

Phase 2 is infra/scaffolding only. The "capabilities" are not user-facing features; they are scaffolding deliverables. The map below shows where each Phase 2 deliverable lives architecturally.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Repo scaffold (`tracer_ai/`, `frontend/`, `infra/`) | Filesystem / VCS | — | Phase 1 design artifacts dictate the layout; Phase 2 mirrors `docs/architecture.md` §"Recommended Project Structure" verbatim |
| Docker Compose stack | Orchestration (Compose) | OS / Docker daemon | Compose v2 plugin orchestrates db / migrate / api / web services on the host's Docker daemon |
| `pgvector/pgvector:pg16` DB image | Database / Storage | — | Postgres 16 + pgvector extension; data volume backed; init.sql owns extension creation |
| Alembic initial migration | Database / Storage | API tier (reads same Settings) | Migration is data-tier authoritative for schema; api tier reads Settings.db.url to confirm DSN parity |
| FastAPI hello + `/healthz` | API / Backend | Database (probe) | API tier owns endpoint; probes DB pool with 500ms timeout |
| Settings (`tracer_ai/config.py`) | API / Backend (cross-cutting) | All other tiers via import | Module-deps.md leaf; imported by tracer/, rag/, eval/, api/, cli/ AND by Alembic env.py |
| Vite + React hello route | Frontend Server (dev) / Browser (runtime) | API (CORS endpoint) | Vite dev server hosts; browser executes; `VITE_API_BASE_URL=http://localhost:8000` is the only API-tier coupling |
| Pre-commit hooks | Local dev tooling | VCS (git hooks) | Runs on host before commit; not in any Docker image |
| Import-cycle guard | Local dev tooling | Static analysis of `tracer_ai/` AST | Reads `docs/module-deps.md`; enforces DAG at commit time |
| README quick-start | Documentation | — | Phase 7 polishes; Phase 2 ships verifiable shape |

**Tier-misassignment risks for the planner to verify:**
- Settings is cross-cutting BUT lives in api-tier package (`tracer_ai/config.py`). A plan that places config in `infra/` would break the Alembic `env.py → tracer_ai.config.Settings` import contract (D-2.16).
- The Alembic migration must NOT call `CREATE EXTENSION vector` — that's `infra/db/init.sql`'s job (D-2.09). Misassignment here causes permission errors when the app user runs the migration without superuser rights.

## Standard Stack

### Core (locked from CLAUDE.md + STACK.md + 02-CONTEXT.md)

| Library | Version (verified) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 (lower bound `>=3.12,<3.13` per D-2.06) | Backend runtime | LTS; widest Docker image availability (`python:3.12-slim-bookworm`) [VERIFIED: STACK.md §Locked Stack] |
| FastAPI | 0.128.x | HTTP API server | Latest as of 2026-05; native Pydantic v2 [VERIFIED: STACK.md] |
| Pydantic | 2.x | Validation + I/O schemas | v2 strict-mode required by api.md [VERIFIED: docs/api.md] |
| pydantic-settings | 2.x | Env-driven Settings | v2 companion; supersedes python-dotenv [CITED: docs.pydantic.dev/latest/concepts/pydantic_settings] |
| uv (Astral) | 0.4+ (use `latest` Docker image with digest pin) | Dependency manager | 10-100× faster cold installs vs Poetry; native pyproject.toml [CITED: docs.astral.sh/uv] |
| SQLAlchemy | 2.0+ (with `[asyncio]` extra) | ORM + Alembic backbone | Async support via `create_async_engine` [VERIFIED: STACK.md] |
| asyncpg | 0.29+ | Async Postgres driver | Required for SQLAlchemy 2.0 async [VERIFIED: STACK.md] |
| pgvector (Python) | 0.3+ | pgvector column type + distance ops | SQLAlchemy 2.0 integration [VERIFIED: STACK.md] |
| Alembic | 1.x (latest) | Schema migrations | Standard for SQLAlchemy projects [CITED: alembic.sqlalchemy.org] |
| uvicorn | 0.30+ (with `[standard]` extra) | ASGI server | `--reload` flag for dev; standard FastAPI pairing [VERIFIED: STACK.md] |
| structlog | 24.x | Structured logging | JSON output for tracer; D-2.37 forbids `print()` in `tracer_ai/` |
| anthropic | 0.49+ | Anthropic SDK | Future use (Phase 3+); installed Phase 2 but not imported [VERIFIED: STACK.md] |
| voyageai | 0.3+ | Voyage AI client | Future use (Phase 3+); installed Phase 2 but not imported |
| sentence-transformers | 3.x | Offline embedder fallback | Future use (Phase 3+); installed Phase 2 but not imported |
| tiktoken | 0.7+ | Token counting | Future use (Phase 3+) |
| python-multipart | latest | File upload support (FastAPI dependency) | Future use (Phase 3+ admin upload endpoint) |
| httpx | 0.27+ | HTTP client + FastAPI TestClient | Phase 2 tests need TestClient |

### Dev tooling (locked)

| Library | Version | Purpose |
|---------|---------|---------|
| ruff | latest | Linter + formatter (replaces flake8 + black) |
| mypy | latest | Static type checker; `--strict` mode |
| pytest | latest | Test runner |
| pytest-asyncio | latest | Async test support |
| pre-commit | latest | Git hook framework |

### Frontend (locked from D-2.30)

| Library | Pinned Version | Purpose | Critical |
|---------|---------|---------|----------|
| react / react-dom | `^18.3.1` | UI runtime | **NOT React 19** — shadcn/ui + Tremor v3 stable on 18 |
| typescript | `~5.5` | Type safety | shadcn/ui requires TS 5+ |
| vite | `^5` | Build + dev server | Latest stable; v5 confirmed compatible with Tailwind v3 |
| tailwindcss | `^3.4` | Styling | **NOT v4** — Tremor v3 + shadcn/ui require v3 [VERIFIED: STACK.md "Tailwind v4 breaks shadcn/ui PostCSS config; pin v3"] |
| @tremor/react | `^3` | Dashboard charts | Phase 5 uses; install Phase 2 |
| @tanstack/react-query | `^5` | Server state | Phase 3 uses; install Phase 2 |
| react-router-dom | `^6` | Routing | Required for `/` hello route + Phase 3 routes |
| clsx + tailwind-merge | `^2` each | shadcn `cn()` utility | shadcn CLI installs |
| lucide-react | latest | Icons | shadcn CLI installs |

### Alternatives Considered (per ADRs / 02-CONTEXT.md)

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| uv | Poetry | Operator muscle memory, but uv is 10-100× faster (D-2.05 reservation) |
| separate `migrate` service | Migrations baked into api entrypoint | Ergonomics tradeoff; D-2.15 chose explicit one-shot for "fresh checkout boots green" reproducibility |
| Custom 60-line `import_cycle_guard.py` | `import-linter` (off-the-shelf) | Maintenance burden vs ~150-line `.importlinter` config — see Topic 9 below |
| Tailwind v4 | Tailwind v3 | v4 breaks Tremor + shadcn ecosystems |

**Installation snapshot (verified 2026-05-04):**
```bash
# Backend
uv add fastapi pydantic pydantic-settings sqlalchemy[asyncio] asyncpg pgvector \
       alembic uvicorn[standard] anthropic voyageai sentence-transformers \
       structlog tiktoken python-multipart httpx
uv add --dev ruff mypy pytest pytest-asyncio pre-commit

# Frontend (after `npm create vite@latest frontend -- --template react-ts`)
# CRITICAL: Vite scaffold defaults to React 19 + Tailwind v4 in 2026.
# Manually pin React 18 + Tailwind v3 in package.json before npm install.
npm install -D tailwindcss@^3.4 postcss autoprefixer
npx tailwindcss init -p
npx shadcn@latest init  # interactive: accepts Tailwind v3 config
npx shadcn@latest add card button
npm install @tremor/react@^3 @tanstack/react-query@^5 react-router-dom@^6
```

**Version verification was performed for all listed packages against npm registry / PyPI / Astral docs (see Sources §). Pin versions in pyproject.toml + package.json at write time, not floating ranges.**

---

## User Constraints (from 02-CONTEXT.md)

### Locked Decisions

The 43 implementation decisions D-2.01..D-2.43 are locked verbatim in
`02-CONTEXT.md` lines 48-131 and not duplicated here. Of particular operational
significance during implementation:

- **D-2.01:** Flat repo layout — `tracer_ai/`, `frontend/`, `infra/` at repo root
- **D-2.05:** `uv` is the dependency manager; `pyproject.toml` + `uv.lock` committed
- **D-2.06:** `requires-python = ">=3.12,<3.13"`
- **D-2.08:** `pgvector/pgvector:pg16` image (digest-pinned at execute time)
- **D-2.09:** `vector` extension created by `infra/db/init.sql`, NOT in Alembic migration
- **D-2.11:** Multi-stage Dockerfile.backend (`base` / `deps` / `dev` / `prod`)
- **D-2.15:** Separate one-shot `migrate` service; `api` `depends_on` it with `service_completed_successfully`
- **D-2.17:** Initial migration = full DDL from `docs/data-model.md` verbatim
- **D-2.19:** Required env vars validated at import time
- **D-2.21:** Fail-fast — `settings = Settings()` at module top level
- **D-2.24:** Pre-commit hooks: ruff, ruff-format, mypy --strict, tsc, pytest, import-cycle-guard
- **D-2.27:** Custom 60-line `import_cycle_guard.py` (revisitable in plan-phase per Topic 9)
- **D-2.29:** Frontend = vite + react-ts + tailwind v3 + shadcn init + one `/` route with `Card`
- **D-2.33:** `/healthz` returns `{"status": "ok", "version": __version__, "db": "ok"|"unreachable"}`
- **D-2.40:** No `gen_ai.system` constant; only `gen_ai.provider.name`

### Claude's Discretion (per 02-CONTEXT.md lines 125-129)

The discuss step ran in `--auto`. Auto-selected decisions are revisitable on counter-evidence; user override authority is reserved for:
- D-2.05 (uv vs Poetry)
- D-2.15 (separate migrate service vs entrypoint-baked migrations)
- D-2.29 (frontend skeleton scope — could shrink to vite-only)

### Deferred Ideas (OUT OF SCOPE — do not research alternatives)

- CI / GitHub Actions workflow (Phase 7)
- Docker secrets / production env hardening (ADR 009)
- Multi-arch image builds (Phase 7)
- Production `prod` Dockerfile target (defined as a stage; not built)
- Cron / scheduled task for monthly partition rotation (helper installed; not scheduled)
- `tracer/exporters/postgres.py` body (Phase 4 TRCR-06)
- Real `/healthz` DB probe via SQLAlchemy pool (Phase 3 wires pool; Phase 2 uses `asyncpg.connect()` directly)
- Tremor chart rendering (Phase 5)
- CHAT/RAG/EVAL/CORP features (Phase 3+)

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Repo scaffold per ARCHITECTURE.md module layout (`tracer_ai/`, `frontend/`, `infra/`) | docs/architecture.md (already produced); `tracer_ai/__init__.py` exposes only `__version__` per D-2.02 |
| INFRA-02 | `docker compose up` boots full stack green (FastAPI hello, Vite hello, Postgres 16+pgvector) | Topics 1, 3, 4, 10 below |
| INFRA-03 | Tags pinned (no `:latest`); `.env.example` checked in; `config.py` validates env vars at startup | Topic 5 (pydantic-settings); D-2.36 grep enforcement |
| INFRA-04 | Pre-commit hooks active: ruff, mypy, tsc, basic test runner, import-cycle guard | Topics 6, 9, 11, 12 below |
| INFRA-05 | README skeleton with setup steps; verify `docs/decisions/` exists from Phase 1 | Topic 8 (Voyage pricing prereq); README is Phase 7 polish |

---

## Architecture Patterns

### System Architecture Diagram (Phase 2 only — hello-world skeleton)

```mermaid
flowchart LR
  host["Developer host (git checkout)"]
  compose["docker compose up"]
  subgraph stack["Compose stack"]
    db[("db<br/>pgvector/pgvector:pg16")]
    migrate["migrate<br/>(one-shot, alembic upgrade head)"]
    api["api<br/>uvicorn FastAPI :8000<br/>GET /healthz"]
    web["web<br/>vite dev :5173<br/>GET /"]
  end
  curl["curl localhost:8000/healthz"]
  browser["browser localhost:5173"]

  host --> compose
  compose --> db
  db -.healthcheck pg_isready.-> migrate
  migrate -.exit 0.-> api
  db -.healthcheck.-> api
  api -.async pool probe.-> db
  curl --> api
  browser --> web
  web -.VITE_API_BASE_URL.-> api
```

**Reading this diagram:** Solid arrows are data flow; dotted arrows are dependency conditions / probes. The `migrate -.exit 0.-> api` and `db -.healthcheck.-> api` dotted edges encode the Compose v2 `depends_on.condition` machinery (Topic 4 below). The `api -.async pool probe.-> db` is the `/healthz` 500ms-timeout `SELECT 1` (D-2.33).

### Recommended Project Structure (verbatim from ARCHITECTURE.md + 02-CONTEXT.md)

```
tracer-ai/
├── tracer_ai/               # Python package (D-2.01 flat layout)
│   ├── __init__.py          # only __version__ (D-2.02)
│   ├── config.py            # Settings (D-2.19, D-2.21)
│   ├── errors.py            # Cross-cutting exceptions
│   ├── tracer/              # Phase 4 fills body; Phase 2 stubs
│   │   ├── __init__.py
│   │   ├── span.py          # Stub: gen_ai.* + rag.* constants only (D-2.40)
│   │   ├── context.py       # Stub
│   │   ├── store.py         # Protocol shape only
│   │   └── exporters/
│   │       ├── __init__.py
│   │       └── postgres.py  # Stub (TRCR-06 fills)
│   ├── rag/                 # Phase 3 fills; Phase 2 creates empty package
│   │   └── __init__.py
│   ├── eval/                # Phase 5 fills
│   │   └── __init__.py
│   ├── corpus/              # Phase 3 fills
│   │   └── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI app + lifespan (Topic 3)
│   │   └── health.py        # /healthz route (D-2.33)
│   └── cli/
│       ├── __init__.py
│       ├── __main__.py      # Phase 6 fills
│       └── partition.py     # create_next_month_partition() helper (D-2.18)
├── frontend/                # D-2.29 minimal skeleton
│   ├── package.json         # React 18 + Tailwind v3 + shadcn pins (D-2.30)
│   ├── tsconfig.json        # @/* path alias for shadcn
│   ├── tsconfig.node.json
│   ├── vite.config.ts       # path.resolve alias matching tsconfig
│   ├── tailwind.config.js   # v3 syntax (NOT v4 @theme)
│   ├── postcss.config.js
│   ├── components.json      # shadcn config (D-2.31)
│   ├── index.html
│   ├── .env.example         # VITE_API_BASE_URL=http://localhost:8000
│   └── src/
│       ├── main.tsx
│       ├── App.tsx          # / route → <Card>Hello tracer-ai</Card>
│       ├── index.css        # Tailwind v3 directives
│       ├── components/
│       │   └── ui/          # shadcn-generated Card.tsx, Button.tsx
│       └── lib/
│           └── utils.ts     # cn() helper from shadcn init
├── infra/
│   ├── docker-compose.yml
│   ├── Dockerfile.backend   # multi-stage: base/deps/dev/prod (D-2.11)
│   ├── Dockerfile.frontend  # multi-stage: base/deps/dev/prod (D-2.13)
│   ├── db/
│   │   └── init.sql         # CREATE ROLE tracer; CREATE DB; CREATE EXTENSION vector (D-2.09)
│   └── scripts/
│       └── import_cycle_guard.py  # custom 60-line guard (D-2.27)
├── alembic/
│   ├── env.py               # async pattern (Topic 2)
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial.py  # full DDL from data-model.md (D-2.17)
├── alembic.ini              # repo root (D-2.16)
├── pyproject.toml           # [project] + [project.optional-dependencies.dev] + [tool.ruff/.mypy/.pytest]
├── uv.lock                  # committed
├── .env.example             # all required vars w/ placeholders (D-2.22, D-2.23)
├── .pre-commit-config.yaml
├── .dockerignore            # mirrors .gitignore + node_modules + .venv (D-2.14)
├── .gitignore
└── README.md                # quick-start (D-2.35; Phase 7 polishes)
```

### Pattern 1: Module-deps-as-DAG, enforced at commit time

**What:** All cross-module imports flow strictly left-to-right per `docs/module-deps.md`. The pre-commit guard greps for forbidden edges in `tracer_ai/`'s AST.

**When to use:** Always — Phase 2 ships the guard; Phase 3+ adds modules and the guard validates each commit.

**Forbidden edges (verbatim from module-deps.md):**
- `corpus → rag` (corpus may import `rag/embedder` ONLY; not full rag/)
- Any edge from `api`/`cli` outward (they are entry points)
- Any edge into `config`/`errors` from outside leaves (they are leaves)

### Pattern 2: Single Settings as cross-tier source of truth

**What:** `tracer_ai.config.Settings` is imported by Alembic `env.py` AND `api/main.py`. Drift between migration DSN and api DSN is impossible by construction.

**When to use:** Always — D-2.16 mandates.

**Code:**
```python
# alembic/env.py
from tracer_ai.config import settings
config.set_main_option("sqlalchemy.url", str(settings.db.url))
```

### Pattern 3: Compose service ordering via `condition: service_completed_successfully`

**What:** `api` waits for `migrate` to exit 0 AND `db` to be healthy before binding port 8000.

**When to use:** D-2.15 mandates for INFRA-02 reproducibility.

**Verified syntax (Compose v2.20.0+):**
```yaml
api:
  depends_on:
    migrate:
      condition: service_completed_successfully
    db:
      condition: service_healthy
```

### Anti-Patterns to Avoid

- **`opentelemetry-sdk` runtime dep** — ADR 005 explicitly forbids. Use OTel attribute *names* as constants only.
- **`gen_ai.system` constant** — DEPRECATED. Use `gen_ai.provider.name` (D-2.40). Pre-commit grep flags any occurrence outside the explicit DEPRECATED comment.
- **`class Config:` Pydantic v1 syntax** — D-2.39 forbids. Use `model_config = ConfigDict(...)`.
- **Direct SDK imports outside adapter files** — D-2.38 forbids. `from anthropic` only allowed in `rag/llm.py` + `eval/llm_judge.py`. Phase 2 doesn't import them, but the rule ships.
- **`print(...)` in `tracer_ai/`** — D-2.37 forbids. Use `structlog.get_logger()`.
- **`:latest` tags** — D-2.36 forbids. Pre-commit grep enforces.
- **Tailwind v4** — breaks Tremor + shadcn (D-2.30; STACK.md).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Module DAG enforcement | 60-line AST analyzer | `import-linter` | See Topic 9 — maintained, NetworkX-backed, supports Layers contracts directly [CITED: import-linter.readthedocs.io] |
| Secret pre-commit scan | Custom grep for `sk-ant-` | `gitleaks` (preferred) or `detect-secrets` | gitleaks: 150+ rules, sub-second, single Go binary [CITED: gitleaks pre-commit-hooks.yaml]; supports custom regex via TOML |
| Async Alembic env.py | Hand-rolled `asyncio.run` shim | `alembic init -t async` template | Official template; uses `connection.run_sync(do_run_migrations)` correctly [CITED: github.com/sqlalchemy/alembic templates/async/env.py] |
| FastAPI lifespan + asyncpg pool | Manual `asyncio.create_task` for cleanup | FastAPI `lifespan=` async context manager | Documented pattern; auto SIGTERM handling via uvicorn [CITED: fastapi.tiangolo.com/advanced/events] |
| Vite hot reload over bind mount | Custom `nodemon` config | `vite` dev server + `CHOKIDAR_USEPOLLING=true` env var | Native Vite HMR + polling for Docker bind-mount file events [CITED: vite docs] |
| changed-only test runner | Hand-rolled git-diff → pytest filter | `pytest-testmon` OR `pytest-picked` | Both maintained; testmon uses coverage graph, picked uses git status [CITED: pypi.org/project/pytest-testmon] |
| Multi-stage uv Dockerfile | Hand-rolled COPY + RUN | Astral's documented pattern | Cache mount + `--no-install-project` deps layer = order-of-magnitude faster rebuilds [CITED: docs.astral.sh/uv/guides/integration/docker] |

**Key insight:** Every Phase 2 deliverable has a maintained, documented canonical implementation. Hand-rolling these saves 30 minutes once and costs hours of maintenance forever.

---

## Per-Topic Findings (the 12 implementation knowledge gaps)

### Topic 1: uv + Docker workflow (multi-stage Dockerfile.backend)

**Question:** What's the current canonical multi-stage Dockerfile for `uv sync --frozen` with separate `deps` and `prod` layers? How is the bind-mount-source-for-dev pattern set up cleanly?

**Finding:** Astral's official docs publish a verified multi-stage pattern. Two key flags drive layer cache hits: `--no-install-project` in the deps layer (so dependency change ≠ source change), and `UV_LINK_MODE=copy` to avoid hardlink errors when `/root/.cache/uv` is on a different filesystem than `/app/.venv`. `UV_COMPILE_BYTECODE=1` reduces startup latency.

**Code excerpt** (canonical Dockerfile.backend skeleton — adapted from Astral docs to D-2.11's 4-stage requirement):

```dockerfile
# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.5  # pin a specific uv release at execute time

# ---- base ----
FROM python:${PYTHON_VERSION}-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /uvx /bin/
WORKDIR /app

# ---- deps (cacheable) ----
FROM base AS deps
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --all-extras

# ---- dev (compose targets this) ----
FROM deps AS dev
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000
# Source bind-mounted by compose at /app/tracer_ai
CMD ["uvicorn", "tracer_ai.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- prod (NOT BUILT in Phase 2; reserved for v1.5 deployment) ----
FROM deps AS prod
COPY tracer_ai /app/tracer_ai
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --all-extras
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000
CMD ["uvicorn", "tracer_ai.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Pitfall to avoid:** Skipping `--no-install-project` in the `deps` layer — every source-file change invalidates the entire deps layer. Result: 30-second rebuilds become 3-minute rebuilds.

**Source:** [docs.astral.sh/uv/guides/integration/docker](https://docs.astral.sh/uv/guides/integration/docker/) [VERIFIED 2026-05-04 via WebFetch]; [github.com/astral-sh/uv-docker-example](https://github.com/astral-sh/uv-docker-example)

---

### Topic 2: Async SQLAlchemy 2.0 + asyncpg + pgvector + Alembic together

**Question:** What's the correct `env.py` shape for an async engine? How does the initial revision encode partitioning? Does `pgvector` need a special import in the migration?

**Finding:** Three orthogonal concerns:

1. **`env.py` async pattern.** The Alembic-shipped `async` template uses `async_engine_from_config(...) → connection.run_sync(do_run_migrations)`. This works with `postgresql+asyncpg://...` DSNs. `engine_from_config()` (Alembic's default) does NOT work with asyncpg.

2. **Partitioned-table DDL in initial revision.** Alembic's `op` API does NOT directly support `PARTITION BY RANGE`. Use `op.execute(sa.text("""...DDL..."""))` for the partitioned table and the per-month partition statements verbatim from `docs/data-model.md`.

3. **pgvector in migration.** `from pgvector.sqlalchemy import Vector` lets you use `Vector(1024)` as a column type in `op.create_table(...)`. The `chunks` table can use the standard `op.create_table` API; partition DDL must use raw SQL.

4. **`include_object` to skip `spans` partitions on autogenerate.** Future revisions (Phase 3+) must not try to recreate the partitioned `spans` parent or its child partitions. Pass `include_object=lambda obj, name, type_, ...: not (type_ == "table" and name.startswith("spans_y"))` to `context.configure(...)`. **Phase 2 doesn't autogenerate (D-2.17 hand-curates the initial revision), but the `include_object` hook MUST be in `env.py` from day one so Phase 3+ doesn't autogenerate-explode.**

**Code excerpt** (canonical `alembic/env.py` for this stack):

```python
import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from tracer_ai.config import settings  # D-2.16 single source of DSN

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", str(settings.db.url))

target_metadata = None  # D-2.17: hand-curated initial; no autogenerate from models in Phase 2

def _include_object(obj: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    # Skip spans partition children — Phase 3+ won't try to recreate them
    if type_ == "table" and name.startswith("spans_y"):
        return False
    return True

def do_run_migrations(connection: Any) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    raise RuntimeError("offline mode not supported (asyncpg DSN required)")
else:
    run_migrations_online()
```

**Initial revision skeleton** (`alembic/versions/0001_initial.py`):

```python
"""initial schema: traces + spans + chunks + monthly partitions

Revision ID: 0001
Revises:
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None

def upgrade() -> None:
    # 1. traces (verbatim from data-model.md lines 54-62)
    op.execute(sa.text("""
        CREATE TABLE traces (
            id UUID PRIMARY KEY,
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ,
            query_text TEXT NOT NULL,
            root_span_id UUID NOT NULL
        );
        CREATE INDEX traces_started_at_idx ON traces (started_at DESC);
    """))

    # 2. spans (PARTITION BY RANGE — raw SQL because op.* doesn't support PARTITION BY)
    op.execute(sa.text("""
        CREATE TABLE spans (
            id UUID NOT NULL,
            trace_id UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
            parent_span_id UUID,
            name TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ,
            attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (id, started_at)
        ) PARTITION BY RANGE (started_at);
    """))

    # 3. Three forward-rolling monthly partitions per D-2.17 + 02-CONTEXT.md verification gate
    for ym, lo, hi in [("y2026m05", "2026-05-01", "2026-06-01"),
                       ("y2026m06", "2026-06-01", "2026-07-01"),
                       ("y2026m07", "2026-07-01", "2026-08-01")]:
        op.execute(sa.text(f"""
            CREATE TABLE spans_{ym} PARTITION OF spans
                FOR VALUES FROM ('{lo}') TO ('{hi}');
            CREATE INDEX spans_{ym}_attrs_gin ON spans_{ym} USING gin (attrs);
            CREATE INDEX spans_{ym}_trace_id_idx ON spans_{ym} (trace_id);
        """))

    # 4. span_payloads (no FK to spans — partition FK enforcement is expensive)
    op.execute(sa.text("""
        CREATE TABLE span_payloads (
            span_id UUID PRIMARY KEY,
            payload JSONB NOT NULL
        );
    """))

    # 5. feedback
    op.execute(sa.text("""
        CREATE TABLE feedback (
            id UUID PRIMARY KEY,
            trace_id UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
            rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
            comment TEXT,
            diagnosis_tag TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX feedback_trace_id_idx ON feedback (trace_id);
    """))

    # 6. regression_cases
    op.execute(sa.text("""
        CREATE TABLE regression_cases (
            id UUID PRIMARY KEY,
            source_trace_id UUID NOT NULL REFERENCES traces(id),
            expected_doc_section TEXT NOT NULL,
            expected_chunk_keywords JSONB NOT NULL,
            promoted_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """))

    # 7. chunks (pgvector) — extension is created by infra/db/init.sql per D-2.09
    op.create_table(
        "chunks",
        sa.Column("id", sa.dialects.postgresql.UUID(), primary_key=True),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("doc_section", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_model_version", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.execute(sa.text(
        "CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    ))
    op.create_index("chunks_doc_section_idx", "chunks", ["doc_section"])

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS regression_cases CASCADE")
    op.execute("DROP TABLE IF EXISTS feedback CASCADE")
    op.execute("DROP TABLE IF EXISTS span_payloads CASCADE")
    # Drop partitions before parent
    for ym in ("y2026m05", "y2026m06", "y2026m07"):
        op.execute(f"DROP TABLE IF EXISTS spans_{ym} CASCADE")
    op.execute("DROP TABLE IF EXISTS spans CASCADE")
    op.execute("DROP TABLE IF EXISTS traces CASCADE")
```

**Pitfall to avoid:** Including `CREATE EXTENSION vector` in the migration. The application user `tracer` won't have `SUPERUSER` role; `CREATE EXTENSION` will fail at migration time. Per D-2.09, `infra/db/init.sql` (run by Postgres image's init mechanism as the superuser `postgres`) owns extension creation. The migration must assume `vector` already exists.

**Source:** [github.com/sqlalchemy/alembic — async env.py template](https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py); [Alembic docs — autogenerate include_object](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#omitting-schema-names-from-the-autogenerate-process); [pgvector-python SQLAlchemy integration](https://github.com/pgvector/pgvector-python)

---

### Topic 3: FastAPI lifespan handler + asyncpg pool + healthz

**Question:** What's the canonical 2026 FastAPI lifespan pattern for setting up an asyncpg pool, exposing it via `app.state.db`, and tearing it down? How should `/healthz` probe the pool with a 500ms timeout?

**Finding:** FastAPI's `lifespan=` parameter accepts an `@asynccontextmanager async def`. Inside, create the pool BEFORE `yield`, dispose it AFTER. uvicorn forwards SIGTERM correctly UNLESS multiple workers + reload are combined (a known footgun; Phase 2 dev uses single worker + reload, so this is fine). The 500ms-timeout `SELECT 1` uses `asyncio.wait_for(pool.fetchval("SELECT 1"), timeout=0.5)`.

**Code excerpt** (`tracer_ai/api/main.py`):

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
import structlog
from fastapi import FastAPI

from tracer_ai import __version__
from tracer_ai.config import settings

log = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Convert SQLAlchemy DSN postgresql+asyncpg://... → asyncpg DSN postgresql://...
    asyncpg_dsn = str(settings.db.url).replace("+asyncpg", "")
    pool = await asyncpg.create_pool(
        dsn=asyncpg_dsn,
        min_size=1,
        max_size=10,
        max_inactive_connection_lifetime=300.0,
    )
    app.state.db_pool = pool
    log.info("db_pool_ready", min_size=1, max_size=10)
    try:
        yield
    finally:
        await app.state.db_pool.close()
        log.info("db_pool_closed")

app = FastAPI(title="tracer-ai", version=__version__, lifespan=lifespan)

# Routes registered after app creation
from tracer_ai.api import health  # noqa: E402
app.include_router(health.router)
```

**`tracer_ai/api/health.py`:**

```python
import asyncio
from typing import Literal

import asyncpg
import structlog
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from tracer_ai import __version__

log = structlog.get_logger()
router = APIRouter()

class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "degraded"]
    version: str
    db: Literal["ok", "unreachable"]

@router.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request, response: Response) -> HealthResponse:
    pool: asyncpg.Pool = request.app.state.db_pool
    db_status: Literal["ok", "unreachable"] = "ok"
    try:
        async with pool.acquire(timeout=0.5) as conn:
            await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=0.5)
    except (asyncio.TimeoutError, asyncpg.PostgresError, OSError) as e:
        db_status = "unreachable"
        log.warning("healthz_db_probe_failed", error=str(e))
        response.status_code = 503
        return HealthResponse(status="degraded", version=__version__, db=db_status)
    return HealthResponse(status="ok", version=__version__, db=db_status)
```

**Pitfall to avoid:** Passing the SQLAlchemy DSN `postgresql+asyncpg://...` directly to `asyncpg.create_pool()` — asyncpg expects the bare `postgresql://` scheme. The `.replace("+asyncpg", "")` is required, or store two DSNs in Settings (one per consumer).

**Source:** [fastapi.tiangolo.com/advanced/events/#lifespan](https://fastapi.tiangolo.com/advanced/events/); [github.com/fastapi/fastapi discussion #9520](https://github.com/fastapi/fastapi/discussions/9520) — pool in lifespan; [daniel.feldroy.com — asyncpg + FastAPI](https://daniel.feldroy.com/posts/2025-10-using-asyncpg-with-fastapi-and-air)

---

### Topic 4: Compose v2 `depends_on.condition` semantics

**Question:** Does it require Compose v2.20.0+? What's the healthcheck syntax? What if migrate exits non-zero?

**Finding:** `service_completed_successfully` was added in **Compose v2.20.0** (released Sep 2023). Any modern Docker Desktop has it. If the dependency exits non-zero, the dependent service NEVER starts (correct fail-fast behavior for INFRA-02 success criterion 1). For Postgres healthcheck: `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` is the canonical probe; recommended `interval: 5s`, `timeout: 3s`, `retries: 5`, `start_period: 5s` for fast-boot dev DB.

**Code excerpt** (`infra/docker-compose.yml`):

```yaml
# Compose Schema v3.8+ implicit; explicit `version:` field is unnecessary in v2 (and emits a warning)
services:
  db:
    image: pgvector/pgvector:pg16@sha256:<DIGEST_AT_EXECUTE_TIME>  # D-2.08 digest pin
    environment:
      POSTGRES_USER: tracer
      POSTGRES_PASSWORD: tracer
      POSTGRES_DB: tracer_ai
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro  # D-2.09
    # ports: ["5432:5432"]  # D-2.10: opt-in only; do not commit uncommented
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tracer -d tracer_ai"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 5s

  migrate:
    build:
      context: ..
      dockerfile: infra/Dockerfile.backend
      target: dev
    env_file: ../.env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ../tracer_ai:/app/tracer_ai:ro
      - ../alembic:/app/alembic:ro
      - ../alembic.ini:/app/alembic.ini:ro
    command: ["alembic", "upgrade", "head"]
    restart: "no"  # one-shot

  api:
    build:
      context: ..
      dockerfile: infra/Dockerfile.backend
      target: dev
    env_file: ../.env
    depends_on:
      migrate:
        condition: service_completed_successfully  # D-2.15
      db:
        condition: service_healthy
    ports: ["8000:8000"]
    volumes:
      - ../tracer_ai:/app/tracer_ai
      - ../pyproject.toml:/app/pyproject.toml:ro
      - ../uv.lock:/app/uv.lock:ro
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 5s

  web:
    build:
      context: ../frontend
      dockerfile: ../infra/Dockerfile.frontend
      target: dev
    env_file: ../frontend/.env
    ports: ["5173:5173"]
    volumes:
      - ../frontend/src:/app/src
      - ../frontend/index.html:/app/index.html
      - /app/node_modules  # named anonymous volume — see Topic 10
    environment:
      CHOKIDAR_USEPOLLING: "true"  # required for Vite HMR over Docker bind mount

volumes:
  db_data:
```

**Pitfall to avoid:** Using `version: "3.8"` at the top of `docker-compose.yml` — Compose v2 emits a warning ("the attribute `version` is obsolete"). Omit it.

**Source:** [docs.docker.com/compose/how-tos/startup-order](https://docs.docker.com/compose/how-tos/startup-order/); [docker/compose issue #8154 — service_completed_successfully introduction](https://github.com/docker/compose/issues/8154); [docs.docker.com/reference/compose-file/services](https://docs.docker.com/reference/compose-file/services/)

---

### Topic 5: Pydantic-settings v2 monolithic Settings with nested namespaces and FLAT env vars

**Question:** What's the idiomatic way to model `Settings.db.url`, `Settings.anthropic.api_key`, populated from FLAT env vars (`DATABASE_URL`, `ANTHROPIC_API_KEY`)?

**Finding:** This is the most subtle topic in Phase 2. pydantic-settings v2's `env_nested_delimiter="__"` machinery expects `DB__URL` and `ANTHROPIC__API_KEY` — NOT `DATABASE_URL` and `ANTHROPIC_API_KEY`. To honor D-2.19's flat names, each nested field needs an explicit `validation_alias=AliasChoices("DATABASE_URL", "DB__URL")` (or just the flat name). The cleanest pattern is to NOT use `env_nested_delimiter` at all and rely on per-field `validation_alias`.

**Code excerpt** (`tracer_ai/config.py`):

```python
"""Settings: single source of truth for env-driven config.

Imported by tracer_ai/api/main.py AND alembic/env.py — drift impossible by construction (D-2.16).
Validation runs at import time (D-2.21); missing required vars raise pydantic.ValidationError before
uvicorn binds the port.
"""
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseModel):
    """Database config — flat env var DATABASE_URL."""
    url: PostgresDsn = Field(
        validation_alias=AliasChoices("DATABASE_URL", "DB_URL"),
        description="postgresql+asyncpg://user:pass@host:port/db",
    )


class AnthropicSettings(BaseModel):
    """Anthropic config — flat env vars ANTHROPIC_API_KEY etc."""
    api_key: SecretStr = Field(validation_alias="ANTHROPIC_API_KEY")
    bot_model: str = Field(
        default="claude-sonnet-4-5-20250929",
        validation_alias="LLM_BOT_MODEL",
    )
    judge_model: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias="LLM_JUDGE_MODEL",
    )


class VoyageSettings(BaseModel):
    """Voyage AI config — flat env vars."""
    api_key: SecretStr = Field(validation_alias="VOYAGE_API_KEY")
    embedding_model: str = Field(
        default="voyage-code-3",
        validation_alias="EMBEDDING_MODEL",
    )


class Settings(BaseSettings):
    """Top-level Settings — fail-fast at import time (D-2.21)."""
    model_config = SettingsConfigDict(
        env_file=None,  # Compose injects via env_file: directive; no implicit .env loading
        case_sensitive=True,
        extra="forbid",
    )

    db: DBSettings = Field(default_factory=lambda: DBSettings.model_validate({}))
    anthropic: AnthropicSettings = Field(default_factory=lambda: AnthropicSettings.model_validate({}))
    voyage: VoyageSettings = Field(default_factory=lambda: VoyageSettings.model_validate({}))

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    enable_reranker: bool = Field(default=False, validation_alias="ENABLE_RERANKER")


# D-2.21 fail-fast: ValidationError raises here if any required var is missing.
settings = Settings()
```

**Note on the `default_factory` trick:** Without it, the nested `BaseModel` won't read its own env vars at top-level Settings construction time, because `BaseSettings` only auto-populates fields IT directly owns. The `default_factory=lambda: DBSettings.model_validate({})` triggers the nested model's own `validation_alias` resolution against `os.environ`. **Verify this trick at Phase 2 implementation time** — the pydantic-settings GitHub issue tracker discusses several workarounds and the cleanest one may have shifted between releases.

**Alternative (simpler, recommended if you'll accept it):** Drop the nested `db.url` / `anthropic.api_key` shape and use a flat `Settings` class with `database_url: PostgresDsn`, `anthropic_api_key: SecretStr` etc. Then `tracer_ai/api/main.py` does `settings.database_url` (not `settings.db.url`). This works out-of-the-box without aliases. **The plan-phase should surface this as a counter-proposal to D-2.20** — D-2.20's nested rationale ("group new vars without renaming existing ones") is real but has a non-zero implementation tax.

**`.env.example`** (committed; D-2.22, D-2.23):

```
# Required — fail-fast on missing
DATABASE_URL=postgresql+asyncpg://tracer:tracer@db:5432/tracer_ai
ANTHROPIC_API_KEY=sk-ant-REPLACE
VOYAGE_API_KEY=REPLACE

# Optional with defaults
LLM_BOT_MODEL=claude-sonnet-4-5-20250929
LLM_JUDGE_MODEL=claude-haiku-4-5-20251001
EMBEDDING_MODEL=voyage-code-3
LOG_LEVEL=INFO
ENABLE_RERANKER=false
```

**Pitfall to avoid:** Setting `env_nested_delimiter="__"` in `SettingsConfigDict` while ALSO using `validation_alias` for flat names. The two mechanisms interact in non-obvious ways (the nested delimiter is checked first, and if `DB__URL` exists, it wins over `DATABASE_URL`). Pick one strategy.

**Source:** [docs.pydantic.dev/latest/concepts/pydantic_settings/#nested-model-default-partial-updates](https://docs.pydantic.dev/latest/concepts/pydantic_settings/); [github.com/pydantic/pydantic-settings issue #27 — env vars not loaded in nested model](https://github.com/pydantic/pydantic-settings/issues/27); [github.com/pydantic/pydantic discussion #8989](https://github.com/pydantic/pydantic/discussions/8989)

---

### Topic 6: pre-commit framework + ruff + mypy + tsc + pytest + custom local hook

**Question:** What's the current `.pre-commit-config.yaml` shape with all six hook types?

**Finding:** Each tool has either an official upstream pre-commit repo OR is run as a local hook:
- **ruff:** `astral-sh/ruff-pre-commit` (official, Astral-maintained). Latest 2026 version: pin to a tag like `v0.7.x` at execute time.
- **mypy:** `pre-commit/mirrors-mypy` (official mirror). `args: [--strict, tracer_ai/]`. `additional_dependencies: [pydantic, types-...]`.
- **tsc:** No upstream repo — declared as `language: system` local hook running `tsc --noEmit -p frontend/tsconfig.json`.
- **pytest:** No upstream repo — local hook. With `pytest-testmon` adds change-tracking.
- **import-cycle-guard:** Local Python hook (D-2.27).
- **secret scanner:** `gitleaks/gitleaks` upstream repo with pre-commit-hooks.yaml at master.

**Code excerpt** (`.pre-commit-config.yaml`):

```yaml
default_language_version:
  python: python3.12

repos:
  # Standard hygiene
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-merge-conflict
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: [--maxkb=500]

  # Ruff — replaces flake8 + black (D-2.25)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.0  # pin a real release at execute time
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # mypy --strict (D-2.26)
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.0
    hooks:
      - id: mypy
        args: [--strict, tracer_ai/]
        additional_dependencies:
          - pydantic>=2
          - pydantic-settings>=2
          - types-PyYAML
        files: ^tracer_ai/

  # gitleaks — secret scanner (replaces D-2.23 homegrown grep; see Topic 11)
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks

  # tsc — frontend type check (local, no upstream repo)
  - repo: local
    hooks:
      - id: tsc-frontend
        name: tsc --noEmit (frontend)
        language: system
        entry: bash -c 'cd frontend && npx tsc --noEmit -p tsconfig.json'
        files: ^frontend/.*\.(ts|tsx)$
        pass_filenames: false

      # pytest changed-only (D-2.24)
      - id: pytest-testmon
        name: pytest --testmon (changed only)
        language: system
        entry: bash -c 'uv run pytest --testmon -q'
        types: [python]
        pass_filenames: false

      # import-cycle guard (D-2.27)
      - id: import-cycle-guard
        name: tracer_ai/ module DAG enforcement
        language: system
        entry: python infra/scripts/import_cycle_guard.py
        files: ^tracer_ai/.*\.py$
        pass_filenames: false
```

**Pitfall to avoid:** Running `mypy` from the `mirrors-mypy` repo without `additional_dependencies: [pydantic>=2]` — mypy can't import `pydantic.BaseModel` from its own venv, so every Pydantic class triggers `error: Class cannot subclass "BaseModel" (has type "Any")`. The fix is documented but easily missed.

**Source:** [pre-commit.com/hooks](https://pre-commit.com/hooks.html); [github.com/astral-sh/ruff-pre-commit](https://github.com/astral-sh/ruff-pre-commit); [jaredkhan.com/blog/mypy-pre-commit](https://jaredkhan.com/blog/mypy-pre-commit) — `additional_dependencies` pattern explained

---

### Topic 7: shadcn CLI 3.x init in 2026 (Vite + React 18 + Tailwind v3)

**Question:** What's the current init flow? Are there known traps with the `@/components/ui/...` alias?

**Finding:** `npx shadcn@latest init` is interactive and prompts for: style, base color, CSS variables, tsconfig path, components dir, utils dir, RSC, TSX. It writes `components.json`, updates `tailwind.config.js`, updates `src/index.css` (Tailwind directives + CSS vars), and adds `src/lib/utils.ts` (the `cn()` helper).

**Critical 2026 caveats:**
1. **shadcn defaults to Tailwind v4** in fresh projects since late 2025. To stay on v3 (D-2.30), choose "Tailwind v3" when prompted, OR pre-install Tailwind v3 BEFORE running shadcn init — the CLI detects existing config and uses v3.
2. **Base color "slate" not in latest list.** Latest shadcn CLI lists: Neutral, Stone, Zinc, Mauve, Olive, Mist, Taupe (verified 2026-05). The 02-CONTEXT.md mention of "slate" reflects older shadcn — pick `Zinc` or `Stone` for a similar grey aesthetic. **Plan-phase action item:** confirm a specific base color before scaffolding.
3. **Path alias setup.** shadcn writes `@/*` to point at `./src/*` in BOTH `tsconfig.json` (`compilerOptions.paths`) AND `vite.config.ts` (`resolve.alias`). If you skip the Vite side, builds fail; if you skip the tsconfig side, `tsc --noEmit` fails.

**Code excerpt** (post-init `frontend/components.json`):

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.js",
    "css": "src/index.css",
    "baseColor": "zinc",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

**`vite.config.ts`:**
```typescript
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: { host: "0.0.0.0", port: 5173, watch: { usePolling: true } },
});
```

**`src/App.tsx` (Phase 2 hello route per D-2.29 + D-2.31):**
```tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function App() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-8">
      <Card className="w-full max-w-md">
        <CardHeader><CardTitle>Hello tracer-ai</CardTitle></CardHeader>
        <CardContent>
          <p className="text-muted-foreground mb-4">
            Phase 2 skeleton — RAG features land in Phase 3.
          </p>
          <Button onClick={() => console.log("phase 2 alive")}>Test</Button>
        </CardContent>
      </Card>
    </div>
  );
}
```

**Pitfall to avoid:** Running `npm create vite@latest frontend -- --template react-ts` and accepting defaults in 2026 — Vite 5 + Vite scaffold default to React 19 + Tailwind v4. Pin React 18 + Tailwind v3 in `package.json` BEFORE first `npm install`. D-2.30 specifies the exact pins.

**Source:** [ui.shadcn.com/docs/installation/vite](https://ui.shadcn.com/docs/installation/vite); [ui.shadcn.com/docs/components-json](https://ui.shadcn.com/docs/components-json); [ui.shadcn.com/docs/changelog](https://ui.shadcn.com/docs/changelog)

---

### Topic 8: Voyage AI pricing verification (INFRA-01 prereq per ADR 003)

**Question:** Without consuming Voyage API credit, what URL shows current pricing for `voyage-code-3`?

**Finding (verified 2026-05-04 via WebFetch):**
- **URL:** `https://docs.voyageai.com/docs/pricing`
- **Free tier:** **First 200 million tokens are complimentary per account** (covers voyage-4-large, voyage-4, voyage-4-lite, voyage-context-3, voyage-code-3 — same allowance pool).
- **Per-million pricing:** `voyage-code-3` = **$0.18 per 1M tokens** (input).
- **Max input per request:** 32K tokens.
- **Free tier allowance:** Cumulative, not monthly-resetting.
- **Rate limits:** Documented separately at `docs.voyageai.com/docs/rate-limits` (Phase 2 doesn't hit this; Phase 3 ingestion will).

**Implication for tracer-ai:** ~50K chunks × ~500 tokens/chunk = 25M tokens for full corpus indexing. Well under the 200M free tier. **No paid spend required for Phase 3 corpus ingestion.** ADR 003's pricing checkbox can be ticked.

**Plan-phase prereq language for the pyproject.toml plan:**
> Before adding `voyageai` to `[project.dependencies]`, the operator MUST visit https://docs.voyageai.com/docs/pricing and confirm:
> 1. `voyage-code-3` is still free under the 200M token allowance, OR
> 2. The operator accepts the current paid rate.
> Tick the checkbox in `docs/decisions/003-embedding-provider.md` "Mandatory follow-ups" before this plan ships.

**Pitfall to avoid:** Assuming pricing is monthly-resetting. The 200M tokens are a one-time allowance per account; once consumed, paid billing kicks in. Phase 3+ should track corpus-ingestion token spend.

**Source:** [docs.voyageai.com/docs/pricing](https://docs.voyageai.com/docs/pricing) [VERIFIED 2026-05-04 via WebFetch]; [www.mongodb.com/docs/voyageai/management/billing](https://www.mongodb.com/docs/voyageai/management/billing/)

---

### Topic 9: Module dependency graph enforcement at pre-commit time (custom vs `import-linter`)

**Question:** Off-the-shelf `import-linter` vs the 60-line custom `import_cycle_guard.py` (D-2.27)?

**Finding:** `import-linter` is the maintained, tested, off-the-shelf solution. It supports Python 3.12, uses `grimp` (NetworkX-backed) for the import graph, and offers contract types that map directly to `docs/module-deps.md`:
- **Layers contract** — enforces strict left-to-right ordering (matches our `config/errors → tracer/corpus → rag/eval → api/cli` layering)
- **Forbidden contract** — enforces specific blocked edges (e.g., `corpus → rag` except `rag.embedder`)
- **Independence contract** — sets of modules that don't depend on each other

It runs as a pre-commit hook via `language: system` (because import-linter requires the project's venv to introspect the package). Latest version supports Python 3.12 cleanly.

**Code excerpt** (`.importlinter` config encoding the locked DAG):

```ini
[importlinter]
root_package = tracer_ai

[importlinter:contract:layers]
name = Module DAG layering
type = layers
layers =
    tracer_ai.api | tracer_ai.cli
    tracer_ai.rag | tracer_ai.eval
    tracer_ai.tracer | tracer_ai.corpus
    tracer_ai.config | tracer_ai.errors

[importlinter:contract:corpus-narrow]
name = corpus may import only rag.embedder, not full rag/
type = forbidden
source_modules =
    tracer_ai.corpus
forbidden_modules =
    tracer_ai.rag.pipeline
    tracer_ai.rag.llm
    tracer_ai.rag.retriever
    tracer_ai.rag.prompt
```

**Pre-commit integration:**
```yaml
- repo: local
  hooks:
    - id: import-linter
      name: import-linter (module DAG)
      language: system
      entry: bash -c 'uv run lint-imports'
      files: ^tracer_ai/.*\.py$
      pass_filenames: false
```

**Recommendation for plan-phase:** **Surface `import-linter` as a counter-proposal to D-2.27** before writing the 60-line custom guard. The tradeoff:
- ✅ **import-linter:** Maintained, tested by ~500K downloads/month, supports Layers contracts (less config to write), better error messages.
- ✅ **Custom 60-line guard:** Zero new deps, zero learning curve, fully owned, simpler diagnosis when it misfires.
- The custom guard's value is *demonstrating engineering discipline* in a portfolio context. The off-the-shelf path's value is *not maintaining a custom AST walker*. For a 12-hour portfolio budget, off-the-shelf wins; for a "show your work" portfolio narrative, custom can win.

**Pitfall to avoid:** If keeping the custom guard, it must build the full call graph (not just direct imports per file). A naive `import X` greps misses `from tracer_ai.rag import pipeline` which is the dominant pattern.

**Source:** [import-linter.readthedocs.io](https://import-linter.readthedocs.io/en/stable/usage.html); [github.com/seddonym/import-linter](https://github.com/seddonym/import-linter); [pypi.org/project/import-linter](https://pypi.org/project/import-linter/) [VERIFIED 2026-05-04: Python 3.12 support confirmed]

---

### Topic 10: Multi-stage Dockerfile.frontend (Vite + Tailwind v3 + shadcn)

**Question:** Bind-mount + named volume for node_modules; node:20-alpine gotchas; npm vs pnpm.

**Finding:** Vite + Docker requires three things to work cleanly: (1) a named/anonymous volume at `/app/node_modules` to prevent the host's empty `node_modules` from masking the container's installed deps, (2) `CHOKIDAR_USEPOLLING=true` for HMR over Docker bind-mount events, (3) `--host 0.0.0.0` in the dev server (default is 127.0.0.1 which Docker port-forward can't reach). `node:20-alpine` is fine for shadcn (no native deps with binary requirements like sharp). Use `npm` — shadcn CLI works fine, no pnpm lockfile considerations.

**Code excerpt** (`infra/Dockerfile.frontend`):

```dockerfile
ARG NODE_VERSION=20.18.0  # pin minor + patch
FROM node:${NODE_VERSION}-alpine AS base
WORKDIR /app
ENV NODE_ENV=development

# ---- deps (cacheable) ----
FROM base AS deps
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# ---- dev (compose targets this) ----
FROM deps AS dev
COPY frontend ./
EXPOSE 5173
ENV CHOKIDAR_USEPOLLING=true
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---- prod (NOT BUILT in Phase 2) ----
FROM deps AS build
COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

**Compose volume pattern** (already shown in Topic 4):
```yaml
volumes:
  - ../frontend/src:/app/src
  - ../frontend/index.html:/app/index.html
  - /app/node_modules  # anonymous — preserves container's node_modules
```

**Pitfall to avoid:** Forgetting the anonymous `/app/node_modules` volume. The compose bind-mount `../frontend:/app` would otherwise overlay the host's `node_modules` (often empty or wrong-arch) on top of the container's installed `node_modules`, breaking every import.

**Source:** [docs.docker.com/guides/nodejs/develop](https://docs.docker.com/guides/nodejs/develop/); [vitejs/vite discussion #16102 — HMR in Docker](https://github.com/vitejs/vite/discussions/16102); [innokrea.com/dockerizing-the-frontend-do-it-right](https://www.innokrea.com/dockerizing-the-frontend-do-it-right-with-react-js-vite/)

---

### Topic 11: Pre-commit secret-scanning (`sk-ant-` literal)

**Question:** Use a homegrown grep, `gitleaks`, or `detect-secrets`?

**Finding:** **`gitleaks` is the recommended choice for a fresh project.** Single Go binary, 150+ built-in rules including a generic Anthropic API key pattern (`sk-ant-`), sub-second pre-commit execution, custom regex via `.gitleaks.toml`. `detect-secrets` is better for retrofitting onto an existing repo with existing secrets to baseline (`detect-secrets scan --baseline .secrets.baseline`); tracer-ai is greenfield, so this advantage doesn't apply.

The homegrown grep (`grep -rE "sk-ant-[a-zA-Z0-9_-]+" --include="*.py" --include="*.yml"`) catches the explicit Anthropic case but misses Voyage keys, generic high-entropy strings, AWS keys (relevant if Phase 7 deploy adds S3), and accidentally-committed `.env` files. The 30 lines of grep config drift over time.

**Code excerpt** (`.gitleaks.toml` — minimal custom rule for tracer-ai):

```toml
[allowlist]
paths = ['''\.env\.example$''']  # placeholder values are intentional

[[rules]]
id = "anthropic-api-key"
description = "Anthropic API key"
regex = '''sk-ant-[a-zA-Z0-9_-]{20,}'''
keywords = ["sk-ant-"]

[[rules]]
id = "voyage-api-key"
description = "Voyage AI API key"
regex = '''(?i)voyage[_-]?api[_-]?key\s*[:=]\s*["']?[a-zA-Z0-9_-]{20,}'''
keywords = ["voyage"]
```

**Pitfall to avoid:** Letting `.env.example`'s placeholder `sk-ant-REPLACE` trigger the scan. The allowlist path entry above prevents that.

**Source:** [github.com/gitleaks/gitleaks](https://github.com/gitleaks/gitleaks); [gitleaks/.pre-commit-hooks.yaml](https://github.com/gitleaks/gitleaks/blob/master/.pre-commit-hooks.yaml); [rafter.so/blog/secrets/secret-scanning-tools-comparison](https://rafter.so/blog/secrets/secret-scanning-tools-comparison)

---

### Topic 12: pytest-testmon vs pytest-picked

**Question:** Which is the right "changed-only" pre-commit hook in 2026?

**Finding:** Both are maintained.
- **`pytest-testmon`** (v2.2+): Builds a coverage-graph database tracking which tests cover which lines. After a code change, runs only tests whose covered lines changed. Persistent state (`.testmondata`); first run is full suite. Strength: *correct* selection (catches transitive impacts via the coverage graph). Weakness: extra DB file, ~1-2s overhead even on no-op runs.
- **`pytest-picked`** (v0.5+): Reads `git status` and runs tests in modified/added files. No state, no graph. Strength: zero overhead, no DB file. Weakness: misses tests in unchanged files that test changed code (the inverse-coverage gap).

**For Phase 2's "fast subset; full suite is CI-only" goal (D-2.28):** `pytest-testmon` is the better fit because the proactive coverage relationship matters as the codebase grows. For a 12-hour portfolio project, the difference is small either way; the full CI run catches whatever local hooks miss.

**Code excerpt** (testmon pre-commit hook):

```yaml
- repo: local
  hooks:
    - id: pytest-testmon
      name: pytest --testmon (changed-only)
      language: system
      entry: bash -c 'uv run pytest --testmon -q --no-header'
      types: [python]
      pass_filenames: false
      stages: [commit]
```

**Pitfall to avoid:** Committing `.testmondata` to git. Add to `.gitignore`. The DB is per-developer-machine; sharing it causes false negatives on other machines.

**Source:** [pypi.org/project/pytest-testmon](https://pypi.org/project/pytest-testmon/) (v2.2+ active 2025); [github.com/anapaulagomes/pytest-picked](https://github.com/anapaulagomes/pytest-picked); [www.testmon.org](https://www.testmon.org/)

---

## Plan dependency graph (advisory for the planner)

Per D-2.41/2.42/2.43, recommended ~5 plans with dependency edges. **The hard constraints are (a)→(b)→(c) sequential and (d) || (e) parallel-after-(c).**

```
                     ┌──────────────────────────┐
                     │ (a) Repo scaffold +      │
                     │     pyproject.toml +     │
                     │     tracer_ai package    │
                     │     skeleton +           │
                     │     .env.example +       │
                     │     .gitignore           │
                     │     [Voyage pricing      │
                     │      prereq exercised]   │
                     └─────────┬────────────────┘
                               │
                               ▼
                     ┌──────────────────────────┐
                     │ (b) Compose stack +      │
                     │     Dockerfile.backend + │
                     │     Dockerfile.frontend +│
                     │     db/init.sql          │
                     │     [boots green w/o     │
                     │      api/migrate yet —   │
                     │      placeholder commands]│
                     └─────────┬────────────────┘
                               │
                               ▼
                     ┌──────────────────────────┐
                     │ (c) Alembic env.py +     │
                     │     0001_initial.py +    │
                     │     migrate service      │
                     │     wired in compose +   │
                     │     condition:           │
                     │     service_completed_   │
                     │     successfully         │
                     └────┬───────────────┬─────┘
                          │               │
                          ▼               ▼
            ┌──────────────────────┐  ┌──────────────────────┐
            │ (d) FastAPI hello +  │  │ (e) Frontend         │
            │     /healthz +       │  │     skeleton +       │
            │     config.py +      │  │     Tailwind v3 +    │
            │     lifespan +       │  │     shadcn init +    │
            │     pool             │  │     hello / route +  │
            │                      │  │     .env.example     │
            └─────────┬────────────┘  └─────────┬────────────┘
                      │                         │
                      └─────────┬───────────────┘
                                │
                                ▼
                     ┌──────────────────────────┐
                     │ (f) Pre-commit +         │
                     │     ruff/mypy/tsc/       │
                     │     pytest-testmon/      │
                     │     gitleaks/            │
                     │     import-cycle-guard + │
                     │     README quick-start   │
                     │     [end-to-end          │
                     │      verification gate]  │
                     └──────────────────────────┘
```

**Note:** Plan (f) is split out from D-2.41's plan (e) for clarity — the wireframe-bound `Card`+`Button` UI is visually separable from the dev-tooling work, and (f) can sequence after both (d) and (e) so the import-cycle guard and tsc hook have real targets to lint. Plan-phase may merge (e)+(f) per D-2.41 discretion.

**Wave parallelization:** Wave 1 = (a). Wave 2 = (b). Wave 3 = (c). Wave 4 = (d) || (e). Wave 5 = (f).

---

## Validation Architecture

> Note: `workflow.nyquist_validation` is `false` in `.planning/config.json`. Including this section per the user's explicit additional_context request.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (latest) + pytest-asyncio |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `uv run pytest -q --testmon` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `tracer_ai.__version__` importable; `from tracer_ai.config import settings` succeeds with required env vars | unit (smoke import) | `uv run pytest tests/test_imports.py -x` | ❌ Wave 0 |
| INFRA-01 | `docs/decisions/` exists with 10 ADRs | smoke | `ls docs/decisions/*.md \| wc -l` (≥ 10) | n/a (filesystem assertion) |
| INFRA-02 | `docker compose up` reaches green for all 3 services | integration (manual + scripted) | `bash infra/scripts/smoke_compose.sh` (drives `docker compose up -d --wait` + `curl localhost:8000/healthz` + `curl localhost:5173/` + `docker compose exec db psql -U tracer -c '\dt'`) | ❌ Wave 0 |
| INFRA-02 | 6 tables + 3 partitions present after migrate | integration | `docker compose exec db psql -U tracer tracer_ai -tAc "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"` (assert traces, spans, span_payloads, feedback, regression_cases, chunks, spans_y2026m05, spans_y2026m06, spans_y2026m07) | ❌ Wave 0 |
| INFRA-02 | `vector` extension installed | integration | `docker compose exec db psql -U tracer -tAc "SELECT extname FROM pg_extension WHERE extname='vector'"` (assert `vector`) | n/a |
| INFRA-03 | No `:latest` in Dockerfiles or compose | unit | `grep -rE ':latest' infra/ \| wc -l` == 0 | n/a |
| INFRA-03 | Settings raises ValidationError when ANTHROPIC_API_KEY unset | unit | `uv run pytest tests/test_config_failfast.py -x` | ❌ Wave 0 |
| INFRA-04 | pre-commit blocks a deliberately-broken commit | integration (manual) | `pre-commit run --all-files` (assert non-zero exit when `tests/fixtures/broken.py` has type error) | ❌ Wave 0 |
| INFRA-04 | import-cycle guard rejects a forbidden edge | unit | `python infra/scripts/import_cycle_guard.py --test-fixture tests/fixtures/cycle_violation/` (assert non-zero) | ❌ Wave 0 |
| INFRA-05 | README contains the documented quick-start commands | unit | `grep -E '^docker compose up' README.md \| wc -l` ≥ 1 | n/a |

### Sampling Rate
- **Per task commit:** `uv run pytest -q --testmon` (changed-only, < 5s typical)
- **Per wave merge:** `uv run pytest -q` (full unit suite, < 30s)
- **Phase gate:** Full pytest + `bash infra/scripts/smoke_compose.sh` end-to-end fresh-checkout drill (the ROADMAP success criterion 1 reproduction)

### Wave 0 Gaps
- [ ] `tests/test_imports.py` — smoke imports (covers INFRA-01)
- [ ] `tests/test_config_failfast.py` — ValidationError on missing required env vars (covers INFRA-03)
- [ ] `tests/conftest.py` — `pytest_asyncio` mode + clean-env fixture
- [ ] `infra/scripts/smoke_compose.sh` — driver script for the fresh-checkout integration verification
- [ ] `tests/fixtures/cycle_violation/` — minimal violating package for import-cycle-guard test
- [ ] `tests/fixtures/broken.py` — deliberately-broken module for the pre-commit blocking demo
- [ ] pyproject `[tool.pytest.ini_options]` block: `asyncio_mode = "auto"`, `testpaths = ["tests"]`

---

## Security Domain

`security_enforcement: true` in `.planning/config.json` (ASVS Level 1, block on high). Including security domain per config.

### Applicable ASVS Categories (Phase 2 only)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 2 has no auth surface (ADR 009 — direction-only; no v1 code). README must state "no auth; firewall before exposing." |
| V3 Session Management | no | No sessions in Phase 2 |
| V4 Access Control | no | No access control surface |
| V5 Input Validation | yes | Pydantic v2 strict-mode (`extra="forbid"`) on `/healthz` response; D-2.39 enforces strict-mode globally for new schemas |
| V6 Cryptography | partial | Secrets handled via `SecretStr` in pydantic-settings; no hand-rolled crypto |
| V7 Error Handling | yes | `/healthz` returns 503 (not 500) on db unreachable per D-2.33 — error envelope follows `docs/api.md` ErrorResponse contract from Phase 3 onward |
| V8 Data Protection | yes | `.env` gitignored; `.env.example` placeholder values only; pre-commit gitleaks scan; D-2.23 forbids real secrets in `.env.example` |
| V14 Configuration | yes | All Docker tags pinned (D-2.36); `.dockerignore` excludes secrets and build artifacts (D-2.14); init.sql owns DB extension creation (D-2.09) so app user lacks SUPERUSER |

### Known Threat Patterns for {Python + FastAPI + Postgres + Vite}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Accidental secret commit (e.g., `.env` with real `sk-ant-...`) | Information Disclosure | gitleaks pre-commit hook + `.gitignore` `.env` + `.env.example` placeholders + D-2.23 grep |
| Latest tag pull supply-chain swap (e.g., `pgvector/pgvector:pg16` tag moved to compromised image) | Tampering | Pin Docker image digests (`@sha256:...`) — D-2.36 |
| Settings injection via env-var pollution (operator pastes `LOG_LEVEL=DEBUG; rm -rf /` ) | Tampering / Elevation of Privilege | Pydantic `Literal[...]` validation on enum-like settings (`LOG_LEVEL`, `ENABLE_RERANKER`); strict mode forbids extras |
| SQL injection in /healthz | Tampering | `/healthz` uses parameterless `SELECT 1` only; no user input touches DB in Phase 2 |
| Path traversal in static file serving | Information Disclosure | Vite dev server enforces project root; FastAPI does not serve static files in Phase 2 |
| CORS overly permissive | Information Disclosure | Phase 2 doesn't open CORS; Phase 3 adds explicit `CORSMiddleware` with allowlist |
| Container running as root | Elevation of Privilege | `Dockerfile.backend` should `RUN adduser --uid 1000 app && USER app` before CMD (Phase 2 plan should include — adds 2 lines) |
| Init.sql overprivileges app user | Elevation of Privilege | `init.sql` creates `tracer` role with NOSUPERUSER NOCREATEROLE; only DB owner of `tracer_ai` |

**ASVS Level 1 gate:** No high-severity findings expected in Phase 2 given the locked decisions. The container-as-non-root mitigation (last row above) is a small Phase 2 plan addition that should be flagged for the planner — it isn't in 02-CONTEXT.md but is ASVS Level 1 standard practice.

---

## Common Pitfalls (Phase 2 specific, in addition to the 12 in PITFALLS.md)

### Pitfall 1: Init.sql runs only once per data volume

**What goes wrong:** Operator changes `init.sql` (e.g., adds a new role), restarts compose, and the change doesn't apply.

**Why:** Postgres's `/docker-entrypoint-initdb.d/` mechanism runs ONLY on an empty data directory. Existing volumes skip it.

**How to avoid:** Document `docker compose down -v` in README troubleshooting. For Phase 2, this is fine — fresh checkouts have no existing volume.

**Warning sign:** "I changed init.sql but pg_extension shows no `vector`" → `docker compose down -v && docker compose up`.

### Pitfall 2: Alembic 0001_initial.py runs as `tracer` (non-superuser); `CREATE EXTENSION` fails

**What goes wrong:** Migration script includes `op.execute("CREATE EXTENSION vector")`; fails because `tracer` user lacks SUPERUSER role.

**Why:** Per D-2.09, extension creation belongs in `infra/db/init.sql` (run as `postgres` superuser by image init).

**How to avoid:** Audit `0001_initial.py` for any `CREATE EXTENSION` text before committing. The migration should assume `vector` already exists.

**Warning sign:** Migrate service exits with `permission denied to create extension "vector"`.

### Pitfall 3: `lifespan` shutdown not called on Compose `docker compose down`

**What goes wrong:** Pool isn't gracefully closed; logs show `connection terminated` warnings.

**Why:** Compose sends SIGTERM to PID 1 (uvicorn); uvicorn forwards to FastAPI lifespan. Works in single-worker mode; **fails with `--reload --workers > 1`**.

**How to avoid:** Phase 2 dev uses `uvicorn ... --reload` only (single worker). Don't add `--workers N` until prod.

**Warning sign:** "lifespan_closed" log doesn't appear on `docker compose down`.

### Pitfall 4: Vite HMR doesn't trigger after host file change

**What goes wrong:** Edit `frontend/src/App.tsx` on host; container doesn't reload.

**Why:** Docker bind-mounts emit different inotify events than native FS; Vite's `chokidar` defaults miss them.

**How to avoid:** `CHOKIDAR_USEPOLLING=true` env var (set in compose) AND `server: { watch: { usePolling: true } }` in `vite.config.ts`. Both belt-and-suspenders.

**Warning sign:** Save file → no rebuild → manual page refresh shows old content.

### Pitfall 5: `npm install` inside `Dockerfile.frontend` produces wrong-arch binaries

**What goes wrong:** Operator on macOS runs `npm install` on host THEN `docker compose up`. The host's `node_modules` (darwin-arm64 binaries for esbuild/rollup) gets bind-mounted into linux/amd64 container; Vite crashes.

**Why:** The compose example in Topic 4 already mitigates via the anonymous `/app/node_modules` volume; this is a reminder.

**How to avoid:** Never run `npm install` on host. Always go through `docker compose run web npm install` if deps change.

**Warning sign:** `Error: Cannot find module '@rollup/rollup-linux-x64-gnu'` on first compose up.

---

## Code Examples (consolidated cross-reference)

The Topic 1-12 sections above contain the canonical 5-25 line code excerpts the executor will adapt. Quick index:

| Asset | Topic | Lines |
|-------|-------|-------|
| `infra/Dockerfile.backend` | Topic 1 | ~30 |
| `alembic/env.py` | Topic 2 | ~40 |
| `alembic/versions/0001_initial.py` | Topic 2 | ~70 |
| `tracer_ai/api/main.py` (lifespan + pool) | Topic 3 | ~25 |
| `tracer_ai/api/health.py` | Topic 3 | ~30 |
| `infra/docker-compose.yml` | Topic 4 | ~50 |
| `tracer_ai/config.py` | Topic 5 | ~40 |
| `.env.example` | Topic 5 | ~10 |
| `.pre-commit-config.yaml` | Topic 6 | ~50 |
| `frontend/components.json` | Topic 7 | ~20 |
| `frontend/vite.config.ts` | Topic 7 | ~10 |
| `frontend/src/App.tsx` | Topic 7 | ~15 |
| `infra/Dockerfile.frontend` | Topic 10 | ~25 |
| `.gitleaks.toml` | Topic 11 | ~15 |
| `.importlinter` (counter-proposal) | Topic 9 | ~20 |

---

## State of the Art

| Old Approach | Current Approach (2026-05) | When Changed | Impact |
|--------------|----------------------------|--------------|--------|
| `pip-tools` / `poetry` for dep mgmt | `uv` | uv hit 1.0 in 2025; 10-100× faster cold install | D-2.05 — Phase 2 adopts uv |
| `engine_from_config()` in Alembic env.py | `async_engine_from_config()` + `connection.run_sync()` | Alembic 1.10+ ships official async template | Topic 2 — must use async pattern with asyncpg |
| FastAPI `@app.on_event("startup")` | `lifespan=` async context manager | FastAPI deprecated startup events in 0.100+ | Topic 3 — use lifespan |
| `gen_ai.system` OTel attribute | `gen_ai.provider.name` | OTel GenAI spec deprecated `gen_ai.system` in 2025 | D-2.40 — Phase 2 stub uses provider.name only |
| Pydantic v1 `class Config:` | Pydantic v2 `model_config = ConfigDict(...)` | Pydantic 2.0 GA in 2023 | D-2.39 — Phase 2 uses v2 idiom |
| Tailwind v3 `@layer` with `tailwind.config.js` | Tailwind v4 `@theme` in CSS | Tailwind v4 GA in 2025 | **D-2.30 explicitly stays on v3** because Tremor + shadcn lag |
| React 18 createRoot pattern | React 19 server components | React 19 GA in 2024-2025 | **D-2.30 explicitly stays on 18** for shadcn/Tremor stability |
| Compose `version: "3.8"` field | Compose v2 (no version field) | Compose v2 plugin format made `version:` obsolete | Topic 4 — omit version field |

**Deprecated / outdated to NOT use:**
- `opentelemetry-sdk` runtime — ADR 005
- `ankane/pgvector` Docker image — D-2.08 specifies `pgvector/pgvector:pg16` (the official image; `ankane/pgvector` is the older alias)
- Class-based Pydantic v1 config — D-2.39
- `axios` — STACK.md prefers `ky` (Phase 3+ frontend; Phase 2 doesn't need either)

---

## Assumptions Log

> All claims tagged `[ASSUMED]` or unverifiable in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `claude-haiku-4-5-20251001` is a real dated snapshot (used in `LLM_JUDGE_MODEL` default, D-2.19) | User Constraints / Settings | LOW — config default; real value is wired in Phase 5 EVAL-01; if name shifts, change one constant. The MODEL ID format is correct (`claude-{family}-{ver}-{date}`); the specific 2025-10-01 date may or may not exist as a public snapshot. **Plan-phase should defer LLM_JUDGE_MODEL pin until Phase 5.** |
| A2 | `pgvector/pgvector:pg16` is the canonical image name (D-2.08) | Standard Stack | MEDIUM — image name verified in 02-CONTEXT.md and STACK.md; specific tag (e.g., `pg16-v0.7.4`) and digest must be re-verified at execute time |
| A3 | uv 0.5+ Docker image at `ghcr.io/astral-sh/uv:latest` is digest-pinnable at execute time | Topic 1 | LOW — Astral publishes digests; planner picks at execute time |
| A4 | Compose v2.20.0+ is universally available on operator machines (Docker Desktop ships it) | Topic 4 | LOW — Docker Desktop 2024+ ships v2.20+ |
| A5 | shadcn CLI 3.5+ supports Tailwind v3 detection on init (won't force v4) | Topic 7 | MEDIUM — shadcn ecosystem may make v4 the default and require explicit downgrade flag. Manual pre-install of Tailwind v3 BEFORE running shadcn init is the bulletproof path. |
| A6 | `import-linter` Layers contracts handle the exact `config|errors → tracer|corpus → rag|eval → api|cli` shape without custom adapter logic | Topic 9 | LOW — verified in import-linter docs; if Layers contract syntax differs slightly, the `.importlinter` config in Topic 9 is editable in minutes |
| A7 | The `default_factory=lambda: DBSettings.model_validate({})` trick triggers nested `validation_alias` resolution against `os.environ` at top-level Settings construction | Topic 5 | **MEDIUM-HIGH** — pydantic-settings nested behavior has shifted across releases. Plan-phase MUST validate this trick on the actual installed pydantic-settings version, OR fall back to flat Settings (the simpler counter-proposal). |
| A8 | `npm`-installed shadcn CLI's `npx shadcn@latest add card button` works in 2026 (CLI namespace stable) | Topic 7 | LOW — verified via WebSearch; CLI command surface stable since shadcn@2.x |

**Items requiring user confirmation before plan-phase:**
- A7 specifically — the nested-Settings-with-flat-env-vars behavior should be either verified in Phase 2 task 1 OR the simpler flat Settings counter-proposal accepted.
- A1 — LLM_JUDGE_MODEL default may need to be `claude-haiku-3-5-20241022` or whatever current dated snapshot is verified in Phase 5.

---

## Open Questions

1. **Should Phase 2 adopt `import-linter` (off-the-shelf) over the custom 60-line guard (D-2.27)?**
   - What we know: Both work; `import-linter` is maintained, more featureful, ~zero maintenance.
   - What's unclear: Portfolio narrative weighs hand-rolled engineering discipline; off-the-shelf weighs pragmatic correctness.
   - Recommendation: Plan-phase explicitly proposes `import-linter` to the operator. If declined, custom guard implementation must walk the full AST (not regex grep `import` lines).

2. **Should D-2.20 nested `Settings.db.url` shape be relaxed to flat `Settings.database_url`?**
   - What we know: pydantic-settings v2 nested models with flat env-var aliases require `default_factory` tricks (Topic 5 A7).
   - What's unclear: Whether Phase 3+ benefits from the nested grouping outweigh the implementation tax.
   - Recommendation: Adopt flat Settings for Phase 2; revisit when Phase 3 adds `corpus.*` or `tracer.*` config blocks. Saving the nested layer is a one-line `alembic` config change later.

3. **Should the container run as non-root in `Dockerfile.backend` dev stage?**
   - What we know: ASVS V14 standard practice; adds 2 lines (`RUN adduser app && USER app`).
   - What's unclear: D-2.11 doesn't specify; not a 02-CONTEXT.md decision.
   - Recommendation: Plan-phase adds `USER app` to the `dev` and `prod` stages. Low effort, high security upside.

4. **Frontend base color in shadcn init: `slate` was 02-CONTEXT.md's example but isn't in latest shadcn CLI list.**
   - What we know: Latest shadcn lists Neutral/Stone/Zinc/Mauve/Olive/Mist/Taupe.
   - What's unclear: Which to pick (cosmetic).
   - Recommendation: `Zinc` for slate-adjacent grey aesthetic. Auto-decision; not a real constraint.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `git` | INFRA-01 (clone) | unverified — assumed | — | None — required |
| `docker` (engine) + `docker compose` v2.20+ | INFRA-02 | unverified — operator-side | — | None — required |
| Internet to PyPI / npm registry | INFRA-01 (`uv sync` + `npm ci`) | unverified | — | None for Phase 2 build; offline dev possible after first build |
| Internet to ghcr.io / Docker Hub | INFRA-02 (image pull) | unverified | — | Offline after first pull |
| Anthropic API key (`sk-ant-...`) | INFRA-03 (Settings validation only — not used Phase 2) | operator-supplied | — | Placeholder OK in `.env` for Phase 2 (Settings only validates non-empty); Phase 3+ requires real key |
| Voyage API key | INFRA-03 (Settings validation only — not used Phase 2) | operator-supplied | — | Same as above |

**Missing dependencies with no fallback:** Docker Desktop / engine, git. The operator must have these.

**Missing dependencies with fallback:** None for Phase 2 build path. Phase 3+ runtime requires real API keys; Phase 2 only requires non-empty Settings values.

---

## Sources

### Primary (HIGH confidence)

- [docs.astral.sh/uv/guides/integration/docker](https://docs.astral.sh/uv/guides/integration/docker/) — uv multi-stage Dockerfile pattern [VERIFIED 2026-05-04 via WebFetch]
- [github.com/astral-sh/uv-docker-example](https://github.com/astral-sh/uv-docker-example) — official reference implementation
- [github.com/sqlalchemy/alembic — alembic/templates/async/env.py](https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py) — canonical async env.py [VERIFIED via WebFetch]
- [alembic.sqlalchemy.org/en/latest/cookbook.html](https://alembic.sqlalchemy.org/en/latest/cookbook.html) — Alembic patterns
- [fastapi.tiangolo.com/advanced/events/](https://fastapi.tiangolo.com/advanced/events/) — FastAPI lifespan
- [docs.docker.com/compose/how-tos/startup-order/](https://docs.docker.com/compose/how-tos/startup-order/) — Compose startup ordering
- [docs.docker.com/reference/compose-file/services/](https://docs.docker.com/reference/compose-file/services/) — Compose service reference
- [docs.pydantic.dev/latest/concepts/pydantic_settings/](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — pydantic-settings v2
- [pre-commit.com/hooks.html](https://pre-commit.com/hooks.html) — pre-commit hook registry
- [github.com/astral-sh/ruff-pre-commit](https://github.com/astral-sh/ruff-pre-commit) — official Ruff pre-commit
- [ui.shadcn.com/docs/installation/vite](https://ui.shadcn.com/docs/installation/vite) — shadcn + Vite
- [ui.shadcn.com/docs/components-json](https://ui.shadcn.com/docs/components-json) — components.json schema
- [docs.voyageai.com/docs/pricing](https://docs.voyageai.com/docs/pricing) — Voyage pricing [VERIFIED 2026-05-04 via WebFetch — 200M free / $0.18 per 1M for voyage-code-3]
- [import-linter.readthedocs.io/en/stable/usage.html](https://import-linter.readthedocs.io/en/stable/usage.html) — import-linter
- [github.com/gitleaks/gitleaks](https://github.com/gitleaks/gitleaks) — gitleaks
- [pypi.org/project/pytest-testmon/](https://pypi.org/project/pytest-testmon/) — pytest-testmon

### Secondary (MEDIUM confidence — WebSearch verified against official source)

- [github.com/pydantic/pydantic-settings/issues/27](https://github.com/pydantic/pydantic-settings/issues/27) — nested + alias env loading edge case
- [github.com/fastapi/fastapi/discussions/9520](https://github.com/fastapi/fastapi/discussions/9520) — pool in lifespan
- [daniel.feldroy.com/posts/2025-10-using-asyncpg-with-fastapi-and-air](https://daniel.feldroy.com/posts/2025-10-using-asyncpg-with-fastapi-and-air) — recent 2025 lifespan + asyncpg post
- [pydevtools.com/handbook/how-to/how-to-use-uv-in-a-dockerfile/](https://pydevtools.com/handbook/how-to/how-to-use-uv-in-a-dockerfile/) — uv Dockerfile patterns
- [hynek.me/articles/docker-uv/](https://hynek.me/articles/docker-uv/) — Hynek Schlawack on uv + Docker
- [jaredkhan.com/blog/mypy-pre-commit](https://jaredkhan.com/blog/mypy-pre-commit) — mypy pre-commit `additional_dependencies`
- [rafter.so/blog/secrets/secret-scanning-tools-comparison](https://rafter.so/blog/secrets/secret-scanning-tools-comparison) — gitleaks vs detect-secrets vs TruffleHog
- [www.innokrea.com/dockerizing-the-frontend-do-it-right-with-react-js-vite/](https://www.innokrea.com/dockerizing-the-frontend-do-it-right-with-react-js-vite/) — Vite + Docker
- [github.com/vitejs/vite/discussions/16102](https://github.com/vitejs/vite/discussions/16102) — Vite HMR Docker
- [docs.docker.com/guides/nodejs/develop/](https://docs.docker.com/guides/nodejs/develop/) — Node.js dev containers

### Tertiary (LOW confidence — WebSearch only)

- [oneuptime.com/blog/post/2026-01-25-docker-compose-depends-on/view](https://oneuptime.com/blog/post/2026-01-25-docker-compose-depends-on/view) — depends_on patterns (cross-checked against official docs)

### Foundation (already-done research; cited verbatim)

- C:/Users/om.mengshetti/Desktop/tracer-ai/.planning/research/STACK.md — locked stack table
- C:/Users/om.mengshetti/Desktop/tracer-ai/.planning/research/ARCHITECTURE.md — module layout, anti-patterns
- C:/Users/om.mengshetti/Desktop/tracer-ai/.planning/research/PITFALLS.md — 12 cross-phase pitfalls
- C:/Users/om.mengshetti/Desktop/tracer-ai/docs/architecture.md — system diagram
- C:/Users/om.mengshetti/Desktop/tracer-ai/docs/module-deps.md — locked module DAG
- C:/Users/om.mengshetti/Desktop/tracer-ai/docs/data-model.md — DDL contract for 0001_initial.py
- C:/Users/om.mengshetti/Desktop/tracer-ai/docs/api.md — Pydantic v2 strict-mode reference
- C:/Users/om.mengshetti/Desktop/tracer-ai/docs/decisions/002,003,004,005,009-*.md — accepted ADRs
- C:/Users/om.mengshetti/Desktop/tracer-ai/.planning/phases/02-skeleton-infrastructure/02-CONTEXT.md — D-2.01..D-2.43

---

## Project Constraints (from CLAUDE.md)

The project's `CLAUDE.md` enforces these directives that the planner MUST honor:

1. **Tech stack locked** — Python 3.12+, FastAPI, Pydantic v2 (no v1); LLM = Anthropic Claude (Sonnet 4.5 / Haiku); Frontend = Vite + React 18 + TypeScript + Tailwind v3 + shadcn/ui; Containerization = Docker Compose v2.
2. **No orchestration framework** — direct Anthropic SDK only. NO LangChain / LlamaIndex.
3. **No `opentelemetry-sdk` runtime** — ADR 005; constants only.
4. **No SQLite for trace storage** — Postgres + JSONB only.
5. **No Chroma / Weaviate** — pgvector only.
6. **No React 19 / Tailwind v4** — pin to React 18.3.1 / Tailwind 3.4.x.
7. **No `axios`** — `ky` or native fetch (Phase 3+; not Phase 2).
8. **Code quality** — type hints everywhere, ruff + mypy --strict clean, Pydantic for all I/O, meaningful docstrings on public functions only.
9. **Modularity** — every external dependency behind a typed Python `Protocol`. No direct SDK calls outside the adapter file.
10. **Cost-conscious** — judge uses Haiku, bot uses Sonnet 4.5, embedding cache.
11. **GSD Workflow Enforcement** — work goes through `/gsd-quick`, `/gsd-debug`, or `/gsd-execute-phase`; no direct edits outside a GSD workflow.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version cross-referenced against PyPI/npm/Astral docs (2026-05-04)
- Architecture patterns: HIGH — design contracts already produced in Phase 1; Phase 2 is mechanical translation
- Topic 1 (uv Docker): HIGH — Astral docs verified via WebFetch
- Topic 2 (async Alembic + pgvector): HIGH — Alembic template verified via WebFetch; pgvector + partitioning patterns from data-model.md
- Topic 3 (FastAPI lifespan + asyncpg): HIGH — official FastAPI docs + recent 2025 community posts
- Topic 4 (Compose depends_on): HIGH — Docker docs verified
- Topic 5 (pydantic-settings nested): MEDIUM — flat-vs-nested env binding behavior shifts across pydantic-settings releases (Assumption A7)
- Topic 6 (pre-commit): HIGH — pre-commit.com registry + recent 2025 setup guides
- Topic 7 (shadcn): MEDIUM-HIGH — base color list shifted (Assumption A5)
- Topic 8 (Voyage pricing): HIGH — verified via WebFetch on 2026-05-04
- Topic 9 (import-linter): HIGH — verified maintained, Python 3.12 supported
- Topic 10 (Vite Docker): HIGH — community-standard pattern
- Topic 11 (gitleaks): HIGH — official repo
- Topic 12 (pytest-testmon): HIGH — actively maintained verified
- Pitfalls: HIGH — sourced from PITFALLS.md + Topic-specific failure modes
- Security: MEDIUM — ASVS Level 1 mapping is judgment; no Phase 2 security tests until plan-phase decides
- Validation: MEDIUM — section included per user request despite `nyquist_validation: false` in config

**Research date:** 2026-05-04
**Valid until:** 2026-06-04 for fast-moving (uv, shadcn CLI, pydantic-settings, FastAPI); 2026-08-04 for stable (Compose, Postgres, Alembic, pre-commit framework)
