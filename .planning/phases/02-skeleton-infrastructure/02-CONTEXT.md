# Phase 2: Skeleton & Infrastructure - Context

**Gathered:** 2026-05-04
**Status:** Ready for planning
**Mode:** `--auto` (recommended option auto-selected for every gray area)

<domain>
## Phase Boundary

Phase 2 produces a **reproducible, fail-fast development skeleton**. The outputs are infra and scaffolding only — no RAG logic, no tracer body, no UI components beyond a hello-world route.

Deliverables (one bullet per locked requirement):

1. **INFRA-01** — Repo scaffolds the canonical module layout from `docs/architecture.md`: `tracer_ai/` (Python package — `tracer/`, `rag/`, `eval/`, `corpus/`, `api/`, `cli/`, plus `errors.py` + `config.py`), `frontend/` (Vite + React 18 + TS + Tailwind v3 + shadcn/ui), `infra/` (Compose + Dockerfiles), and `docs/decisions/` directory.
2. **INFRA-02** — `docker compose up` from a fresh checkout boots three services green:
   - `db` — Postgres 16 with `pgvector` extension and the **full initial Alembic migration applied** (5 trace tables + `chunks` + 3 forward-rolling monthly `spans` partitions).
   - `api` — FastAPI hello-world (`GET /healthz` returns `200`).
   - `web` — Vite dev server serving a hello-world `/` route.
3. **INFRA-03** — All Docker image tags pinned (no `:latest`); `.env.example` checked in; `tracer_ai/config.py` is a Pydantic v2 `BaseSettings` that **validates every required env var at import time** and produces a clear, named error per missing var. The api container exits non-zero before binding the port if validation fails.
4. **INFRA-04** — Pre-commit hooks active and run on every commit:
   - `ruff` (lint + format) on backend
   - `mypy --strict` on `tracer_ai/`
   - `tsc --noEmit` on `frontend/`
   - `pytest -q` on changed test files (fast subset; full suite is CI-only)
   - **Import-cycle pre-commit guard** wired against `docs/module-deps.md` (D-45) — stops a commit that introduces an edge violating the locked DAG (`config → tracer → rag → eval → api/cli`; `corpus` imports `rag/embedder` only).
5. **INFRA-05** — README skeleton with `docker compose up` quick-start; the `docs/decisions/` directory already exists from Phase 1 — verify, do not recreate.

**Verification gate (single):** From a freshly cloned repo on a Linux/macOS host with Docker Desktop and `git` installed:

```
git clone <repo> && cd tracer-ai
cp .env.example .env  # set ANTHROPIC_API_KEY=sk-ant-... and VOYAGE_API_KEY=...
docker compose up --build
```

…starts all three services green, `curl localhost:8000/healthz` returns `{"status":"ok"}`, the frontend `http://localhost:5173/` shows a hello page, and `docker compose exec db psql -U tracer -c '\dt'` lists `traces`, `spans`, `span_payloads`, `feedback`, `regression_cases`, `chunks` plus `spans_y2026m05`/`spans_y2026m06`/`spans_y2026m07` partitions and the `vector` extension is enabled. Pre-commit hooks block a deliberately-broken commit (`mypy` violation in a stub file) on a fresh checkout.

**Out of scope this phase (deferred to later phases):**
- Any RAG logic in `rag/` (Phase 3 CORP/RAG/CHAT/ADMN)
- Any tracer body beyond stub modules + attribute-name constants file shape (constants populated from `docs/trace-schema.md` is fine; emission helpers come in Phase 4 TRCR-04)
- Any chat UI components beyond a hello route (Phase 3)
- Voyage AI pricing verification (a Phase 2 INFRA-01 **prereq** per ADR 003 — operator must check `docs.voyageai.com/docs/pricing` and tick the ADR 003 checkbox before INFRA-01 closes; the discuss/plan/execute pipeline must NOT consume Voyage API credit just to verify pricing)
- CI / GitHub Actions config — README only mentions "CI runs on push" intent; actual workflow file deferred to Phase 7 polish
- Multi-arch Docker image builds — single `linux/amd64` is the target

