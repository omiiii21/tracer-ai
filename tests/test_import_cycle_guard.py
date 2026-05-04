"""Verify infra/scripts/import_cycle_guard.py rejects DAG violations.

Builds fake tracer_ai/-shaped package trees in tmp_path and asserts:
  1. backward edge (tracer -> api) is rejected (exit 1 with violation message);
  2. real tracer_ai/ package passes (exit 0);
  3. narrow exception (corpus -> rag.embedder) is accepted (exit 0) -- this
     is the regression test for fix B-2 (the dedup bug in _imports_in_file
     where a bare ``tracer_ai.rag`` from-module entry would have flagged the
     corpus -> rag edge as a violation).
"""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def fake_violating_pkg(tmp_path: Path) -> Path:
    """Build a tracer_ai/-shaped package with one backward edge (tracer -> api)."""
    root = tmp_path / "tracer_ai"
    root.mkdir()
    (root / "__init__.py").write_text("__version__ = '0.0.0'\n")
    # Layer 0: config (leaf)
    (root / "config.py").write_text("X = 1\n")
    # Layer 1: tracer/ -- should NOT import from api (Layer 3)
    tracer_dir = root / "tracer"
    tracer_dir.mkdir()
    (tracer_dir / "__init__.py").write_text("")
    (tracer_dir / "violator.py").write_text(
        "# Deliberate backward edge -- tracer (layer 1) importing from api (layer 3)\n"
        "from tracer_ai.api import main\n"
    )
    # Layer 3: api/ -- needs to exist so the guard finds the target package
    api_dir = root / "api"
    api_dir.mkdir()
    (api_dir / "__init__.py").write_text("")
    (api_dir / "main.py").write_text("app = None\n")
    return tmp_path


def test_guard_rejects_backward_edge(fake_violating_pkg: Path) -> None:
    """Guard MUST exit non-zero on a backward (high->low layer) import."""
    repo_root = Path(__file__).resolve().parent.parent
    guard = repo_root / "infra" / "scripts" / "import_cycle_guard.py"
    result = subprocess.run(
        [sys.executable, str(guard), "--package", str(fake_violating_pkg / "tracer_ai")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"Expected exit code 1; got {result.returncode}. "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "violates DAG" in result.stderr or "violates DAG" in result.stdout


def test_guard_passes_on_real_tracer_ai() -> None:
    """The real tracer_ai/ tree from Wave 1+2+3+4 stubs must satisfy the DAG."""
    repo_root = Path(__file__).resolve().parent.parent
    guard = repo_root / "infra" / "scripts" / "import_cycle_guard.py"
    pkg = repo_root / "tracer_ai"
    result = subprocess.run(
        [sys.executable, str(guard), "--package", str(pkg)],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0, (
        f"Expected exit code 0 on real tracer_ai/; got {result.returncode}. "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )


@pytest.fixture
def fake_corpus_imports_rag_embedder(tmp_path: Path) -> Path:
    """Build a tracer_ai/-shaped tree where corpus/ imports rag.embedder.

    Per fix B-2 + STATE.md / docs/module-deps.md NARROW_ALLOWED_EDGES, this is
    the SOLE allowed corpus -> rag edge. The guard MUST exit 0, NOT flag this
    as a violation. This is a regression guard against the dedup-bug fixed in
    ``_imports_in_file`` where the bare from-module entry would cause a false
    positive on ``corpus -> rag`` (because narrow_target reduces to ``rag``,
    which is not in NARROW_ALLOWED_EDGES -- the alias-derived ``rag.embedder``
    IS).
    """
    root = tmp_path / "tracer_ai"
    root.mkdir()
    (root / "__init__.py").write_text("__version__ = '0.0.0'\n")
    # Layer 0: config (leaf, present so layer detection works)
    (root / "config.py").write_text("X = 1\n")
    # Layer 1: corpus/ -- uses the locked narrow exception
    corpus_dir = root / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "__init__.py").write_text("")
    (corpus_dir / "chunker.py").write_text(
        "# narrow allowed edge per docs/module-deps.md\nfrom tracer_ai.rag import embedder\n"
    )
    # Layer 2: rag/embedder.py exists as the target
    rag_dir = root / "rag"
    rag_dir.mkdir()
    (rag_dir / "__init__.py").write_text("")
    (rag_dir / "embedder.py").write_text("def embed() -> None: pass\n")
    return tmp_path


def test_guard_accepts_corpus_imports_rag_embedder(
    fake_corpus_imports_rag_embedder: Path,
) -> None:
    """Regression test for fix B-2: corpus -> rag.embedder must NOT be flagged.

    Without the dedup fix in ``_imports_in_file``, this test would FAIL because
    the bare ``tracer_ai.rag`` from-module entry reduces to package ``rag``,
    which is not in NARROW_ALLOWED_EDGES.
    """
    repo_root = Path(__file__).resolve().parent.parent
    guard = repo_root / "infra" / "scripts" / "import_cycle_guard.py"
    result = subprocess.run(
        [
            sys.executable,
            str(guard),
            "--package",
            str(fake_corpus_imports_rag_embedder / "tracer_ai"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Expected exit 0 (corpus -> rag.embedder is allowed); got "
        f"{result.returncode}. stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
