"""Phase 5 EVAL-06 calibration: hand-label traces and tune the bad-answer threshold.

Two operator-facing flows:

1. ``tracer-ai calibrate label --n 30 --strategy stratified`` -- walk N most-recent /
   random / stratified-by-faithfulness traces; prompt [g]ood/[b]ad/[s]kip + notes;
   append to ``docs/eval/calibration_set.yaml``. Read-only against the DB; does NOT
   re-run the judge (judge scores are already in ``rag.eval`` spans / ``traces.faithfulness``).

2. ``tracer-ai calibrate threshold`` -- read the YAML, run best-F1 sweep over
   [0.3, 0.9] step 0.05, print sweep table + suggested env-var value (D-5.12).

Pitfall 6 mitigation: ``run_threshold_sweep`` refuses to run when the YAML's
``prompt_version`` does not match the runtime ``PROMPT_VERSION`` constant. The
operator must rerun ``calibrate label`` against the new prompts to get fresh labels.

Print-allowlist invariant (D-2.37): this module does NOT call ``print()`` directly.
``render_sweep_report`` returns a string; the CLI dispatcher in
``tracer_ai/cli/__main__.py`` (the only file in tracer_ai/ allowed raw print) emits
it. ``run_label`` writes interactive prompts to ``sys.stderr`` to keep stdout clean
for piping.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import asyncpg
import yaml

from tracer_ai.config import settings
from tracer_ai.eval.llm_judge import PROMPT_VERSION

YAML_SCHEMA_VERSION = 1


@dataclass
class CalibrationEntry:
    """One labeled trace in the calibration set.

    Mirrors the YAML row schema (RESEARCH.md Pattern 7). The dataclass shape lets
    tests construct fixtures inline without round-tripping through YAML.
    """

    trace_id: str
    label: Literal["good", "bad", "skip"]
    notes: str
    faithfulness: float
    relevance: float = 0.0
    query_excerpt: str = ""


# ----- Threshold sweep helpers -----


def _iter_thresholds(start: float = 0.3, stop: float = 0.9, step: float = 0.05) -> Iterator[float]:
    """Yield thresholds with no floating-point drift via integer-loop arithmetic.

    Default: 0.30, 0.35, ..., 0.90 -> 13 values. Each value is rounded to 2
    decimals so test equality checks are not subject to FP representation drift.
    """
    n = round((stop - start) / step) + 1
    return (round(start + i * step, 2) for i in range(n))


def confusion_at(
    entries: list[CalibrationEntry],
    threshold: float,
) -> tuple[int, int, int, int]:
    """Return ``(tp, fp, tn, fn)`` where positive = "bad" (faithfulness < threshold).

    Skip-labeled entries are excluded from the confusion matrix.
    """
    tp = fp = tn = fn = 0
    for e in entries:
        if e.label == "skip":
            continue
        predicted_bad = e.faithfulness < threshold
        actual_bad = e.label == "bad"
        if predicted_bad and actual_bad:
            tp += 1
        elif predicted_bad and not actual_bad:
            fp += 1
        elif not predicted_bad and not actual_bad:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Standard precision/recall/F1 with explicit zero-division guard."""
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    return p, r, f1


def run_threshold_sweep(yaml_path: Path) -> dict[str, Any]:
    """Read the YAML, sweep [0.3, 0.9] step 0.05, return result dict.

    Raises ValueError if the YAML's prompt_version doesn't match the runtime
    PROMPT_VERSION (Pitfall 6 mitigation -- a stale calibration set would
    silently pin the threshold against an obsolete judge prompt body).
    """
    if not yaml_path.exists():
        raise ValueError(
            f"Calibration set not found at {yaml_path}. "
            f"Run `tracer-ai calibrate label --n 30` first to produce it."
        )
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "entries" not in data:
        raise ValueError(
            f"Calibration set at {yaml_path} is malformed: " f"missing top-level `entries:` key."
        )

    yaml_prompt_version = data.get("prompt_version", "<unknown>")
    if yaml_prompt_version != PROMPT_VERSION:
        raise ValueError(
            f"Calibration set was labeled against judge_prompt_version="
            f"{yaml_prompt_version!r} but current PROMPT_VERSION is "
            f"{PROMPT_VERSION!r}. Re-run `tracer-ai calibrate label --n 30` "
            f"to relabel against the current prompts (Pitfall 6)."
        )

    entries = [CalibrationEntry(**row) for row in data["entries"]]
    rows: list[dict[str, Any]] = []
    best_t = 0.6
    best_f1 = -1.0
    for t in _iter_thresholds():
        tp, fp, tn, fn = confusion_at(entries, t)
        p, r, f1 = precision_recall_f1(tp, fp, fn)
        rows.append(
            {
                "threshold": t,
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
                "p": p,
                "r": r,
                "f1": f1,
            }
        )
        if f1 > best_f1:
            best_f1 = f1
            best_t = t
    return {
        "sweep": rows,
        "best_threshold": best_t,
        "best_f1": best_f1,
        "n_labeled": len(entries),
        "prompt_version": PROMPT_VERSION,
        "judge_model": settings.llm_judge_model,
    }