</domain>

<decisions>
## Implementation Decisions

### Repo Layout (D-2.01..D-2.04)
- **D-2.01:** **Flat layout at repo root.** `tracer_ai/` (Python package), `frontend/`, `infra/` are siblings — matches `docs/architecture.md` §"Recommended Project Structure" verbatim. NOT a `backend/tracer_ai/` nested layout.
- **D-2.02:** `tracer_ai/__init__.py` exposes only `__version__` (PEP 396); cross-module imports go through explicit submodule paths (e.g., `from tracer_ai.tracer.span import Span`) so the import-cycle pre-commit guard can grep them mechanically.
- **D-2.03:** `infra/` contains: `docker-compose.yml`, `Dockerfile.backend` (multi-stage), `Dockerfile.frontend` (multi-stage), `db/init.sql` (creates the `tracer` role and `tracer_ai` database; `CREATE EXTENSION IF NOT EXISTS vector` runs here, not in the Alembic migration, so the extension is owned by Postgres init, not application schema).
- **D-2.04:** `docs/decisions/` already exists (Phase 1 created it with 10 ADRs). Phase 2 only **verifies** its presence as part of INFRA-05 — does not recreate.

### Python Dependency Manager (D-2.05..D-2.07)
- **D-2.05:** **`uv` is the dependency manager.** `pyproject.toml` is the single source of truth; `uv.lock` is committed. Justification: faster than Poetry/`pip-tools` (10–100× cold installs); single static binary in CI/Docker; native `pyproject.toml`; reproducible locks. Tradeoff acknowledged: less mature than Poetry, but the API surface used here (`uv sync`, `uv pip compile`, `uv run`) has been stable since `uv 0.4`.
- **D-2.06:** `pyproject.toml` **declares Python 3.12 as the lower bound** (`requires-python = ">=3.12,<3.13"`). 3.13 is excluded for the v1 build — wider Docker image availability (`python:3.12-slim-bookworm`) and one less compatibility variable for downstream agents to reason about.
- **D-2.07:** Two dependency groups in `pyproject.toml`: `[project.dependencies]` (runtime: `fastapi`, `pydantic[v2]`, `pydantic-settings`, `anthropic`, `voyageai`, `sentence-transformers`, `pgvector`, `asyncpg`, `sqlalchemy[asyncio]`, `alembic`, `uvicorn[standard]`, `httpx`, `structlog`, `tiktoken`, `python-multipart`) and `[project.optional-dependencies].dev` (`ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pre-commit`, `types-*` stubs as needed). Phase 2 installs both via `uv sync --all-extras` in dev images.

### Postgres Image & Extension Activation (D-2.08..D-2.10)
- **D-2.08:** **`pgvector/pgvector:pg16` is the database image.** Pinned to a dated tag (e.g., `pgvector/pgvector:pg16-v0.7.4` or whichever tag is current at execute time — pin the *digest*, not just the floating tag). NOT `ankane/pgvector` (deprecated alias) and NOT `postgres:16` + manual extension install (extra failure surface).
- **D-2.09:** `vector` extension is created by `infra/db/init.sql` on first container start (Postgres mounts files in `/docker-entrypoint-initdb.d/` only on empty data volumes — perfect for "fresh `docker compose up`"). The Alembic initial revision assumes the extension exists and **does not** issue `CREATE EXTENSION` itself (no permission to do so as the application user).
- **D-2.10:** `db` service exposes 5432 ONLY on the Compose internal network by default; an opt-in `ports: ["5432:5432"]` line is commented in the compose file with a security note ("uncomment for psql from the host; do not commit uncommented").

