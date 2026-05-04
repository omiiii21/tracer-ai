# Phase 2 Deferred Items

Items discovered during Phase 2 execution that are out of scope for the
current plan and were deferred to a later wave or phase.

## Wave 4 (Plan 02-04) discoveries

### D-1: ruff E501 in tests/test_imports.py:61

A docstring in `tests/test_imports.py:61` (Wave 1, commit 3cbcb7a) is 111
characters long, exceeding the project's `line-length = 100` ruff setting.

- **Scope:** Pre-existing Wave 1 artifact -- NOT caused by Wave 4 changes.
- **Disposition:** Defer to Wave 5 (which adds pre-commit hooks per Plan
  02-05) or to a docs(02-XX) followup; the line is a test docstring and
  has no runtime impact.
- **Trigger to fix:** When `pre-commit run --all-files` is wired in Wave 5,
  this fails CI; fix at that point by wrapping the docstring or adding a
  per-file ignore.
