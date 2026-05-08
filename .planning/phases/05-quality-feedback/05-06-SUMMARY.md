---
phase: 05-quality-feedback
plan: 06
subsystem: cli
tags: [calibrate, argparse, best-f1-sweep, prompt-version-mismatch, pitfall-6, pitfall-10, eval-06, d-5-11, d-5-12]

# Dependency graph
requires:
  - phase: 05-quality-feedback
    plan: 01
    provides: "PROMPT_VERSION constant + EvalScores schema + AnthropicJudge.score (the calibration set is labeled against the prompt version produced here)"
  - phase: 04-tracer-trace-explorer
    plan: 01
    provides: "traces.faithfulness denormalized column (run_label reads recent traces with non-NULL faithfulness)"
provides:
  - "tracer_ai/eval/calibrate.py — run_threshold_sweep + render_sweep_report + run_label + helpers (confusion_at, precision_recall_f1, _iter_thresholds)"
  - "tracer-ai calibrate label --n N --strategy {recent|random|stratified} --out <path> CLI subcommand"
  - "tracer-ai calibrate threshold --in <path> CLI subcommand (best-F1 sweep + suggested env value)"
  - "Pitfall 6 mismatch refusal: when YAML prompt_version != current PROMPT_VERSION, run_threshold_sweep raises ValueError naming both stale and current versions + 'Re-run' instruction"
  - "n<=0 early-return in _dispatch_calibrate BEFORE asyncio.run + asyncpg pool (no DATABASE_URL required for the CLI8 smoke path)"
  - "pyyaml>=6.0,<7.0 added to runtime dependencies"
  - "docs/eval/.gitkeep — calibration_set.yaml is operator-produced after `calibrate label` against seeded traces; not committed up-front"
affects: [05-07 frontend (no direct dep), 06 regression-set CLI (will reuse the labeling-loop pattern; calibrate threshold report shape may inform regression-set quality reports)]

# Tech tracking
tech-stack:
  added: ["pyyaml>=6.0,<7.0 (runtime); types-PyYAML already in dev"]
  patterns:
    - "argparse subparser group nesting: top-level `command` subparsers (ingest, calibrate); calibrate has its own `cal_command` subparsers (label, threshold). Pitfall 10 — argparse not Click; matches existing tracer_ai/cli/__main__.py pattern."
    - "Best-F1 sweep over [0.30, 0.90] step 0.05 = 13 thresholds; integer-loop arithmetic + 2-decimal rounding to avoid FP drift (D-5.12)."
    - "Pitfall 6 mismatch refusal via ValueError: error message contains BOTH the stale prompt_version from YAML AND the current PROMPT_VERSION constant + 'Re-run `tracer-ai calibrate label --n 30`' instruction so the operator can self-recover."
    - "Print allowlist invariant (D-2.37): render_sweep_report returns a string; run_label writes interactive prompts to sys.stderr; only cli/__main__.py emits print()."
    - "Short-circuit BEFORE asyncpg pool when n<=0: enables CI smoke-test of the CLI surface without a live DATABASE_URL (CLI8 acceptance)."

key-files:
  created:
    - "tracer_ai/eval/calibrate.py — calibration core (run_threshold_sweep + render_sweep_report + run_label + confusion_at + precision_recall_f1)"
    - "docs/eval/.gitkeep — operator-produced calibration_set.yaml goes here"
    - "tests/test_calibrate_threshold.py — 11 tests TH1-TH9 + 2 helper tests covering sweep correctness + Pitfall-6 refusal"
    - "tests/test_calibrate_cli.py — 8 subprocess integration tests CLI1-CLI8 covering the full argparse + dispatch surface"
  modified:
    - "tracer_ai/eval/__init__.py — additively export CalibrationEntry / run_label / run_threshold_sweep / render_sweep_report"
    - "tracer_ai/cli/__main__.py — add calibrate subparser group + _dispatch_calibrate routing"
    - "pyproject.toml — pyyaml>=6.0,<7.0 added to runtime dependencies; uv.lock updated"
---

# Plan 05-06 — `tracer-ai calibrate {label,threshold}` CLI

## What was built

Two CLI subcommands that close out EVAL-06 (operator-driven threshold calibration):