### Docker Image Strategy (D-2.11..D-2.14)
- **D-2.11:** **Single multi-stage `Dockerfile.backend`.** Stages: `base` (python:3.12-slim-bookworm + system deps), `deps` (uv + `uv sync --frozen`), `dev` (deps + bind-mount source + `uvicorn --reload`), `prod` (deps + `COPY tracer_ai/` + `uvicorn`). Compose targets `dev` for local; `prod` is reserved for v1.5 deployment ADR 009.
- **D-2.12:** **Bind-mount source for dev hot-reload.** `volumes: ["./tracer_ai:/app/tracer_ai", "./pyproject.toml:/app/pyproject.toml", "./uv.lock:/app/uv.lock"]`. The image still `COPY`s source so `prod` builds work without the host filesystem.
- **D-2.13:** Single multi-stage `Dockerfile.frontend`: `node:20-alpine` base, `deps` (npm ci), `dev` (vite dev server with bind-mounted source + node_modules volume), `prod` (vite build + nginx static-serve). Compose targets `dev`.
- **D-2.14:** `.dockerignore` mirrors `.gitignore` plus `node_modules/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `dist/`, `*.log` — keep build context lean.

### Migration Tooling at Boot (D-2.15..D-2.18)
- **D-2.15:** **A separate one-shot `migrate` service in compose.** It runs `alembic upgrade head` and exits. The `api` service has `depends_on: { migrate: { condition: service_completed_successfully }, db: { condition: service_healthy } }`. This makes startup ordering explicit and stops the api binding port until migrations finish — reproducibility property (INFRA-02 success criterion 1) flows directly from this.
- **D-2.16:** `alembic.ini` lives at repo root; `alembic/` directory holds env.py and `versions/`. `env.py` reads the DSN from `tracer_ai.config.Settings` — the same `Settings` class the api uses, so a config-mismatch between migration and api is impossible.
- **D-2.17:** **Initial Alembic revision content = full DDL from `docs/data-model.md` verbatim** (5 trace tables + `chunks` + 3 forward-rolling monthly `spans` partitions for `2026-05`, `2026-06`, `2026-07`). The revision filename is timestamped (`alembic revision --autogenerate` is NOT used for the initial migration — the DDL is hand-curated to match the locked spec; autogenerate is opt-in for subsequent revisions only).
- **D-2.18:** Partition-creation strategy for future months: a Python helper `tracer_ai/cli/partition.py` exposes `create_next_month_partition()` callable as `python -m tracer_ai.cli partition create-next-month`. Phase 2 installs the helper but does NOT wire a cron — operator runs it monthly. Cron / scheduled task wiring is Phase 7 polish.

### Environment Variables, Validation, and Secrets (D-2.19..D-2.23)
- **D-2.19:** **Single `Settings` class in `tracer_ai/config.py`** built on `pydantic-settings.BaseSettings`. Required vars (Phase 2 set):
  - `DATABASE_URL` (postgresql+asyncpg DSN; **required**)
  - `ANTHROPIC_API_KEY` (**required** — even though no LLM call happens in Phase 2 hello-world; required so the fail-fast behavior is verifiable end-to-end)
  - `VOYAGE_API_KEY` (**required** — same rationale)
  - `EMBEDDING_MODEL` (default `voyage-code-3`; reserved for Phase 3)
  - `LLM_BOT_MODEL` (default `claude-sonnet-4-5-20250929`)
  - `LLM_JUDGE_MODEL` (default `claude-haiku-4-5-20251001`)
  - `LOG_LEVEL` (default `INFO`)
  - `ENABLE_RERANKER` (default `false`; reserved per ADR 007)
- **D-2.20:** Nested namespaces (`Settings.db`, `Settings.anthropic`) modeled as nested `BaseModel` fields — keeps the import surface flat (`from tracer_ai.config import settings`) while letting downstream phases group new vars without renaming existing ones.
- **D-2.21:** **Fail-fast at import time.** `settings = Settings()` at module top level; missing required vars raise `pydantic.ValidationError` before the api process even reaches `uvicorn.run()`. The validation error message is human-readable (e.g., `"ANTHROPIC_API_KEY: field required"`).
- **D-2.22:** **`.env` (gitignored) + `.env.example` (committed)** loaded via Compose `env_file:` directive. NOT Docker secrets in v1 (ADR 009 defers production hardening). `.env.example` is the canonical "what you need to set" reference and lives in repo root.
- **D-2.23:** No env var contains a real secret in `.env.example` — values are placeholders (`ANTHROPIC_API_KEY=sk-ant-REPLACE`, `DATABASE_URL=postgresql+asyncpg://tracer:tracer@db:5432/tracer_ai`). README setup section instructs the operator to copy and edit. Pre-commit hook scans staged files for the literal string `sk-ant-` outside `.env.example` to prevent accidental secret commits.

