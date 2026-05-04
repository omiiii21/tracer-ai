---
phase: 02-skeleton-infrastructure
plan: 01
subsystem: infra
tags:
  - python-scaffold
  - uv
  - pyproject
  - pydantic-v2
  - tracer-ai
  - otel-genai
  - voyageai
  - infra-01
  - infra-03

# Dependency graph
requires:
  - phase: 01-research-design-artifacts
    provides: docs/architecture.md (Recommended Project Structure), docs/module-deps.md (locked DAG), docs/trace-schema.md (OTel attribute constants block), docs/decisions/003-embedding-provider.md (Voyage pricing follow-up checkbox), docs/decisions/005-observability-strategy.md (no opentelemetry-sdk runtime)
provides:
  - "Repo scaffold: pyproject.toml + uv.lock with all locked runtime + dev deps"
  - "tracer_ai/ Python package skeleton mirroring docs/architecture.md (15 .py files across 6 namespaces)"
  - "OTel-aligned attribute name constants block in tracer_ai/tracer/span.py (Phase 4 TRCR-01 fills emission helpers)"
  - ".env.example env-var contract (placeholder values only per D-2.23)"
  - ".gitignore + .dockerignore exclusions per D-2.14"
  - "tests/test_imports.py (16 test items) covering INFRA-01 smoke imports"
  - "Voyage AI pricing prereq resolved (ADR 003 follow-up checkbox ticked)"
affects:
  - 02-02-compose-dockerfiles  # Wave 2 mounts pyproject.toml + uv.lock as Dockerfile.backend deps stage
  - 02-03-alembic-migrations   # Wave 3 imports tracer_ai.config (lands in Wave 4)
  - 02-04-fastapi-config       # Wave 4 fills tracer_ai/config.py + api/main.py (FLAT Settings shape)
  - 02-05-frontend-precommit   # Wave 5 wires custom import-cycle guard against module-deps.md DAG
  - phase-04-tracing           # Phase 4 TRCR-01..06 fills tracer/span.py emission helpers + Postgres exporter

# Tech tracking
tech-stack:
  added:
    - "fastapi 0.128.x"
    - "pydantic 2.7+ + pydantic-settings 2.4+"
    - "sqlalchemy[asyncio] 2.0.x"
    - "asyncpg 0.29+"
    - "pgvector 0.3.x"
    - "alembic 1.13+"
    - "uvicorn[standard] 0.30+"
    - "anthropic 0.49+"
    - "voyageai 0.3+ (Voyage AI free-tier verified per ADR 003)"
    - "sentence-transformers 3.x (offline fallback per ADR 003)"
    - "structlog 24.x"
    - "tiktoken 0.7+"
    - "httpx 0.27+"
    - "python-multipart 0.0.9+"
    - "ruff 0.7+ + mypy 1.11+ (strict) + pytest 8.3+ + pytest-asyncio + pytest-testmon + pre-commit"
    - "uv 0.9.x (Python dep manager + Python 3.12 toolchain manager)"
    - "hatchling (build backend)"
  patterns:
    - "Flat repo layout: tracer_ai/ + tests/ siblings at repo root (D-2.01)"
    - "tracer_ai/__init__.py exposes ONLY __version__ per PEP 396 (D-2.02); cross-module imports go through explicit submodule paths"
    - "OTel attribute names as Python string constants centralized in tracer_ai/tracer/span.py — spec rename = one-line edit per constant (D-2.40)"
    - "gen_ai.system isolated to a single COMMENTED-OUT DEPRECATED marker line (T-2-01-04 mitigation)"
    - "Pydantic v2 idiom only: model_config = ConfigDict(...); no class Config: blocks anywhere (D-2.39)"
    - ".env.example placeholder discipline: short literal placeholders (sk-ant-REPLACE) below gitleaks regex threshold (T-2-01-01)"

