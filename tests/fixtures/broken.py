"""Deliberate type error fixture (Wave 0 gap -- RESEARCH.md Validation Architecture).

Used to demonstrate that pre-commit blocks bad commits. NOT collected by
pytest (filename does not start with ``test_``); imported only by the
phase-end verification script (Task 4 Gate 2). The file lives under
tests/fixtures/ which is OUTSIDE [tool.mypy].files = ["tracer_ai"], so
the regular mypy --strict run does not trip on it.

Gate 2 copies this file into tracer_ai/_temp_broken.py so mypy --strict
tracer_ai/ MUST flag the type error -- proving the hook actually blocks
bad code rather than silently passing.
"""


# This function annotates int but returns str -- mypy --strict catches it.
def add(a: int, b: int) -> int:
    return "this is not an int"
