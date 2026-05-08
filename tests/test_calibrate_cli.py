"""Phase 5 Plan 05-06 CLI integration tests for `tracer-ai calibrate`.

Tests CLI1-CLI8 cover:
- CLI1: `calibrate --help` exits 0; lists label and threshold subcommands
- CLI2: `calibrate threshold --help` exits 0; lists --in
- CLI3: `calibrate threshold --in <good-yaml>` exits 0; report contains
        threshold/P/R/F1/Suggested
- CLI4: `calibrate threshold --in <missing>` exits 2; stderr names "not found"
- CLI5: `calibrate threshold --in <prompt-mismatch>` exits 2; stderr "Re-run"
        (Pitfall 6 mitigation acceptance via the CLI surface)
- CLI6: `calibrate` (no subcommand) exits 2 (argparse "required" error)
- CLI7: `calibrate` with no sub-subcommand exits 2
- CLI8: `calibrate label --n 0 --strategy recent` exits 0 with "Nothing to
        label" -- verifies the n<=0 short-circuit precedes asyncpg pool, so
        the CLI runs without DATABASE_URL (CI-friendly without DB secret).

All tests subprocess.run([sys.executable, "-m", "tracer_ai.cli", ...]) to
exercise the full argparse + dispatch path. Required env vars are seeded
into the child process env so module-top Settings() doesn't ValidationError.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Pre-set required env vars BEFORE importing tracer_ai.* (so we can derive
# PROMPT_VERSION at fixture-creation time without ValidationError).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-x")
os.environ.setdefault("VOYAGE_API_KEY", "voy-x")

from tracer_ai.eval.llm_judge import PROMPT_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent


def _child_env() -> dict[str, str]:
    """Build a child-process env that satisfies Settings() validation.

    Mirrors what the parent test process has but is explicit so subprocess
    invocations don't depend on ambient env state.
    """
    return {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/testdb",
        "ANTHROPIC_API_KEY": "sk-ant-x",
        "VOYAGE_API_KEY": "voy-x",
    }


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m tracer_ai.cli ARGS` and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "tracer_ai.cli", *args],
        cwd=REPO_ROOT,
        env=_child_env(),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def good_yaml(tmp_path: Path) -> Path:
    """Build a 6-entry calibration YAML with the current PROMPT_VERSION."""
    path = tmp_path / "calibration_set.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "created_at": "2026-05-08T00:00:00Z",
                "calibration_strategy": "recent",
                "prompt_version": PROMPT_VERSION,
                "judge_model": "claude-haiku-4-5-20251001",
                "entries": [
                    {
                        "trace_id": "00000000-0000-0000-0000-000000000001",
                        "label": "bad",
                        "notes": "",
                        "faithfulness": 0.3,
                        "relevance": 0.4,
                        "query_excerpt": "x",
                    },
                    {
                        "trace_id": "00000000-0000-0000-0000-000000000002",
                        "label": "bad",
                        "notes": "",
                        "faithfulness": 0.45,
                        "relevance": 0.5,
                        "query_excerpt": "y",
                    },
                    {
                        "trace_id": "00000000-0000-0000-0000-000000000003",
                        "label": "good",
                        "notes": "",
                        "faithfulness": 0.7,
                        "relevance": 0.8,
                        "query_excerpt": "a",
                    },
                    {
                        "trace_id": "00000000-0000-0000-0000-000000000004",
                        "label": "good",
                        "notes": "",
                        "faithfulness": 0.85,
                        "relevance": 0.9,
                        "query_excerpt": "b",
                    },
                    {
                        "trace_id": "00000000-0000-0000-0000-000000000005",
                        "label": "good",
                        "notes": "",
                        "faithfulness": 0.95,
                        "relevance": 0.95,
                        "query_excerpt": "c",
                    },
                    {
                        "trace_id": "00000000-0000-0000-0000-000000000006",
                        "label": "skip",
                        "notes": "",
                        "faithfulness": 0.5,
                        "relevance": 0.5,
                        "query_excerpt": "d",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def stale_yaml(tmp_path: Path) -> Path:
    """Build a YAML with a prompt_version that mismatches current PROMPT_VERSION."""
    path = tmp_path / "calibration_set.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "created_at": "2026-05-08T00:00:00Z",
                "calibration_strategy": "recent",
                "prompt_version": "v0.old-prompts",  # stale
                "judge_model": "claude-haiku-4-5-20251001",
                "entries": [
                    {
                        "trace_id": "00000000-0000-0000-0000-000000000001",
                        "label": "bad",
                        "notes": "",
                        "faithfulness": 0.3,
                        "relevance": 0.4,
                        "query_excerpt": "x",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


# ----- CLI1: calibrate --help lists label + threshold -----


def test_cli1_calibrate_help_lists_subcommands() -> None:
    result = _run_cli("calibrate", "--help")
    assert result.returncode == 0, result.stderr
    assert "label" in result.stdout
    assert "threshold" in result.stdout


# ----- CLI2: calibrate threshold --help shows --in -----


def test_cli2_threshold_help_shows_in_flag() -> None:
    result = _run_cli("calibrate", "threshold", "--help")
    assert result.returncode == 0, result.stderr
    assert "--in" in result.stdout


# ----- CLI3: threshold --in <good-yaml> exits 0 with sweep report -----


def test_cli3_threshold_with_good_yaml_prints_sweep_report(good_yaml: Path) -> None:
    result = _run_cli("calibrate", "threshold", "--in", str(good_yaml))
    assert result.returncode == 0, f"stderr={result.stderr}"
    out = result.stdout
    for expected in ("threshold", "tp", "fp", "tn", "fn", "P", "R", "F1"):
        assert expected in out, f"missing column header: {expected}"
    assert "Best F1:" in out
    assert "Suggested .env value:" in out
    assert "BAD_ANSWER_FAITHFULNESS_THRESHOLD=" in out


# ----- CLI4: threshold --in <missing> exits 2 with helpful stderr -----


def test_cli4_threshold_missing_file_exits_2(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    result = _run_cli("calibrate", "threshold", "--in", str(missing))
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()


# ----- CLI5: threshold prompt-version mismatch exits 2 (Pitfall 6) -----


def test_cli5_threshold_prompt_version_mismatch_exits_2(stale_yaml: Path) -> None:
    result = _run_cli("calibrate", "threshold", "--in", str(stale_yaml))
    assert result.returncode == 2
    assert "Re-run" in result.stderr
    # Pitfall 6 mitigation: stderr names both stale and current versions.
    assert "v0.old-prompts" in result.stderr
    assert PROMPT_VERSION in result.stderr


# ----- CLI6: no subcommand exits 2 (argparse required) -----


def test_cli6_no_subcommand_exits_2() -> None:
    result = _run_cli()
    assert result.returncode == 2
    # argparse-standard message contains "the following arguments are required"
    assert "required" in result.stderr.lower()


# ----- CLI7: calibrate without sub-subcommand exits 2 -----


def test_cli7_calibrate_without_sub_subcommand_exits_2() -> None:
    result = _run_cli("calibrate")
    assert result.returncode == 2
    assert "required" in result.stderr.lower()


# ----- CLI8: calibrate label --n 0 short-circuits BEFORE asyncpg pool -----


def test_cli8_label_n0_short_circuits_without_db(tmp_path: Path) -> None:
    """The n<=0 guard must precede asyncpg.create_pool so this test runs in CI
    without a live DATABASE_URL. The test sets DATABASE_URL to an unreachable
    host -- if the guard fired correctly, the CLI never tries to connect.
    """
    env = _child_env()
    # Point DATABASE_URL at an obviously unreachable host. If the n<=0 guard is
    # broken, asyncpg will hang (or fail with a connection error) and this test
    # will surface that regression.
    env["DATABASE_URL"] = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/none"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tracer_ai.cli",
            "calibrate",
            "label",
            "--n",
            "0",
            "--strategy",
            "recent",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15.0,
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "Nothing to label" in result.stdout