### Pre-commit & Tooling (D-2.24..D-2.28)
- **D-2.24:** **`pre-commit` framework** via `.pre-commit-config.yaml`. Hooks (in order): `ruff` (lint), `ruff-format`, `mypy --strict tracer_ai/`, `tsc --noEmit -p frontend/tsconfig.json`, `pytest -q --testmon` (changed-only), `import-cycle-guard.py` (custom; reads `docs/module-deps.md` and asserts `tracer_ai/` imports satisfy the DAG).
- **D-2.25:** **`ruff` config** in `pyproject.toml [tool.ruff]`: target-version `py312`; rules `E,F,I,UP,B,SIM,RUF`; `pydantic`-aware: do not flag `Settings(BaseSettings)` patterns; line-length 100.
- **D-2.26:** **`mypy` config**: `--strict` everywhere under `tracer_ai/`; `[[tool.mypy.overrides]]` per third-party module without stubs (`voyageai`, `pgvector`, `tiktoken` if needed) marked `ignore_missing_imports = true`. NO `# type: ignore` comments unless paired with a TODO referencing a tracked issue.
- **D-2.27:** **Import-cycle guard** is a 60-line Python script at `infra/scripts/import_cycle_guard.py`. It (a) walks `tracer_ai/` AST, (b) builds the directed import graph at module-package granularity (`tracer_ai.tracer`, `tracer_ai.rag`, etc.), (c) compares against the locked DAG in `docs/module-deps.md`, (d) exits non-zero on any edge that violates the DAG. Visual acyclicity from Phase 1 plus runtime enforcement here = Pitfall avoidance for downstream phases.
- **D-2.28:** Hooks run on every `git commit`. CI (deferred to Phase 7) re-runs the same hooks plus the FULL `pytest` suite (not changed-only). Tiered design — fast loop locally, exhaustive on CI — is the standard cost/friction balance.

### Frontend Skeleton Scope (D-2.29..D-2.32)
- **D-2.29:** **Frontend skeleton = vite + react-ts + tailwind v3 + shadcn init + one `/` route showing a `Card` "Hello tracer-ai" page.** Not "vite hello-world only" because Phase 3 immediately needs the Tailwind + shadcn + react-router scaffolding; doing it in Phase 3 instead would mix infra and feature work.
- **D-2.30:** `frontend/package.json` pins:
  - `react@^18.3.1`, `react-dom@^18.3.1`, `typescript@~5.5`, `vite@^5`, `tailwindcss@^3.4`, `@tremor/react@^3`, `@tanstack/react-query@^5`, `react-router-dom@^6`, `clsx`, `tailwind-merge`, `lucide-react`. **Tailwind v3 pin is critical** (Tremor v3 + shadcn/ui both require v3; v4 breaks both).
- **D-2.31:** `shadcn` initialized with default config (`components.json` checked in); only `Card` and `Button` components scaffolded in Phase 2 — additional components added by feature phases as needed.
- **D-2.32:** `frontend/.env.example` carries `VITE_API_BASE_URL=http://localhost:8000`. README's "what to set" section calls out backend AND frontend env files.