key-files:
  created:
    - "pyproject.toml — backend dep manifest + ruff/mypy/pytest tool config"
    - "uv.lock — 130-package locked resolution"
    - ".gitignore — Python + node + env + IDE + .claude/ exclusions"
    - ".dockerignore — mirrors .gitignore plus .git/.planning/.claude/docs/ exclusions"
    - ".env.example — 8-var contract (3 required + 5 with defaults)"
    - "tracer_ai/__init__.py — __version__ = '0.1.0' only"
    - "tracer_ai/errors.py — TracerAIError base"
    - "tracer_ai/tracer/__init__.py — namespace stub"
    - "tracer_ai/tracer/span.py — OTel + rag.* attribute name constants block"
    - "tracer_ai/tracer/context.py — Phase 4 TRCR-04 stub"
    - "tracer_ai/tracer/store.py — Phase 4 TRCR-05 stub"
    - "tracer_ai/tracer/exporters/__init__.py — namespace stub"
    - "tracer_ai/tracer/exporters/postgres.py — Phase 4 TRCR-06 stub"
    - "tracer_ai/rag/__init__.py — Phase 3 stub"
    - "tracer_ai/eval/__init__.py — Phase 5 stub"
    - "tracer_ai/corpus/__init__.py — Phase 3 stub"
    - "tracer_ai/api/__init__.py — Wave 4 stub"
    - "tracer_ai/cli/__init__.py — Phase 6 stub"
    - "tracer_ai/cli/__main__.py — Phase 6 print-allowlisted entry"
    - "tracer_ai/cli/partition.py — create_next_month_partition() NotImplementedError stub (D-2.18)"
    - "tests/__init__.py — empty package marker"
    - "tests/conftest.py — clean_env fixture with sys.modules eviction for Wave-4 fail-fast tests"
    - "tests/test_imports.py — 16-item smoke-import suite for INFRA-01"
  modified:
    - "docs/decisions/003-embedding-provider.md — ticked Mandatory follow-ups Voyage pricing checkbox (verified 2026-05-04 free-tier coverage)"

key-decisions:
  - "Voyage AI pricing prereq resolved: 200M-token free tier per account (cumulative) covers Phase 3 corpus ingestion (~25M tokens for 50K chunks × 500 tokens/chunk); paid rate $0.18/1M not triggered. ADR 003 follow-up checkbox ticked."
  - "Open Question Q1 resolution: ship D-2.27 custom import-cycle guard for the portfolio narrative (60-line Python script reading docs/module-deps.md). import-linter alternative documented in Wave 5 plan as future swap per RESEARCH.md Topic 9."
  - "Open Question Q2 resolution: Wave 4 plan adopts FLAT Settings shape (no nested namespaces) per RESEARCH.md Topic 5 recommendation. D-2.20's nested-namespace rationale revisited; saved nested grouping is a future revision when var count exceeds ~12. Phase 2 Wave 1 dep list is unaffected."
  - "Empty [tool.uv] table reserved in pyproject.toml so future uv-specific keys (dev-dependencies, index-strategy, etc.) have a stable home without future churn."
  - "Hatchling chosen as build backend over setuptools — minimal config, no setup.py/setup.cfg, native [tool.hatch.build.targets.wheel].packages = [\"tracer_ai\"] declaration."

patterns-established:
  - "Repo skeleton authority: docs/architecture.md is the source of truth for the tracer_ai/ module shape; Phase 2 mirrors it verbatim"
  - "OTel attribute constants centralization: every gen_ai.* and rag.* attribute name is a Python constant in tracer_ai/tracer/span.py — spec rename = one-line edit, no pipeline-code touchpoints"
  - "Stub-with-purpose: every Phase 2 stub names its future owner (Phase X TRCR-NN, Phase Y polish) so readers can trace each empty file to a downstream plan"
  - "Threat-mitigation traceability: T-2-01-01 (.env.example real-key leak) and T-2-01-04 (gen_ai.system reintroduction) both have specific acceptance grep gates wired into the plan-end <verification>"
  - "uv dep groups: [project.dependencies] for runtime, [project.optional-dependencies].dev for tooling; uv sync --all-extras installs both for dev"

requirements-completed:
  - INFRA-01  # PARTIAL — Wave-4 closes config-failfast portion; Wave 1 closes scaffold portion
  - INFRA-03  # PARTIAL — Wave 4 wires Settings fail-fast at import; Wave 1 closes .env.example placeholder discipline