# ----- Reporting (called from cli/__main__.py print allowlist) -----


def render_sweep_report(result: dict[str, Any]) -> str:
    """Build the human-readable sweep report as a single string.

    The CLI dispatcher (cli/__main__.py) emits via ``print()``. This function
    must NOT print -- D-2.37 invariant. Future eval-CLI-rescore (Phase 6) can
    reuse this same renderer.
    """
    lines: list[str] = []
    n = int(result["n_labeled"])
    lines.append(f"Calibrated against N={n} labeled traces.")
    lines.append(
        f"Judge model: {result['judge_model']}; " f"prompt_version: {result['prompt_version']}.\n"
    )
    lines.append(
        f"{'threshold':>10}  {'tp':>4}  {'fp':>4}  {'tn':>4}  {'fn':>4}  "
        f"{'P':>5}  {'R':>5}  {'F1':>5}"
    )
    for row in result["sweep"]:
        lines.append(
            f"{row['threshold']:>10.2f}  {row['tp']:>4}  {row['fp']:>4}  "
            f"{row['tn']:>4}  {row['fn']:>4}  "
            f"{row['p']:>5.2f}  {row['r']:>5.2f}  {row['f1']:>5.2f}"
        )
    lines.append(f"\nBest F1: {result['best_f1']:.3f} at threshold {result['best_threshold']:.2f}")
    lines.append("\nSuggested .env value:")
    lines.append(f"  BAD_ANSWER_FAITHFULNESS_THRESHOLD={result['best_threshold']}")
    if n < 50:
        lines.append(
            f"\nNote: small-N calibration (N={n}). Re-run after expanding the "
            f"calibration set to >= 50 traces for higher confidence."
        )
    return "\n".join(lines)


# ----- Label-session flow -----


# Each strategy is a parameterized SELECT against the live traces table; the
# operator-supplied `n` lands as $1. WHERE faithfulness IS NOT NULL excludes
# in-flight traces (matches the Phase 4 list-traces invariant). The relevance
# subquery pulls AVG of rag.eval span attribute keyed by the OTel spec name.
_SELECT_TRACES_SQL: dict[str, str] = {
    "recent": (
        "SELECT id, query_text, latency_ms, faithfulness, "
        "  (SELECT COALESCE(AVG((s.attrs->>'rag.eval.relevance')::float), 0.0) "
        "    FROM spans s WHERE s.trace_id = t.id AND s.name = 'rag.eval') AS relevance "
        "FROM traces t "
        "WHERE faithfulness IS NOT NULL "
        "ORDER BY started_at DESC "
        "LIMIT $1"
    ),
    "random": (
        "SELECT id, query_text, latency_ms, faithfulness, "
        "  (SELECT COALESCE(AVG((s.attrs->>'rag.eval.relevance')::float), 0.0) "
        "    FROM spans s WHERE s.trace_id = t.id AND s.name = 'rag.eval') AS relevance "
        "FROM traces t "
        "WHERE faithfulness IS NOT NULL "
        "ORDER BY random() "
        "LIMIT $1"
    ),
    # stratified: half from < 0.6 (likely-bad) and half from >= 0.6 (likely-good)
    "stratified": (
        "(SELECT id, query_text, latency_ms, faithfulness, 0.0::float AS relevance "
        "  FROM traces WHERE faithfulness IS NOT NULL AND faithfulness < 0.6 "
        "  ORDER BY random() LIMIT ($1::int / 2)) "
        "UNION ALL "
        "(SELECT id, query_text, latency_ms, faithfulness, 0.0::float AS relevance "
        "  FROM traces WHERE faithfulness IS NOT NULL AND faithfulness >= 0.6 "
        "  ORDER BY random() LIMIT ($1::int - $1::int / 2))"
    ),
}


