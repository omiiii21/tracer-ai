"""Anti-pattern enforcement tests (D-2.36..40 + ADR 005).

These tests run as a fast pre-commit hook (entry: pytest tests/test_anti_patterns.py)
AND as part of the regular pytest suite. They catch the locked anti-patterns
before they propagate.

Patterns enforced:
  - D-2.36: no ``:latest`` Docker image tags in infra/, frontend/package.json, pyproject.toml
  - D-2.37: no raw print() in tracer_ai/ except cli/__main__.py allowlist
  - D-2.38: no SDK imports outside the dedicated adapter file
            (anthropic in rag/llm.py + eval/llm_judge.py; voyageai in rag/embedder.py)
  - D-2.39: no Pydantic v1 ``class Config:`` idiom (use ConfigDict on model_config)
  - D-2.40: ``gen_ai.system`` constant only on the explicit DEPRECATED comment line
  - ADR 005: no ``opentelemetry-sdk`` in pyproject.toml runtime [project.dependencies]
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Sentinel substring built up from fragments so this test file does NOT itself
# match the grep gates it enforces. Without this, ``test_no_latest_image_tag_in_infra``
# would scan for the literal ":" + "latest" string and the test file would
# show up as a hit if it ever expanded its scan path.
_LATEST_TAG = ":" + "latest"


def _git_grep(pattern: str, paths: list[str]) -> list[str]:
    """``git grep -nE PATTERN PATHS`` -- list of matching lines (empty if none)."""
    result = subprocess.run(
        ["git", "grep", "-nE", pattern, "--", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 1:  # no matches
        return []
    if result.returncode != 0:
        raise RuntimeError(f"git grep failed: {result.stderr}")
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def test_no_latest_image_tag_in_infra() -> None:
    """D-2.36: no ``:latest`` tag in Dockerfiles, compose, or package manifests."""
    matches = _git_grep(
        re.escape(_LATEST_TAG),
        ["infra/", "frontend/package.json", "pyproject.toml"],
    )
    # Allow ``:latest`` in comments only; filter out lines beginning with #
    real = [m for m in matches if not re.match(r"^[^:]+:[^:]+:\s*#", m)]
    assert not real, f"Forbidden {_LATEST_TAG} tag found: {real}"


def test_no_print_in_tracer_ai_except_cli_main() -> None:
    """D-2.37: no raw print(...) in tracer_ai/ except cli/__main__.py allowlist."""
    matches = _git_grep(r"^\s*print\(", ["tracer_ai/"])
    # Allow tracer_ai/cli/__main__.py only (D-2.37 explicit allowlist)
    real = [m for m in matches if not m.startswith("tracer_ai/cli/__main__.py")]
    assert not real, f"Forbidden print() in tracer_ai/: {real}"


def test_no_pydantic_v1_class_config() -> None:
    """D-2.39: no ``class Config:`` v1 idiom anywhere in tracer_ai/."""
    matches = _git_grep(r"^\s*class Config\s*:", ["tracer_ai/"])
    assert not matches, f"Pydantic v1 class Config: found (use ConfigDict): {matches}"


def test_no_gen_ai_system_outside_deprecated_comment() -> None:
    """D-2.40: gen_ai.system constant only on the DEPRECATED comment-out line."""
    matches = _git_grep(r"gen_ai\.system", ["tracer_ai/"])
    # Allow only lines containing the literal "DEPRECATED" (case-sensitive)
    real = [m for m in matches if "DEPRECATED" not in m]
    assert not real, f"gen_ai.system constant found outside DEPRECATED comment: {real}"


def test_no_anthropic_sdk_outside_adapter() -> None:
    """D-2.38: ``from anthropic`` only in tracer_ai/rag/llm.py and tracer_ai/eval/llm_judge.py.

    Phase 2 has neither file yet -- assert no violators today.
    """
    matches = _git_grep(r"^\s*from anthropic\b", ["tracer_ai/"])
    allowed = ("tracer_ai/rag/llm.py", "tracer_ai/eval/llm_judge.py")
    real = [m for m in matches if not any(m.startswith(a) for a in allowed)]
    assert not real, f"from anthropic outside allowed adapters: {real}"


def test_no_voyageai_sdk_outside_adapter() -> None:
    """D-2.38: ``from voyageai`` only allowed in tracer_ai/rag/embedder.py.

    Phase 2 has no Phase 3 adapter yet -- assert no violators today.
    """
    matches = _git_grep(r"^\s*from voyageai\b", ["tracer_ai/"])
    allowed = ("tracer_ai/rag/embedder.py",)
    real = [m for m in matches if not any(m.startswith(a) for a in allowed)]
    assert not real, f"from voyageai outside allowed adapters: {real}"


def test_no_opentelemetry_sdk_runtime_dep() -> None:
    """ADR 005 narrative: no ``opentelemetry-sdk`` in pyproject.toml runtime deps."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Crude but effective: scan the [project.dependencies] table
    deps_block_match = re.search(
        r"^dependencies = \[(.+?)\]",
        pyproject,
        re.DOTALL | re.MULTILINE,
    )
    assert deps_block_match, "pyproject.toml missing [project.dependencies]"
    deps_block = deps_block_match.group(1)
    assert (
        "opentelemetry-sdk" not in deps_block
    ), "opentelemetry-sdk in runtime deps -- ADR 005 forbids; constants only"
