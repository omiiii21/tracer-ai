---
phase: 02-skeleton-infrastructure
plan: 05
subsystem: infra
tags: [vite, react18, typescript, tailwind-v3, shadcn, frontend-skeleton, docker-compose, hmr]

# Dependency graph
requires:
  - phase: 02-skeleton-infrastructure
    provides: |
      Wave 2: infra/Dockerfile.frontend (multi-stage base/deps/dev/build/prod);
      frontend/.env.example (VITE_API_BASE_URL=http://localhost:8000);
      frontend/package.json placeholder. Wave 4: api service wired and
      health-checked at localhost:8000/healthz.
provides:
  - Pinned Vite 5 + React 18.3.1 + TypeScript ~5.5 + Tailwind v3.4 manifest
  - shadcn/ui Zinc-base primitives (Card, Button) at frontend/src/components/ui/
  - Hello-route Card at / showing "Hello tracer-ai" (D-2.29)
  - @/* path alias mirrored across tsconfig.json + vite.config.ts
  - Compose web service serving Vite dev on :5173 with HMR over Docker bind-mount
  - End-to-end 4-service boot from fresh checkout — INFRA-02 closed
affects: [03-rag-corpus, 03-chat-ui, 05-dashboard]

# Tech tracking
tech-stack:
  added:
    - "react 18.3.1, react-dom 18.3.1"
    - "typescript ~5.5"
    - "vite ^5.4 + @vitejs/plugin-react ^4.3"
    - "tailwindcss ^3.4 + autoprefixer + postcss + tailwindcss-animate"
    - "@tremor/react ^3.18 (installed; first use Phase 5 dashboard)"
    - "@tanstack/react-query ^5 (installed; first use Phase 3 chat)"
    - "react-router-dom ^6.27 (installed; first use Phase 3 routes)"
    - "clsx ^2.1 + tailwind-merge ^2.5 + lucide-react ^0.460"
  patterns:
    - "shadcn primitives owned in-tree (frontend/src/components/ui/) — no shadcn CLI runtime dependency"
    - "cn() helper at @/lib/utils.ts (twMerge + clsx) — shadcn canonical"
    - "Path alias @/* declared in BOTH tsconfig.json paths AND vite.config.ts resolve.alias"
    - "Vite watch.usePolling=true + compose CHOKIDAR_USEPOLLING=true (belt-and-suspenders for Docker bind-mount HMR)"
    - "Anonymous /app/node_modules volume in compose (Pitfall 5 mitigation)"

key-files:
  created:
    - frontend/tsconfig.json
    - frontend/tsconfig.node.json
    - frontend/vite.config.ts
    - frontend/tailwind.config.js
    - frontend/postcss.config.js
    - frontend/components.json
    - frontend/package-lock.json
    - frontend/index.html
    - frontend/src/main.tsx
    - frontend/src/App.tsx
    - frontend/src/index.css
    - frontend/src/lib/utils.ts
    - frontend/src/components/ui/card.tsx
    - frontend/src/components/ui/button.tsx
  modified:
    - frontend/package.json (replaced Wave 2 stub with pinned full set)
    - infra/docker-compose.yml (web service: drop sleep placeholder, extend bind-mounts)
    - infra/Dockerfile.frontend (Rule 1 chown fix + npm ci preference)
    - .dockerignore (Rule 3 expand node_modules patterns)

key-decisions:
  - "shadcn baseColor=zinc per Open Question Q4 (slate dropped from current shadcn CLI palette list)"
  - "Hand-author shadcn primitives instead of running `npx shadcn init` — deterministic for automated pipeline; avoids the 2026 React-19/Tailwind-v4 default trap"
  - "Pin React 18 + Tailwind v3 in package.json BEFORE first npm install (Pitfall 5 / RESEARCH.md Topic 7)"
  - "Generate package-lock.json via `docker run node:20-alpine npm install` to avoid host-arch (Windows) binary contamination of the Linux container"
  - "Button shipped without @radix-ui/react-slot asChild support (out of scope for Phase 2 hello route; add when Phase 3+ needs it)"
  - "Compose bind-mount the seven config files individually with :ro instead of mounting the whole frontend/ directory — matches threat T-2-05-08 mitigation"

patterns-established:
  - "Docker-resident dependency installation: when generating Linux node_modules from a Windows host, always `docker run -v $PWD:/app node:20-alpine npm install` (never host npm install)"
  - "/app/ ownership: Dockerfile.frontend deps stage chowns /app to node:node BEFORE copying source so the running USER node can write Vite's vite.config.ts.timestamp-*.mjs sibling files"
  - "Frontend file routing: any `/app/*.config.*` or tsconfig file gets its own bind-mount entry in compose web service so editing on host triggers HMR"

requirements-completed: [INFRA-01, INFRA-02]

# Metrics
duration: ~25 min (active executor time; Docker builds dominate)
completed: 2026-05-04
---

# Phase 2 Plan 05: Frontend Skeleton Summary

**Vite 5 + React 18.3.1 + Tailwind v3.4 + shadcn/ui Zinc-base hello-route Card live at http://localhost:5173/, with end-to-end 4-service Compose boot closing INFRA-02.**

## Performance

- **Duration:** ~25 min active execution (most wall time absorbed by `docker compose build` for `web` and `api` images on cold cache)
- **Started:** 2026-05-04T18:53:00Z
- **Completed:** 2026-05-04T19:18:00Z
- **Tasks:** 3 / 3
- **Files modified:** 18 (15 new + 3 modified)

## Accomplishments

- Pinned manifest (`frontend/package.json` + lockfile) blocks the 2026 React-19 / Tailwind-v4 silent-upgrade trap; negative grep gates baked into the verification step.
- shadcn/ui Zinc-base primitives (Card, Button) hand-authored in-tree under `frontend/src/components/ui/` — no shadcn CLI runtime dependency, no Tailwind v4 / React 19 contamination risk.
- `@/*` path alias declared in BOTH `tsconfig.json` `compilerOptions.paths` AND `vite.config.ts` `resolve.alias` — `tsc --noEmit -p tsconfig.json` exits 0 across the alias boundary.
- `infra/docker-compose.yml` `web` service drops the Wave-2 `["sleep", "infinity"]` placeholder; Vite dev server runs on `:5173` via the Dockerfile dev-stage CMD. Bind-mounts cover all seven config files individually (matches T-2-05-08 mitigation).
- Live verified end-to-end: from `docker compose down -v` → `docker compose up -d --build db migrate api web`, all 4 services come green and `curl http://localhost:5173/` returns 200 + `<div id="root"></div>` HTML shell.

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin package.json + tsconfig + vite/tailwind/postcss/shadcn config** — `be4f38f` (feat)
2. **Task 2: Author Vite entry + hello-route Card with shadcn primitives** — `368f59d` (feat)
3. **Task 3: Wire web service in compose; close INFRA-02 4-service boot** — `576426c` (feat, includes Rule 1 + Rule 3 fixes)

_Note: Wave 4's `30f153a` (Plan 02-04 SUMMARY commit) is the prior baseline._

## Frontend Dependency Manifest (every dep with pinned version)

| Dep | Pinned Version | Phase Use |
|---|---|---|
| `react` | `^18.3.1` | Always |
| `react-dom` | `^18.3.1` | Always |
| `typescript` | `~5.5.0` | tsc + Wave 5 pre-commit hook |
| `vite` | `^5.4.0` | Dev server + build |
| `@vitejs/plugin-react` | `^4.3.0` | JSX + Fast Refresh |
| `tailwindcss` | `^3.4.0` | Styling (NOT v4) |
| `tailwindcss-animate` | `^1.0.7` | shadcn animations |
| `autoprefixer` | `^10.4.0` | PostCSS chain |
| `postcss` | `^8.4.0` | Tailwind pipeline |
| `@tremor/react` | `^3.18.0` | Phase 5 dashboard charts |
| `@tanstack/react-query` | `^5.0.0` | Phase 3 chat fetch state |
| `react-router-dom` | `^6.27.0` | Phase 3 multi-route |
| `clsx` | `^2.1.0` | shadcn cn() input |
| `tailwind-merge` | `^2.5.0` | shadcn cn() output |
| `lucide-react` | `^0.460.0` | shadcn icon library |
| `@types/react` | `^18.3.0` | Type defs |
| `@types/react-dom` | `^18.3.0` | Type defs |
| `@types/node` | `^20.16.0` | path/fileURLToPath in vite.config.ts |

## Open Question Resolution

- **Q4 — shadcn base color:** **Zinc** (slate dropped from current shadcn CLI palette list). `frontend/components.json` `"baseColor": "zinc"`; CSS variables in `frontend/src/index.css` derived from the canonical shadcn Zinc light/dark palette.

## Pin Enforcement Gates

Negative grep gates baked into the plan verification (and re-runnable from CLI):

```bash
grep -E '"react": "\^19' frontend/package.json | wc -l           # → 0
grep -E '"tailwindcss": "\^4' frontend/package.json | wc -l      # → 0
grep -E '"react": "\^18\.3\.1"' frontend/package.json | wc -l    # → 1
grep -E '"tailwindcss": "\^3\.4' frontend/package.json | wc -l   # → 1
```

These gates protect against `npm update` and any future re-execution of `npm create vite@latest` (which defaults to React 19 + Tailwind v4 in 2026).

## TypeScript Compile Cleanliness

```bash
$ docker run --rm -v "$(pwd)/frontend":/app -w /app node:20.18.0-alpine \
    sh -c "npx tsc --noEmit -p tsconfig.json"
# exit 0
```

Confirmed across the `@/*` alias boundary. Wave 5's pre-commit `tsc-frontend` hook will have a real lint target.

## End-to-End Stack Boot (INFRA-02 closure)

```bash
$ cd infra
$ docker compose down -v --remove-orphans
$ docker compose up -d --build db migrate api web
# All services come green:
#   infra-db-1       Up (healthy)
#   infra-migrate-1  Exited (0)
#   infra-api-1      Up (healthy) — 0.0.0.0:8000
#   infra-web-1      Up — 0.0.0.0:5173
$ curl -s http://localhost:8000/healthz
{"status":"ok","version":"0.1.0","db":"ok"}
$ curl -s http://localhost:5173/ | grep -c '<div id="root"></div>'
1
```

INFRA-02 four-service boot success criterion satisfied.

## Decisions Made

- **shadcn primitives hand-authored** (not `npx shadcn init`) — deterministic for automated pipeline, immune to 2026 React-19/Tailwind-v4 silent-default trap.
- **Generate `package-lock.json` via Docker** (`docker run node:20-alpine npm install`) — avoids host (Windows) binary architecture contamination of the Linux node_modules tree.
- **Compose bind-mounts every config file individually** (not the whole `frontend/` directory) — matches T-2-05-08 mitigation; restricts Vite's filesystem visibility.
- **No `command:` override in compose web service** — let `Dockerfile.frontend` dev-stage `CMD` be the single source of truth for the dev-server invocation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Strip `.tsx` extension from `App` import in `main.tsx`**

- **Found during:** Task 2 (tsc verify)
- **Issue:** `import App from "./App.tsx"` triggered `TS5097: An import path can only end with a '.tsx' extension when 'allowImportingTsExtensions' is enabled.` Plan's tsconfig sets `allowImportingTsExtensions: false` (correct for Vite + bundler resolution).
- **Fix:** Changed to `import App from "./App";` — bundler resolution finds `App.tsx` automatically.
- **Files modified:** `frontend/src/main.tsx`
- **Verification:** `tsc --noEmit -p tsconfig.json` → exit 0 (was failing with TS5097)
- **Committed in:** `368f59d` (Task 2 commit, pre-commit fix)

**2. [Rule 3 - Blocking] Extend `.dockerignore` to defeat Windows symlinks under `frontend/node_modules/.bin/`**

- **Found during:** Task 3 (initial `docker compose up --build` attempt)
- **Issue:** BuildKit failed with `invalid file request frontend/node_modules/.bin/autoprefixer` when COPYing the build context. The host `frontend/node_modules/` (created by the Task-1 `docker run npm install` to seed `package-lock.json`) contained Windows-incompatible npm-bin symlinks that BuildKit could not traverse, even with `node_modules/` already in `.dockerignore`.
- **Fix:** Added explicit `**/node_modules/`, `**/node_modules`, and `frontend/node_modules` patterns to `.dockerignore` (belt-and-suspenders, since the simple `node_modules/` pattern should have caught the path); additionally deleted the host `frontend/node_modules/` directory entirely (no longer needed once `package-lock.json` was generated — Docker installs into the anonymous `/app/node_modules` volume at container build time).
- **Files modified:** `.dockerignore`
- **Verification:** `docker compose up -d --build web` succeeded; web container built and started.
- **Committed in:** `576426c` (Task 3 commit)

**3. [Rule 1 - Bug] `chown /app` to `node:node` in `Dockerfile.frontend` deps stage**

- **Found during:** Task 3 (web container started but Vite crashed)
- **Issue:** `Error: EACCES: permission denied, open '/app/vite.config.ts.timestamp-1777902389447-d9346bc7dc5d7.mjs'`. The Wave 2 Dockerfile did `COPY frontend ./` as root then `USER node`, leaving `/app/` and its contents owned by `root:root` mode 755. Vite, when bundling `vite.config.ts`, writes a sibling `*.timestamp-*.mjs` temp file in the same directory — and the running `node` user (uid 1000) lacked write permission on `/app/`.
- **Fix:** In `infra/Dockerfile.frontend` deps stage, `RUN chown -R node:node /app && USER node` BEFORE the `COPY --chown=node:node frontend/package.json ...`; same pattern in dev and build stages with `COPY --chown=node:node frontend ./`. Also added `frontend/package-lock.json*` to the deps-stage COPY so `npm ci` (now preferred over `npm install` since Plan 02-05 ships the lockfile) works deterministically.
- **Files modified:** `infra/Dockerfile.frontend`
- **Verification:** Vite dev server now starts cleanly inside the container; `curl http://localhost:5173/` returns 200 + Vite-injected HMR client + `<div id="root">`.
- **Committed in:** `576426c` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (1 typescript bug, 1 build-context blocker, 1 container-permissions bug)
**Impact on plan:** All three deviations were necessary for INFRA-02 closure. None changed the plan's surface area or scope. Files outside the plan's `files_modified` list (`infra/Dockerfile.frontend`, `.dockerignore`) were touched only as Rule 1 / Rule 3 fixes; both were Wave-2-era artifacts where Phase 2 first exercised them with a real Vite source tree.

## Issues Encountered

- Windows host quirks: MSYS2 path-conversion mangling required `MSYS_NO_PATHCONV=1` for the `docker run -v` invocation that generated `package-lock.json`. Documented in the SUMMARY but not propagated to any committed file (developers on Linux/macOS hosts won't hit this).
- `jq` unavailable on Windows Git-Bash by default; the plan's verify gate uses `jq -e '.status == "ok"'` which silently fails. Confirmed manually that the JSON body contains `"status":"ok"` and `"db":"ok"`. Wave 5's CI hooks (Linux) will have `jq` available.

## Known Stubs

| Stub | File | Line | Reason / Resolved by |
|---|---|---|---|
| `console.log("phase 2 alive")` in Button onClick | `frontend/src/App.tsx` | 17 | Phase 2 hello-route stub; T-2-05-07 acknowledges. Phase 3 chat wireframes replace with real chat-submit handler. |
| Empty `Card` route at `/` (no router) | `frontend/src/App.tsx` | (whole file) | Phase 2 ships a single hello route. Phase 3 introduces `react-router-dom` `<BrowserRouter>` wrapping `App` with `/chat`, `/dashboard`, `/admin` routes. |

## Threat Flags

None. Plan 02-05 introduced no new trust-boundary surface beyond what `<threat_model>` already enumerated; the three Rule-1/Rule-3 deviations all tightened (rather than expanded) attack surface (chown to non-root user; restrict bind-mount scope).

## User Setup Required

None — no external service configuration required. (The Anthropic / Voyage API keys for Phase 3+ are already in `.env.example`; operator supplies them when Phase 3 plans land.)

## Next Phase Readiness

- **Wave 5 pre-commit hooks**: `tsc-frontend` hook has a real lint target (`frontend/tsconfig.json` + 7 source files).
- **Phase 3 chat UI**: All Phase-3 deps already installed and pinned (`@tanstack/react-query`, `react-router-dom`); shadcn `Card` + `Button` primitives ready to compose; `@/*` path alias confirmed working; `VITE_API_BASE_URL` env-var contract enforced in `frontend/.env.example`.
- **Phase 5 dashboard**: `@tremor/react` already installed; Tremor is Recharts-backed and Tailwind v3-native, both of which Plan 02-05 pinned.

## Self-Check: PASSED

Verification of SUMMARY claims (all run after final commit):

- File existence (15 created + 3 modified) — all 18 paths return `FOUND` via `test -f`.
- Commits exist: `be4f38f`, `368f59d`, `576426c` — all return `FOUND` via `git log --oneline | grep`.
- Pin gates: `react@^18.3.1`=1, `tailwindcss@^3.4`=1, `react@^19`=0, `tailwindcss@^4`=0, `baseColor=zinc`=1, `usePolling: true`=1, `@/*`=1.
- tsc clean: `docker run node:20-alpine npx tsc --noEmit -p tsconfig.json` → exit 0.
- Live HTTP: `curl http://localhost:5173/` → 200 + `<div id="root"></div>`; `curl http://localhost:8000/healthz` → 200 + `{"status":"ok","db":"ok"}`.

---
*Phase: 02-skeleton-infrastructure*
*Plan: 05*
*Completed: 2026-05-04*