@dataclass
class _SelectTraceRow:
    """Internal row shape returned by _select_traces (typed dict equivalent).

    Tests using a stub for `_select_traces` may pass plain dicts; this dataclass
    is for documentation, not runtime validation.
    """

    id: Any
    query_text: str
    latency_ms: int
    faithfulness: float
    relevance: float = 0.0
    fields: dict[str, Any] = field(default_factory=dict)


async def _select_traces(
    pool: asyncpg.Pool,
    *,
    n: int,
    strategy: str,
) -> list[dict[str, Any]]:
    """Run the strategy SELECT and return rows as dicts.

    Pool is constructed and closed by the caller (run_label). Parameterized $1
    is the operator-supplied limit; no user input enters the SQL string.
    """
    sql = _SELECT_TRACES_SQL[strategy]
    async with pool.acquire(timeout=5.0) as conn:
        rows = await conn.fetch(sql, n)
    return [dict(r) for r in rows]


async def run_label(
    *,
    n: int = 30,
    strategy: Literal["recent", "random", "stratified"] = "recent",
    out_path: Path = Path("docs/eval/calibration_set.yaml"),
    input_fn: Callable[[str], str] = input,
) -> dict[str, int]:
    """Walk N traces; prompt operator; append to YAML. Returns counts.

    Early-returns when ``n <= 0`` BEFORE constructing the asyncpg pool. This
    makes the CLI smoke-test ``tracer-ai calibrate label --n 0`` runnable
    without a live ``DATABASE_URL`` -- verifiable in CI without a database
    secret. The CLI dispatcher in ``cli/__main__.py`` emits the user-facing
    "Nothing to label" message via print() (D-2.37 allowlist); this function
    returns counts only, keeping the print-free invariant of
    ``tracer_ai/eval/calibrate.py`` intact.

    For all interactive prompts and trace headers, output is written to
    ``sys.stderr`` so stdout stays clean for piping. The injectable ``input_fn``
    lets tests stub stdin without subprocess machinery.
    """
    if n <= 0:
        return {"entries_added": 0, "skipped": 0}

    asyncpg_dsn = str(settings.database_url).replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn=asyncpg_dsn, min_size=1, max_size=2)
    try:
        traces = await _select_traces(pool, n=n, strategy=strategy)
    finally:
        await pool.close()

    # Load existing entries if any (append mode preserves prior labels).
    existing: dict[str, Any] = {}
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    entries: list[dict[str, Any]] = list(existing.get("entries", []))
    already_labeled = {e["trace_id"] for e in entries}

    added = 0
    skipped = 0
    for tr in traces:
        tid = str(tr["id"])
        if tid in already_labeled:
            continue
        # User-facing output goes to stderr to keep stdout clean for piping.
        sys.stderr.write(
            f"\n--- Trace {tid[:8]}... ---\n"
            f"Query: {tr['query_text']}\n"
            f"Faithfulness: {float(tr['faithfulness']):.2f}\n"
            f"Latency: {tr['latency_ms']}ms\n"
        )
        ans = input_fn("Label [g]ood / [b]ad / [s]kip: ").strip().lower()
        if ans not in ("g", "b", "s"):
            ans = "s"
        label = {"g": "good", "b": "bad", "s": "skip"}[ans]
        notes = ""
        if ans in ("g", "b"):
            notes = input_fn("Notes (optional, blank to skip): ").strip()
        entries.append(
            {
                "trace_id": tid,
                "label": label,
                "notes": notes,
                "faithfulness": float(tr["faithfulness"]),
                "relevance": float(tr.get("relevance", 0.0)),
                "query_excerpt": str(tr["query_text"])[:120],
            }
        )
        if label == "skip":
            skipped += 1
        else:
            added += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "schema_version": YAML_SCHEMA_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "calibration_strategy": strategy,
                "prompt_version": PROMPT_VERSION,
                "judge_model": settings.llm_judge_model,
                "entries": entries,
            },
            f,
            default_flow_style=False,
            sort_keys=False,
        )
    return {"entries_added": added, "skipped": skipped}