# Metrics
duration: 18min
completed: 2026-05-04
---

# Phase 2-01: Repo Scaffold Summary

**uv-managed Python 3.12 repo scaffold with `tracer_ai/` 15-file package mirror, OTel-aligned attribute constants block, .env.example contract, and 16-item smoke-import suite green (INFRA-01 + INFRA-03 partial).**

## Performance

- **Duration:** ~18 minutes
- **Started:** 2026-05-04 (Wave 1 of Phase 2 chain in `--auto` mode)
- **Completed:** 2026-05-04
- **Tasks:** 4 (Task 0 [BLOCKING] checkpoint + Tasks 1-3 auto)
- **Files created:** 23 (15 tracer_ai .py files + 6 dotfiles/test files + pyproject.toml + uv.lock)
- **Files modified:** 2 (.gitignore enhanced + docs/decisions/003-embedding-provider.md checkbox ticked)

## Accomplishments

- **Voyage pricing prereq cleared** (Task 0): ADR 003 Mandatory follow-ups checkbox ticked. RESEARCH.md Topic 8 verified 2026-05-04 — 200M-token free tier covers ~25M-token Phase 3 corpus ingestion. No paid spend required to close INFRA-01. Auto-approved per `--auto` chain workflow.
- **`pyproject.toml` + `uv.lock` shipped** (Task 1) with all locked deps from CLAUDE.md "Locked Stack Validation" table: 15 runtime deps + 7 dev deps. uv 0.9.26 resolved 130 packages in 1.81s. `requires-python = ">=3.12,<3.13"` per D-2.06; tooling config tables (`[tool.ruff]`, `[tool.mypy]` strict, `[tool.pytest.ini_options]` asyncio_mode=auto) all in place.
- **`tracer_ai/` 15-file package skeleton scaffolded** (Task 2) mirroring `docs/architecture.md` Recommended Project Structure verbatim across 6 namespaces (`tracer/`, `rag/`, `eval/`, `corpus/`, `api/`, `cli/`) plus root-level `errors.py`. The OTel-aligned attribute constants block from `docs/trace-schema.md` lives in `tracer_ai/tracer/span.py` ready for Phase 4 TRCR-01 emission helpers. `gen_ai.system` correctly isolated to a single commented-out DEPRECATED marker per D-2.40 / threat T-2-01-04.
- **Repo dotfiles + Wave-0 smoke-import suite shipped** (Task 3): `.gitignore` (Python + node + env + IDE + `.claude/` preserved), `.dockerignore` (mirrors gitignore + Docker-build-context exclusions per D-2.14), `.env.example` (8-var contract, sk-ant-REPLACE intentionally short to clear gitleaks regex per T-2-01-01), `tests/test_imports.py` (16 items: 1 version + 13 module imports + 1 OTel constants + 1 partition stub) all green.

## Task Commits

Each task was committed atomically:

1. **Task 0 [BLOCKING]: Verify Voyage AI pricing prereq (ADR 003)** — `76742e6` (docs)
2. **Task 1: Author pyproject.toml + uv.lock with locked deps and tool config** — `706e46a` (feat)
3. **Task 2: Create tracer_ai package skeleton with stub modules and OTel constants** — `c5b1f78` (feat)
4. **Task 3: Author .gitignore, .dockerignore, .env.example, and Wave-0 test scaffolding** — `3cbcb7a` (feat)

**Plan metadata:** orchestrator owns final phase commit (per `<sequential_execution>` mandate; STATE.md/ROADMAP.md untouched).

## Files Created/Modified

### Created (23 files)

**Backend dep manifest (Task 1):**
- `pyproject.toml` — runtime + dev dep groups; ruff/mypy/pytest tool config; hatchling build backend
- `uv.lock` — 130-package deterministic resolution

