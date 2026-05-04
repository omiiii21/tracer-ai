"""tracer_ai/ module DAG enforcement (D-2.27).

Walks tracer_ai/ AST and asserts every cross-package import satisfies the
locked DAG from docs/module-deps.md. Exits 0 on success; exits 1 with one
line per violating edge on failure.

Per RESEARCH.md Topic 9 Pitfall: must walk the full AST (not regex
``import X`` lines) because the dominant pattern is ``from tracer_ai.rag
import pipeline`` -- regex misses these.

Per Open Question Q1: this is the custom 60+ line guard the operator
selected over import-linter for portfolio narrative reasons. To swap to
import-linter, install ``import-linter``, ship a ``.importlinter`` config
(see RESEARCH.md Topic 9 lines 1077-1100), and replace this script's
pre-commit hook entry with ``bash -c 'uv run lint-imports'``.

CLI:
    python infra/scripts/import_cycle_guard.py
    python infra/scripts/import_cycle_guard.py --package <path>
    python infra/scripts/import_cycle_guard.py --test-fixture <path>
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# LAYERS -- mirrors docs/module-deps.md acyclicity statement.
# Index 0 = leaves; higher index = "later" layer; edges may only flow from
# lower index to higher index (left-to-right in module-deps.md flowchart LR).
LAYERS: list[set[str]] = [
    {"config", "errors"},  # leaves
    {"tracer", "corpus"},  # foundation
    {"rag", "eval"},  # orchestration
    {"api", "cli"},  # entry points
]

# Narrow exception per docs/module-deps.md Module Purpose Table:
# corpus may import ONLY rag.embedder (NOT full rag/) -- STATE.md decision.
# Phase 2 has no rag/embedder.py yet, but the rule ships from day one.
NARROW_ALLOWED_EDGES: set[tuple[str, str]] = {
    ("corpus", "rag.embedder"),
}


def layer_of(package_name: str) -> int | None:
    """Return the layer index (0..n) of a tracer_ai sub-package, or None if unknown."""
    for idx, members in enumerate(LAYERS):
        if package_name in members:
            return idx
    return None


def package_of_module(module_name: str) -> str:
    """Strip submodule path: tracer_ai.rag.pipeline -> rag (the immediate sub-package)."""
    parts = module_name.split(".")
    # Expect 'tracer_ai.<package>.<...>' or 'tracer_ai.<package>'
    if len(parts) >= 2 and parts[0] == "tracer_ai":
        return parts[1]
    return module_name


def _imports_in_file(path: Path) -> list[str]:
    """Parse a .py file and return all imported module names (full dotted form).

    Per fix B-2: when an ``ast.ImportFrom`` carries ``names``, ONLY emit the alias-derived
    full target (e.g., ``tracer_ai.rag.embedder``) -- do NOT additionally emit the bare
    from-module (e.g., ``tracer_ai.rag``). The bare entry is a strict subset of the
    information already in the alias form and would cause false positives when a
    narrow exception (corpus -> rag.embedder) is checked: the bare ``tracer_ai.rag``
    target reduces to package ``rag``, which is NOT in NARROW_ALLOWED_EDGES, so the
    edge is incorrectly flagged. Emitting only the alias-derived target lets the
    narrow-exception check see the full path it needs (``rag.embedder``).
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            # Reconstruct: from tracer_ai.rag import embedder -> tracer_ai.rag.embedder
            # We deliberately DO NOT emit the bare ``node.module`` -- the alias-derived
            # form is strictly more specific and avoids the narrow-exception false
            # positive described in the docstring above.
            if node.names:
                for alias in node.names:
                    found.append(f"{node.module}.{alias.name}")
            else:
                # Defensive: if for some reason names is empty (shouldn't happen for
                # valid Python), fall back to the bare module so we don't lose the edge.
                found.append(node.module)
    return found


def check(package_root: Path) -> list[str]:
    """Return a list of violation messages; empty list = no violations."""
    violations: list[str] = []
    for py_file in sorted(package_root.rglob("*.py")):
        if py_file.name.startswith("."):
            continue
        relative = py_file.relative_to(package_root.parent)
        # Determine the importing package: tracer_ai/<pkg>/...
        parts = relative.parts
        if len(parts) < 2 or parts[0] != "tracer_ai":
            continue
        importer_pkg = parts[1]
        importer_layer = layer_of(importer_pkg)
        if importer_layer is None:
            continue  # e.g. tracer_ai/__init__.py at root -- no layer

        for imp in _imports_in_file(py_file):
            # Only check intra-tracer_ai imports
            if not imp.startswith("tracer_ai."):
                continue
            target_pkg = package_of_module(imp)
            if target_pkg == importer_pkg:
                continue  # same-package imports are always fine
            target_layer = layer_of(target_pkg)
            if target_layer is None:
                continue

            # Forbidden: importing FROM a higher layer (target_layer > importer_layer)
            # Allowed: importing from a lower or equal layer (target_layer <= importer_layer)
            #   ... because edges flow leaves -> entry points; api imports from rag, not vice versa.
            if target_layer > importer_layer:
                # Check the narrow exception list.
                # Reconstruct narrow form: e.g., "corpus" importing "rag.embedder".
                # The imp string is dotted (e.g. ``tracer_ai.rag.embedder``); the
                # narrow target is ``<target_pkg>.<submodule>``.
                imp_parts = imp.split(".", 2)
                submodule = imp_parts[2] if len(imp_parts) >= 3 else ""
                narrow_target = f"{target_pkg}.{submodule}".rstrip(".")
                if (importer_pkg, narrow_target) in NARROW_ALLOWED_EDGES:
                    continue
                violations.append(
                    f"{relative}: {importer_pkg} (layer {importer_layer}) "
                    f"-> {target_pkg} (layer {target_layer}) -- {imp} violates DAG"
                )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="tracer_ai/ module DAG enforcement (D-2.27).")
    parser.add_argument(
        "--package",
        default="tracer_ai",
        help="Package root to walk (default: tracer_ai/ relative to repo root).",
    )
    parser.add_argument(
        "--test-fixture",
        default=None,
        help="Walk a test-fixture directory instead of tracer_ai/.",
    )
    args = parser.parse_args()

    target = Path(args.test_fixture) if args.test_fixture else Path(args.package)

    if not target.exists():
        sys.stderr.write(f"ERROR: {target} not found\n")
        return 2

    violations = check(target)
    if violations:
        sys.stderr.write("Module DAG violations detected (per docs/module-deps.md):\n")
        for v in violations:
            sys.stderr.write(f"  {v}\n")
        return 1

    sys.stdout.write(f"OK: {target} module DAG check clean ({len(LAYERS)} layers).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