### Health Check Contract (D-2.33..D-2.35)
- **D-2.33:** **`GET /healthz`** is the only api endpoint Phase 2 ships. Returns `{"status": "ok", "version": tracer_ai.__version__, "db": "ok" | "unreachable"}`. The `db` field is set by attempting one `SELECT 1` against the pool with a 500ms timeout; a Postgres outage produces `"unreachable"` and HTTP 503 (not 500 — important for orchestration).
- **D-2.34:** Compose `healthcheck` for `db` uses `pg_isready -U tracer`. `healthcheck` for `api` uses `curl --fail http://localhost:8000/healthz`. `web` has no healthcheck (Vite dev is too noisy; Phase 7 production image will add one).
- **D-2.35:** README's quick-start section ends with the exact `curl localhost:8000/healthz | jq` command and expected output — this is the verifiable acceptance test for INFRA-02.

### Anti-Patterns Baked Into the Skeleton (D-2.36..D-2.40)
- **D-2.36:** No `:latest` tag anywhere in `docker-compose.yml`, `Dockerfile.*`, or `package.json` (lockfile pins). Pre-commit grep enforces.
- **D-2.37:** No raw `print(...)` in `tracer_ai/`. Logging goes through `structlog.get_logger()`. Pre-commit grep enforces (allowlist: `tracer_ai/cli/__main__.py` may use `print` for CLI output once that exists in Phase 6).
- **D-2.38:** No SDK imports outside their adapter file. Pre-commit grep enforces: `from anthropic` is only allowed in `tracer_ai/rag/llm.py` and `tracer_ai/eval/llm_judge.py`; `from voyageai` only in `tracer_ai/rag/embedder.py`. (These files don't exist yet in Phase 2; the rule still ships so Phase 3 implementers can't drift.)
- **D-2.39:** No `class Config:` (Pydantic v1) blocks anywhere. `model_config = ConfigDict(...)` is the v2 idiom — matches `docs/api.md` D-26 contract.
- **D-2.40:** No `gen_ai.system` constant. `tracer_ai/tracer/span.py` (skeleton stub in Phase 2; full body in Phase 4 TRCR-01) carries only `gen_ai.provider.name` per ADR 005 / D-22 — and a comment-out line for `gen_ai.system` with the deprecation note. Pre-commit grep flags any occurrence of the string `gen_ai.system` (outside the comment-out line that explicitly says DEPRECATED).

### Plan-Time Decisions Reserved for the Planner (D-2.41..D-2.43)
- **D-2.41:** **Number and order of plans.** Recommend ~5 plans: (a) Repo scaffold + pyproject + tracer_ai package skeleton, (b) Compose + Dockerfiles + db/init.sql, (c) Alembic + initial migration + migrate service, (d) FastAPI hello + /healthz + config.py, (e) Frontend skeleton + Tailwind/shadcn + pre-commit + import-cycle guard + README. Planner may merge or split; the dependency edges between (a)→(b)→(c)→(d) and (a)→(e) are the only hard constraints.
- **D-2.42:** **Wave parallelization.** Plans (d) and (e) can run in parallel after (c). Plans (a)→(b)→(c) are strictly sequential.
- **D-2.43:** **Verification ordering inside each plan.** Each plan ends with a `<verify>` block that exercises only what that plan changed (e.g., the Alembic plan greps `\dt` output for the 6 expected tables; the api plan curls `/healthz`). The phase-end verifier (post all plans) runs the end-to-end fresh-checkout drill against ROADMAP success criteria 1.

### Claude's Discretion
The discuss step ran in `--auto` mode: every D-2.* decision above is the **recommended option** drawn from `docs/architecture.md`, `docs/data-model.md`, ADRs 001–010, and the locked stack in PROJECT.md. None required user judgment beyond what the research already validated. The planner may surface counter-evidence on any decision during plan-phase; the user retains override authority on:
- D-2.05 (`uv` vs Poetry — if the operator already has Poetry muscle memory)
- D-2.15 (separate `migrate` service vs entrypoint-baked migrations — ergonomics tradeoff)
- D-2.29 (frontend skeleton scope — could shrink to vite-only-hello-world if Phase 3 budget is tighter than expected)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before planning or implementing.**