1. **`tracer-ai calibrate label --n N --strategy {recent|random|stratified} --out <path>`** — Walks N most-recent / random / stratified traces (each already judged by Plan 05-04's dispatcher), prompts the operator for ground-truth labels (`[g]ood / [b]ad / [s]kip`), and appends entries to a YAML file. The label loop is read-only against existing `traces.faithfulness` rows; it does NOT invoke the judge.

2. **`tracer-ai calibrate threshold --in <path>`** — Reads the YAML, runs a best-F1 sweep over `[0.30, 0.90]` step 0.05 (13 thresholds), and prints a formatted sweep table + suggested `BAD_ANSWER_FAITHFULNESS_THRESHOLD` env-var value (D-5.12). When the YAML's `prompt_version` doesn't match the runtime `PROMPT_VERSION`, the command refuses with exit 2 and a "Re-run" instruction (Pitfall 6 mitigation).

## Tasks completed

| # | Task | Commit | What landed |
|---|------|--------|-------------|
| 1 | Calibrate threshold-sweep core + helpers + pyyaml dep | `6c7e188` | `tracer_ai/eval/calibrate.py` (run_threshold_sweep + render_sweep_report + run_label + confusion_at + precision_recall_f1); 11 tests TH1-TH9 + 2 helper tests; `eval/__init__.py` additive exports; `pyyaml>=6.0,<7.0` runtime dep; `docs/eval/.gitkeep` |
| 2 | CLI subparser wiring + 8 subprocess CLI tests | `c943e1a` | `tracer_ai/cli/__main__.py` (calibrate subparser + `_dispatch_calibrate` routing + n<=0 short-circuit + Pitfall-6 ValueError → exit 2); `tests/test_calibrate_cli.py` (CLI1-CLI8 covering --help, threshold success, FileNotFoundError, mismatch refusal, missing-subcommand argparse errors, no-DB CLI8 smoke) |

## Verification

- **Unit:** `pytest tests/test_calibrate_threshold.py tests/test_calibrate_cli.py` — 19/19 pass (8 CLI + 11 threshold-sweep).
- **Full unit suite:** 278 passed, 1 skipped — no regressions vs. baseline.
- **mypy --strict** on `tracer_ai/eval/calibrate.py` and `tracer_ai/cli/__main__.py`: 0 errors.
- **ruff check**: clean.
- **Pitfall 6 acceptance:** TH6 (unit) + CLI5 (subprocess) both confirm the YAML-vs-PROMPT_VERSION mismatch raises ValueError → exit 2 with both versions in the message + "Re-run" instruction.
- **CLI8 acceptance:** `tracer-ai calibrate label --n 0` exits 0 with stdout "Nothing to label" — confirmed via subprocess WITHOUT DATABASE_URL set in the child env (the n<=0 guard short-circuits before `asyncio.run(run_label(...))`).
- **D-2.37 print-allowlist:** `grep -E "^[^#]*print\(" tracer_ai/eval/calibrate.py | grep -v "^\s*#"` returns 0 lines; `tracer_ai/cli/__main__.py` is the only file emitting `print()`.

## Decisions worth recording

- **Pitfall 6 mismatch refusal is exit 2 (not 1)**: matches argparse-error convention. Operator sees `calibrate threshold failed: <reason>` on stderr and a non-zero exit; CI gates can trip on this. The error message names BOTH versions + "Re-run `tracer-ai calibrate label --n 30`" so the operator can self-recover without spelunking the codebase.
- **`_dispatch_calibrate` lives in `cli/__main__.py`, NOT in `eval/`**: keeps the print() allowlist tight (D-2.37). `calibrate.py` returns formatted strings via `render_sweep_report`; the CLI is the only side that prints.
- **n<=0 short-circuit is a feature, not an edge case**: it's the CI-friendly surface that verifies the CLI dispatch path without needing a live DATABASE_URL. The guard is documented inline so future maintainers don't "helpfully" remove it.
- **argparse, not Click (Pitfall 10)**: the existing `tracer_ai/cli/__main__.py` uses argparse and its subparser pattern. Adding a Click dependency just for `calibrate` would split the CLI surface across two libraries; argparse handles nested subcommands (`command` → `cal_command`) cleanly enough.
- **Best-F1 sweep range [0.30, 0.90] step 0.05 = 13 thresholds locked (D-5.12)**: covers the realistic operating range; below 0.30 the judge is rarely confident enough to flag; above 0.90 nearly every imperfect answer trips. Future tightening goes here, not the route handler.

## Deviations from plan

None of substance. Two minor surface differences:

- **`_dispatch_calibrate` extracted as a helper function** rather than inlining the dispatch in `main()`: keeps `main()` short and matches the existing local-import-keeps-cold-path-fast pattern (e.g., `from tracer_ai.eval.calibrate import ...` is now scoped to the function).
- **`FileNotFoundError` is caught alongside `ValueError`** in the threshold dispatch branch. The plan implies only `ValueError`, but `run_threshold_sweep` raises `FileNotFoundError` when `--in <missing>` (CLI4 acceptance). Catching both as "config-shaped failure" → exit 2 keeps the contract honest.

## Hand-off to Wave 3 (plan 05-07)

No direct dependency. Plan 05-07 (frontend) consumes `GET /admin/eval-config` (Plan 05-03) for the threshold reading and does not need to invoke the calibration CLI. Calibration is an offline operator workflow.

For Phase 6 (Eval CLI + Regression Set):
- The label-loop pattern (`run_label`) and the YAML schema can be reused for the regression-set authoring flow.
- `confusion_at`, `precision_recall_f1`, `_iter_thresholds` are the threshold-sweep primitives; the regression set's pass-rate report can reuse them or compose them differently.
- The print() allowlist convention (CLI prints; logic returns strings) should be preserved across any new subcommands added in Phase 6.