**`tracer_ai/` package skeleton (Task 2):**
- `tracer_ai/__init__.py` — `__version__ = "0.1.0"` only (D-2.02)
- `tracer_ai/errors.py` — `TracerAIError` base; leaf module
- `tracer_ai/tracer/__init__.py` — namespace stub
- `tracer_ai/tracer/span.py` — OTel `gen_ai.*` (5) + `rag.*` (9) + `feedback.*` (1) constants block (Phase 4 TRCR-01 fills emission helpers)
- `tracer_ai/tracer/context.py` — Phase 4 TRCR-04 stub
- `tracer_ai/tracer/store.py` — Phase 4 TRCR-05 stub
- `tracer_ai/tracer/exporters/__init__.py` — namespace stub
- `tracer_ai/tracer/exporters/postgres.py` — Phase 4 TRCR-06 stub
- `tracer_ai/rag/__init__.py` — Phase 3 stub
- `tracer_ai/eval/__init__.py` — Phase 5 stub
- `tracer_ai/corpus/__init__.py` — Phase 3 stub
- `tracer_ai/api/__init__.py` — Wave 4 stub
- `tracer_ai/cli/__init__.py` — Phase 6 stub
- `tracer_ai/cli/__main__.py` — print-allowlisted entry (D-2.37)
- `tracer_ai/cli/partition.py` — `create_next_month_partition()` NotImplementedError stub (D-2.18; Phase 7 polish fills body)

**Dotfiles + tests (Task 3):**
- `.dockerignore` — Docker-build-context exclusions
- `.env.example` — 8-key env-var contract
- `tests/__init__.py` — package marker
- `tests/conftest.py` — `clean_env` fixture with `sys.modules.pop("tracer_ai.config", ...)` per W-6 fix
- `tests/test_imports.py` — 16-item smoke-import suite

### Modified (2 files)

- `.gitignore` — replaced 1-line `.claude/`-only file with full Python + node + env + IDE exclusion set; preserved `.claude/` exclusion (Rule 1 fix — see Deviations §)
- `docs/decisions/003-embedding-provider.md` — Mandatory follow-ups Voyage pricing checkbox ticked with verification date and source

### `pyproject.toml` Dep Table (per CLAUDE.md "Locked Stack Validation")

| Group   | Package                       | Version Range  | Purpose                                |
| ------- | ----------------------------- | -------------- | -------------------------------------- |
| runtime | fastapi                       | >=0.128,<0.129 | HTTP API server (Wave 4)               |
| runtime | pydantic                      | >=2.7,<3.0     | Data validation, schema, Settings base |
| runtime | pydantic-settings             | >=2.4,<3.0     | Env-var typed config (Wave 4 FLAT)     |
| runtime | sqlalchemy[asyncio]           | >=2.0,<2.1     | ORM + async sessions (Wave 3 + 4)      |
| runtime | asyncpg                       | >=0.29,<0.31   | Async Postgres driver                  |
| runtime | pgvector                      | >=0.3,<0.4     | Vector column type + distance queries  |
| runtime | alembic                       | >=1.13,<2.0    | DB migrations (Wave 3)                 |
| runtime | uvicorn[standard]             | >=0.30,<0.40   | ASGI server                            |
| runtime | anthropic                     | >=0.49,<1.0    | Claude SDK (Phase 3)                   |
| runtime | voyageai                      | >=0.3,<1.0     | Embeddings (Phase 3, free-tier ok)     |
| runtime | sentence-transformers         | >=3.0,<4.0     | Offline embedding fallback             |
| runtime | structlog                     | >=24.1,<25.0   | Structured JSON logging                |
| runtime | tiktoken                      | >=0.7,<1.0     | Token estimation pre-LLM-call          |
| runtime | httpx                         | >=0.27,<0.30   | HTTP client + FastAPI TestClient       |
| runtime | python-multipart              | >=0.0.9,<1.0   | Corpus admin upload endpoint           |
| dev     | ruff                          | >=0.7,<1.0     | Lint + format                          |
| dev     | mypy                          | >=1.11,<2.0    | --strict static type check             |
| dev     | pytest                        | >=8.3,<9.0     | Test runner                            |
| dev     | pytest-asyncio                | >=0.23,<1.0    | Async test support                     |
| dev     | pytest-testmon                | >=2.2,<3.0     | Changed-only test selection            |
| dev     | pre-commit                    | >=3.7,<5.0     | Git hooks framework (Wave 5)           |
| dev     | types-PyYAML                  | (no pin)       | Type stubs                             |

