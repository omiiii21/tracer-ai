"""Phase 4 alembic reversibility -- upgrade head -> downgrade -1 -> upgrade head clean.

Skipped automatically when no `db` service is reachable; the CI / docker compose
flow runs this against a real Postgres 16 + pgvector instance.
"""

from __future__ import annotations

import os
import subprocess

import pytest

# Project compose file lives at infra/docker-compose.yml (per Plan 04-01 Deviation 2).
_DOCKER_COMPOSE = ["docker", "compose", "-f", "infra/docker-compose.yml"]


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _docker_compose_available() -> bool:
    try:
        rc, _, _ = _run(["docker", "compose", "version"])
        return rc == 0
    except FileNotFoundError:
        return False


@pytest.mark.skipif(
    not _docker_compose_available(),
    reason="docker compose CLI not available in this environment",
)
def test_alembic_upgrade_downgrade_upgrade_clean() -> None:
    """Forward -> backward -> forward must all succeed without errors."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    # Step 1: upgrade to head (idempotent -- gets us to 0002)
    rc, out, err = _run(
        [*_DOCKER_COMPOSE, "run", "--rm", "migrate", "alembic", "upgrade", "head"],
        cwd=repo_root,
    )
    assert rc == 0, f"alembic upgrade head failed:\nstdout={out}\nstderr={err}"

    # Step 2: downgrade -1 (rolls back 0002)
    rc, out, err = _run(
        [*_DOCKER_COMPOSE, "run", "--rm", "migrate", "alembic", "downgrade", "-1"],
        cwd=repo_root,
    )
    assert rc == 0, f"alembic downgrade -1 failed:\nstdout={out}\nstderr={err}"

    # Step 3: upgrade head again (re-applies 0002)
    rc, out, err = _run(
        [*_DOCKER_COMPOSE, "run", "--rm", "migrate", "alembic", "upgrade", "head"],
        cwd=repo_root,
    )
    assert rc == 0, f"alembic upgrade head (second time) failed:\nstdout={out}\nstderr={err}"

    # Verify the new columns are present after re-upgrade
    rc, out, err = _run(
        [
            *_DOCKER_COMPOSE,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "tracer",
            "-d",
            "tracer_ai",
            "-c",
            "\\d traces",
        ],
        cwd=repo_root,
    )
    assert rc == 0, f"psql \\d traces failed:\n{err}"
    for col in ["latency_ms", "faithfulness", "feedback_rating", "estimated_cost_usd"]:
        assert col in out, f"column {col} missing after re-upgrade:\n{out}"