### Foundation & Vision
- `tracer-ai-foundation-prd.md` — locked foundation PRD; canonical "why" + "what"
- `About.md` — original brief; one-paragraph framing
- `.planning/PROJECT.md` — project guardrails, locked tech stack, Out of Scope list, Key Decisions table
- `.planning/REQUIREMENTS.md` §"Infrastructure (Phase 2)" — INFRA-01..05 requirement bodies and verification language
- `.planning/ROADMAP.md` §"Phase 2: Skeleton & Infrastructure" — phase goal, depends_on, success criteria

### Phase 1 Outputs (Phase 2 implements against these contracts)
- `docs/architecture.md` — system overview + component responsibilities + module dependency graph (the layout `tracer_ai/` MUST match)
- `docs/module-deps.md` — locked module DAG (Phase 2 INFRA-04 import-cycle guard reads this directly)
- `docs/data-model.md` — Postgres DDL block + `chunks` schema + monthly partitioning convention (the **initial Alembic migration is a verbatim translation of this file**)
- `docs/trace-schema.md` — attribute name constants (Phase 2 stubs the constants file shape; Phase 4 TRCR-01 fills it in)
- `docs/api.md` — Pydantic v2 strict-mode shapes (Phase 2 only ships `/healthz` schema; the rest is Phase 3+ contract)
- `docs/sequence-diagrams.md` — request lifecycle diagram (informs `api/main.py` lifespan handler shape; Pitfall #1 mitigation pattern)
- `docs/wireframes/README.md` + 5 wireframe files — frontend component inventory (Phase 2 needs only `Card` + `Button` from shadcn)
- `docs/_verification.md` — Phase 1 verification report (proves the doc set is complete; Phase 2 entry unblocked)

### ADRs (every Phase 2 decision must cite at least one)
- `docs/decisions/001-charting-library.md` — Tremor v3 (informs `frontend/package.json` pins; Phase 2 installs but doesn't render charts yet)
- `docs/decisions/002-vector-store.md` — pgvector on Postgres (the `chunks` table in INFRA-02)
- `docs/decisions/003-embedding-provider.md` — Voyage AI primary; Voyage pricing checkbox is a Phase 2 INFRA-01 prereq
- `docs/decisions/004-trace-storage.md` — Postgres + JSONB; `spans` partitioned by `started_at` monthly
- `docs/decisions/005-observability-strategy.md` — NO `opentelemetry-sdk` runtime dep; constants-only (Phase 2 stubs the constants file)
- `docs/decisions/006-chunking-strategy.md` — markdown-aware chunker default (informs Phase 3; not Phase 2 implementation, but `EMBEDDING_MODEL` env var is reserved here)
- `docs/decisions/007-reranking.md` — `ENABLE_RERANKER=false` reserved env var
- `docs/decisions/008-judge-prompts-thresholds.md` — Haiku model dated snapshot (informs `LLM_JUDGE_MODEL` default)
- `docs/decisions/009-auth-deployment-direction.md` — no auth in v1; `prod` Dockerfile stage reserved, not built
- `docs/decisions/010-scope-trim.md` — cut order if budget slips >25%

### Research (already done; ADRs codified these — refer when ADR is silent)
- `.planning/research/STACK.md` — locked stack validation; alternatives + version compatibility table
- `.planning/research/ARCHITECTURE.md` — module layout, dep graph, anti-patterns, pgvector + Postgres consolidation rationale
- `.planning/research/PITFALLS.md` — 12 pitfalls with phase mapping (Phase 2 mitigates Pitfalls 2 + 3 by infra design)
- `.planning/research/SUMMARY.md` — executive summary (use when ADRs are insufficient)
- `.planning/research/FEATURES.md` — competitor parity + differentiator gap

### Phase 1 Discuss Artifact (precedent for this phase)
- `.planning/phases/01-research-design-artifacts/01-CONTEXT.md` — Phase 1 decisions, including D-32 query schema and D-37 cut order

### Phase 2 State / Memory
- `.planning/STATE.md` §"Decisions" — running log; reaffirms DDL contract, `gen_ai.system` deprecation, embedding-metadata triple-column pattern
- `.planning/STATE.md` §"Blockers/Concerns" — Voyage AI pricing not yet confirmed; Tailwind v3 pin critical; judge calibration deferred

### External (cited; do not re-fetch in Phase 2 — citations live in research files)
- pgvector Docker image (`pgvector/pgvector:pg16` — pin a digest at execute time)
- `uv` documentation — `uv sync`, `uv lock`, project structure (Astral)
- pydantic-settings v2 — `BaseSettings` + nested model fields
- SQLAlchemy 2.0 async + asyncpg — `create_async_engine("postgresql+asyncpg://...")`
- Alembic — `env.py` async pattern + initial revision authoring
- pre-commit framework — `.pre-commit-config.yaml` schema
- Docker Compose v2 — `depends_on.condition: service_completed_successfully`
- shadcn/ui CLI v3.x init flow

### Outputs (created during Phase 2; become canonical for later phases)
- `pyproject.toml` + `uv.lock` — backend dep manifest (every Phase 3+ adapter adds deps here)
- `tracer_ai/config.py` — `Settings` class (every Phase 3+ env var added here)
- `tracer_ai/api/main.py` — FastAPI app + lifespan handler (Phase 3 adds routes; Phase 4 wires the trace queue lifespan)
- `infra/docker-compose.yml`, `infra/Dockerfile.backend`, `infra/Dockerfile.frontend`, `infra/db/init.sql` — Compose stack (Phase 3+ may add services like `worker` if needed; v1 plan does not require any)
- `alembic/versions/0001_initial.py` — full DDL initial revision (Phase 3+ revisions add to this; never edit `0001_initial.py`)
- `frontend/package.json` + `frontend/vite.config.ts` + `frontend/tailwind.config.js` + `frontend/components.json` — frontend manifest set
- `.pre-commit-config.yaml` + `infra/scripts/import_cycle_guard.py` — quality gates
- `.env.example` — env var contract
- `README.md` — quick-start section (Phase 7 polishes; Phase 2 ships a working skeleton)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **None yet at code level** — repo root contains `About.md`, `CLAUDE.md`, `tracer-ai-foundation-prd.md`, `README.md` (placeholder), the `.planning/` and `.claude/` directories, and the Phase 1 `docs/` tree. No `tracer_ai/`, `frontend/`, `infra/`, `alembic/`, `pyproject.toml` exist yet — Phase 2 creates all of them.
- The Phase 1 `docs/` tree IS a reusable asset: every Phase 2 decision is cross-referenced into ADRs and design docs that already exist on disk. Phase 2 is implementation against a fully-specified contract — no architecture discovery needed.

### Established Patterns
- **GSD planning lifecycle** — `.claude/get-shit-done/` workflows + `.planning/` state. Phase 2 follows discuss → plan → execute. Plans + commits live under `.planning/phases/02-skeleton-infrastructure/`.
- **Research is canonical, ADRs codify it, Phase 2 implements it** — no new architectural choices in Phase 2; only mechanical translation of locked decisions into infra.
- **`gen_ai.provider.name` (NOT `gen_ai.system`)** — Phase 1 STATE.md decisions reaffirm; Phase 2 stub of `tracer_ai/tracer/span.py` must reflect this from line 1.
- **Embedding-metadata triple-column pattern** — `embedding_model + embedding_model_version + indexed_at` on every vector table. Phase 2 initial migration writes this on the `chunks` table; future vector tables (Phase 3+ user-uploaded docs) repeat the pattern.
- **Pydantic v2 strict-mode in API schemas** — `model_config = ConfigDict(extra="forbid")`; no `Optional[...]` (use `str | None`); no `class Config:` v1 blocks. Phase 2 only ships `/healthz` response, but applies the rule from day one.

### Integration Points
- `tracer_ai.config.Settings` is imported by Alembic `env.py` AND `api/main.py` AND every future module. Drift is a bug; single source of truth lives in `tracer_ai/config.py`.
- `infra/db/init.sql` runs ONCE on first container boot (Postgres only sources `/docker-entrypoint-initdb.d/` on an empty data volume). Wiping `volumes:` re-runs it. Document this in the README troubleshooting section.
- Pre-commit hooks run before commit; CI (Phase 7) re-runs the same hooks plus full pytest. Drift = test that passes locally but fails CI; mitigation is identical hook config used in both places.
- The 6-table + chunks DDL block at `docs/data-model.md` is the **byte-for-byte content of `alembic/versions/0001_initial.py`** (with monthly partition statements expanded for the next 3 months). When `data-model.md` changes, a new revision is added (never edit `0001_initial.py`).
- The frontend `Card`/`Button` shadcn imports in Phase 2 must use the path conventions emitted by the `shadcn init` CLI (`@/components/ui/card`, `@/components/ui/button`) — Phase 3+ feature wireframes assume this alias.

</code_context>

<specifics>
## Specific Ideas

- **"Fresh-checkout boots green" is the verification mechanism** (per ROADMAP.md success criteria 1). Plan-phase should add a verification task that, on a clean clone, runs `cp .env.example .env`, sets only the two API keys, and runs `docker compose up --build` — and asserts all three healthchecks pass and `psql \dt` lists the expected tables/partitions. This is the gate.
- **Memory note honored:** "Design artifacts before any coding" — Phase 1 produced all docs; Phase 2 is the FIRST coding phase. Every Phase 2 decision cites a Phase 1 artifact.
- **Memory note honored:** "List alternatives in PRDs for downstream-agent research" — every D-2.* decision above either references the ADR that lists alternatives or names the rejected alternative inline (e.g., D-2.08 names `ankane/pgvector` and `postgres:16`+manual). Plan-phase / executor agents can reopen any decision if a constraint shifts.
- **Voyage pricing checkbox** must be exercised before INFRA-01 closes. Plan-phase should make it a `<prereq>` block on whichever plan creates `pyproject.toml` (so the operator confirms the price/quota of the embedding provider before committing the dep).
- **Self-referential narrative** does not surface in Phase 2 — no chat UI, no LLM calls, no corpus. Phase 3 picks up that thread.

</specifics>

<deferred>
## Deferred Ideas

- **CI / GitHub Actions workflow** — Phase 7 polish; Phase 2 README mentions intent only.
- **Docker secrets / production env hardening** — ADR 009; Phase 1.5+.
- **Multi-arch image builds** — `linux/amd64` only in v1; multi-arch is a portfolio polish item (Phase 7).
- **Production `prod` Dockerfile target** — defined as a stage in `Dockerfile.backend` so future deployment ADR 009 work is one `docker build --target prod` away, but NOT built/deployed in Phase 2.
- **Cron / scheduled task for monthly partition rotation** — helper installed (`tracer_ai/cli/partition.py create-next-month`) but not scheduled. Phase 7 polish.
- **`tracer/exporters/postgres.py` body** — Phase 2 stubs the file with the Protocol shape only; the async-queue body lives in Phase 4 TRCR-06.
- **Real `/healthz` DB probe via the SQLAlchemy pool** — Phase 2 ships the endpoint; Phase 3 wires the pool. Until then `/healthz` returns `db: "ok"` only when a `SELECT 1` succeeds via `asyncpg.connect()` directly.
- **Frontend `Tremor` chart usage** — installed in `package.json`; not rendered until Phase 5 dashboard work.
- **Voyage pricing verification** — INFRA-01 prereq, NOT a Phase 1 carry-over (Phase 1 deferred it explicitly). The plan-phase plan that creates `pyproject.toml` is where the checkbox gets exercised.

</deferred>

---

*Phase: 2-Skeleton & Infrastructure*
*Context gathered: 2026-05-04*
*Mode: --auto (recommended decisions auto-selected and logged inline above)*