## Decisions Made

- **Voyage pricing closed via free tier** (Task 0): RESEARCH.md Topic 8 already verified 2026-05-04; auto-mode chain auto-approves. ADR 003 Mandatory follow-ups checkbox ticked with date + URL + reasoning inline.
- **Open Question Q1 → ship D-2.27 custom import-cycle guard** (Wave 5 carry): 60-line Python script reading docs/module-deps.md is the portfolio-narrative win over off-the-shelf import-linter; latter documented as future swap.
- **Open Question Q2 → Wave 4 adopts FLAT Settings shape** (Wave 4 carry): RESEARCH.md Topic 5 found FLAT is the pydantic-settings idiom for var counts ≤ 12; D-2.20's nested-namespace rationale revisited; saved nested grouping is a future revision.
- **Hatchling over setuptools**: minimal `[tool.hatch.build.targets.wheel].packages = ["tracer_ai"]` is cleaner than setup.py/cfg dance.
- **Empty `[tool.uv]` table reserved**: stable home for future uv-specific keys without churn.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Self-invalidating grep gate in `tracer_ai/tracer/span.py` docstring**
- **Found during:** Task 2 (tracer_ai package skeleton)
- **Issue:** The plan's verbatim docstring text in `tracer_ai/tracer/span.py` contained the literal substring `gen_ai.system` twice in explanatory prose (lines 10 and 12 after stripping `^#` comments). The plan's acceptance criterion `grep -v '^#' tracer_ai/tracer/span.py | grep -c 'gen_ai\.system'` must return 0; `grep -v '^#'` strips only `#`-prefixed comment lines, not docstring content. So the file as written by the plan failed its own acceptance gate (returned 2 instead of 0).
- **Fix:** Rewrote the relevant docstring sentences to refer to "the OTel GenAI legacy provider-identifier attribute (see the comment-line marker below)" rather than spelling the literal `gen_ai.system` twice. Preserved the "DO NOT use" intent and the threat T-2-01-04 mitigation traceability. The SOLE remaining `gen_ai.system` mention is on the explicit `# DEPRECATED: gen_ai.system  (kept commented-out for posterity; D-2.40)` marker line, which `grep -v '^#'` correctly strips.
- **Files modified:** `tracer_ai/tracer/span.py`
- **Verification:** `grep -v '^#' tracer_ai/tracer/span.py | grep -c 'gen_ai\.system'` returns 0; `grep -n 'gen_ai\.system' tracer_ai/tracer/span.py` returns exactly one hit on the commented-out DEPRECATED marker line. All 16 pytest items still pass; the runtime `not hasattr(span, "GEN_AI_SYSTEM")` invariant holds.
- **Committed in:** c5b1f78 (Task 2 commit)

**2. [Rule 2 - Missing Critical] Preserved `.claude/` exclusion in new `.gitignore`**
- **Found during:** Task 3 (dotfiles)
- **Issue:** The pre-existing `.gitignore` was a 1-line file containing only `.claude/` (Claude Code's local agent state directory). The plan's verbatim `.gitignore` content does NOT mention `.claude/`. Replacing the existing file with the plan's content as-is would expose the `.claude/` directory as untracked AND let future `git add .` mistakes accidentally commit Claude Code agent files (workflow caches, session state).
- **Fix:** Added `.claude/` line under a "Claude Code agent state" comment block in the new `.gitignore`. Project convention (CLAUDE.md context) treats `.claude/` as never-versioned tooling state.
- **Files modified:** `.gitignore`
- **Verification:** `grep -c '^\.claude/$' .gitignore` returns 1; `git status` no longer shows `.claude/` as untracked.
- **Committed in:** 3cbcb7a (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug fix in plan-supplied verbatim file body, 1 Rule 2 missing-critical exclusion preserved from prior tooling convention)
**Impact on plan:** Both auto-fixes were necessary for correctness (gate-passing) and for not breaking project tooling conventions. Neither expanded scope. The Rule 1 fix is a learning to feed back to the planner: when an acceptance gate uses a comment-stripping pre-filter, verbatim docstrings must also avoid the forbidden token, OR the gate must extend to strip docstrings too.

## Issues Encountered

- **`__pycache__/` directories created during `python -c "import tracer_ai..."` Task 2 verification.** The pre-existing 1-line `.gitignore` (only `.claude/`) didn't exclude them, so they showed up as untracked in `git status`. Resolution: explicitly staged only `.py` source files in Task 2 (per `<task_commit_protocol>` "NEVER `git add .`"); Task 3's new `.gitignore` adds `__pycache__/` so subsequent `git status` runs are clean.
- **System Python is 3.13.6, but `pyproject.toml` requires `>=3.12,<3.13`.** `uv` automatically downloaded and managed a CPython 3.12.4 toolchain (`Using CPython 3.12.4 interpreter`) — no manual intervention required. This is the standard `uv` behavior and validates the dep-manager choice (D-2.05).
- **`uv sync --all-extras` pulls torch 2.11 + transformers 4.57** (sentence-transformers offline-fallback dep tree). The 130-package install completed without errors.

## User Setup Required

None — Phase 2 Wave 1 is pure scaffolding. The operator will copy `.env.example` → `.env` and fill in `ANTHROPIC_API_KEY` + `VOYAGE_API_KEY` once Wave 2 ships Compose; no action needed before Wave 2 starts.

## Threat Flags

None — no new attack surface introduced beyond what was modeled in the plan's `<threat_model>`. Both T-2-01-01 (.env.example real-key leak) and T-2-01-04 (`gen_ai.system` reintroduction via copy-paste) have working acceptance grep gates wired into the plan-end `<verification>` and the gates pass cleanly.

## Wave 2 Readiness

- **`pyproject.toml` + `uv.lock`** are ready as Wave 2 `Dockerfile.backend` `deps` stage build context (`uv sync --frozen --no-install-project --all-extras`).
- **`.env.example`** is ready for Wave 2 Compose `env_file:` directive.
- **`tracer_ai/`** package import path is stable; Wave 4 can fill `tracer_ai/config.py` (FLAT Settings shape per Q2) and `tracer_ai/api/main.py` against this scaffold without touching existing files.
- **`.dockerignore`** keeps the Docker build context lean (excludes `.git/`, `.planning/`, `.claude/`, `docs/`).
- **`tests/test_imports.py`** is the Wave-0 INFRA-01 gate; it goes from 16 → 17+ items as Wave 4 adds `tracer_ai.config` to the parametrized list and `tests/test_config_failfast.py` lands.

## Self-Check: PASSED

**Files created — verified present:**
- `pyproject.toml`, `uv.lock` — present
- All 15 `tracer_ai/` `.py` files — present
- `.gitignore`, `.dockerignore`, `.env.example` — present
- `tests/__init__.py`, `tests/conftest.py`, `tests/test_imports.py` — present
- `docs/decisions/003-embedding-provider.md` — modified, checkbox ticked

**Commits — verified in `git log --oneline -5`:**
- `76742e6` — Task 0 ADR edit (FOUND)
- `706e46a` — Task 1 pyproject.toml + uv.lock (FOUND)
- `c5b1f78` — Task 2 tracer_ai package (FOUND)
- `3cbcb7a` — Task 3 dotfiles + tests (FOUND)

**Plan-end verification block — all 6 sections green:**
1. Repo scaffold sanity: PASS
2. Dep manifest sanity: 15 runtime + 6 dev deps (>= 14 + >= 6 thresholds met)
3. No locked anti-patterns: 0 `:latest`, 0 `class Config:`, 0 `print()` outside allowlist, 0 `gen_ai.system` non-comment hits
4. Smoke imports green: 16/16 pytest items pass in 0.03s
5. Env contract sanity: 8 env var lines present, 0 real `sk-ant-` keys
6. ADR 003 prereq: 2 pricing-verified mentions

---
*Phase: 02-skeleton-infrastructure*
*Plan: 01 (Wave 1)*
*Completed: 2026-05-04*
