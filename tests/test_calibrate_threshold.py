"""Phase 5 Plan 05-06 unit tests for tracer_ai/eval/calibrate.py threshold sweep.

Tests TH1-TH9 cover:
- TH1: _iter_thresholds() yields exactly 13 values 0.30..0.90 step 0.05 (no FP drift)
- TH2: confusion_at(entries, threshold=0.5) on a fixture set
- TH3: precision_recall_f1(2, 0, 1) -> (1.0, 2/3, 0.8)
- TH4: precision_recall_f1(0, 0, 5) -> (0.0, 0.0, 0.0) (no division by zero)
- TH5: run_threshold_sweep over a synthetic 30-entry YAML
- TH6: prompt_version mismatch raises ValueError (Pitfall #6 mitigation)
- TH7: missing entries key raises ValueError
- TH8: render_sweep_report writes the expected columns + suggested env value
- TH9: render_sweep_report shows the small-N caveat when n_labeled < 50
"""

from __future__ import annotations

import os

# Pre-set required env vars BEFORE importing tracer_ai.* (per Plan 05-01 pattern):
# pytest autouse fixtures only run after collection-time imports, so a fresh
# Settings() at module-top of any tracer_ai imports would raise ValidationError
# without these defaults.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-x")
os.environ.setdefault("VOYAGE_API_KEY", "voy-x")

from pathlib import Path

import pytest
import yaml

from tracer_ai.eval.calibrate import (
    CalibrationEntry,
    _iter_thresholds,
    confusion_at,
    precision_recall_f1,
    render_sweep_report,
    run_threshold_sweep,
)
from tracer_ai.eval.llm_judge import PROMPT_VERSION

# ----- TH1: thresholds enumerate exactly 13 values without FP drift -----


def test_iter_thresholds_yields_13_values_with_no_fp_drift() -> None:
    values = list(_iter_thresholds())
    assert values == [
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
    ]
    # Each value is rounded to 2 decimals (no 0.30000000004 drift):
    for v in values:
        assert v == round(v, 2)


# ----- TH2: confusion_at on a fixture set -----


def _fixture_entries() -> list[CalibrationEntry]:
    """Build the TH2 fixture: 3 good + 3 bad + 1 skip.

    Goods: f=0.7, 0.8, 0.9 (all >= 0.5 -> tn=3 at threshold=0.5)
    Bads:  f=0.2, 0.4, 0.55 (0.2/0.4 < 0.5 -> tp=2; 0.55 >= 0.5 -> fn=1)
    Skip:  f=0.5 (excluded from confusion matrix)
    """
    return [
        CalibrationEntry(trace_id="g1", label="good", notes="", faithfulness=0.7),
        CalibrationEntry(trace_id="g2", label="good", notes="", faithfulness=0.8),
        CalibrationEntry(trace_id="g3", label="good", notes="", faithfulness=0.9),
        CalibrationEntry(trace_id="b1", label="bad", notes="", faithfulness=0.2),
        CalibrationEntry(trace_id="b2", label="bad", notes="", faithfulness=0.4),
        CalibrationEntry(trace_id="b3", label="bad", notes="", faithfulness=0.55),
        CalibrationEntry(trace_id="s1", label="skip", notes="", faithfulness=0.5),
    ]


def test_confusion_at_threshold_0_5_correct_for_fixture() -> None:
    entries = _fixture_entries()
    tp, fp, tn, fn = confusion_at(entries, threshold=0.5)
    assert (tp, fp, tn, fn) == (2, 0, 3, 1)


# ----- TH3: precision_recall_f1 happy path -----


def test_precision_recall_f1_with_tp_2_fp_0_fn_1() -> None:
    p, r, f1 = precision_recall_f1(tp=2, fp=0, fn=1)
    assert p == pytest.approx(1.0, abs=1e-9)
    assert r == pytest.approx(2.0 / 3.0, abs=1e-9)
    assert f1 == pytest.approx(0.8, abs=1e-9)


# ----- TH4: precision_recall_f1 zero-division guard -----


def test_precision_recall_f1_zero_division_returns_zeros() -> None:
    p, r, f1 = precision_recall_f1(tp=0, fp=0, fn=5)
    assert p == 0.0
    assert r == 0.0
    assert f1 == 0.0


# ----- TH5: run_threshold_sweep over a synthetic 30-entry YAML -----


def _write_synthetic_yaml(path: Path, prompt_version: str | None = None) -> None:
    """Build a 30-entry YAML where the analytical best F1 threshold is known.

    15 good entries with faithfulness in [0.65, 0.95] (well above any threshold tested).
    15 bad  entries with faithfulness in [0.10, 0.55] (well below 0.6 mostly).

    At threshold = 0.60: tp = 15 (all bads <0.6 except the one at 0.55? all <0.6 so tp=15),
    fp = 0 (all goods >= 0.65), fn = 0 -> P=R=F1=1.0. This will be the best.
    """
    bads_f = [
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.42,
        0.45,
        0.48,
        0.50,
        0.52,
        0.54,
        0.55,
        0.55,
    ]
    goods_f = [
        0.65,
        0.68,
        0.70,
        0.72,
        0.75,
        0.78,
        0.80,
        0.82,
        0.85,
        0.87,
        0.90,
        0.92,
        0.93,
        0.94,
        0.95,
    ]

    entries = []
    for i, f in enumerate(bads_f):
        entries.append(
            {
                "trace_id": f"bad-{i}",
                "label": "bad",
                "notes": "",
                "faithfulness": f,
                "relevance": 0.5,
                "query_excerpt": "x",
            }
        )
    for i, f in enumerate(goods_f):
        entries.append(
            {
                "trace_id": f"good-{i}",
                "label": "good",
                "notes": "",
                "faithfulness": f,
                "relevance": 0.85,
                "query_excerpt": "y",
            }
        )
    data = {
        "schema_version": 1,
        "created_at": "2026-05-08T00:00:00Z",
        "calibration_strategy": "stratified",
        "prompt_version": prompt_version or PROMPT_VERSION,
        "judge_model": "claude-haiku-4-5-20251001",
        "entries": entries,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_run_threshold_sweep_finds_best_threshold(tmp_path: Path) -> None:
    yaml_path = tmp_path / "calibration_set.yaml"
    _write_synthetic_yaml(yaml_path)

    result = run_threshold_sweep(yaml_path)
    assert "best_threshold" in result
    assert "best_f1" in result
    assert "sweep" in result
    assert "n_labeled" in result
    assert result["n_labeled"] == 30
    assert len(result["sweep"]) == 13
    # The synthetic data should yield an exact F1 at threshold 0.60 (all 15 bads
    # below threshold; all 15 goods above): tp=15, fp=0, fn=0 -> P=R=F1=1.0.
    assert result["best_f1"] == pytest.approx(1.0, abs=1e-9)
    assert result["best_threshold"] == pytest.approx(0.60, abs=1e-9)


# ----- TH6: prompt_version mismatch refuses with helpful error (Pitfall 6) -----


def test_run_threshold_sweep_refuses_on_prompt_version_mismatch(tmp_path: Path) -> None:
    yaml_path = tmp_path / "calibration_set.yaml"
    _write_synthetic_yaml(yaml_path, prompt_version="v0.old")

    with pytest.raises(ValueError) as exc_info:
        run_threshold_sweep(yaml_path)
    msg = str(exc_info.value)
    # Pitfall 6 mitigation: error message names BOTH the stale yaml version,
    # the current PROMPT_VERSION, and instructs the operator to re-run.
    assert "v0.old" in msg
    assert PROMPT_VERSION in msg
    assert "Re-run" in msg


# ----- TH7: malformed YAML missing entries key raises ValueError -----


def test_run_threshold_sweep_raises_on_missing_entries_key(tmp_path: Path) -> None:
    yaml_path = tmp_path / "calibration_set.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "prompt_version": PROMPT_VERSION,
                # NOTE: no `entries:` key
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        run_threshold_sweep(yaml_path)
    assert "entries" in str(exc_info.value)


def test_run_threshold_sweep_raises_on_missing_file(tmp_path: Path) -> None:
    yaml_path = tmp_path / "does-not-exist.yaml"
    with pytest.raises(ValueError) as exc_info:
        run_threshold_sweep(yaml_path)
    assert "not found" in str(exc_info.value).lower()


# ----- TH8: render_sweep_report contains the expected columns + suggested env -----


def test_render_sweep_report_contains_required_strings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    yaml_path = tmp_path / "calibration_set.yaml"
    _write_synthetic_yaml(yaml_path)
    result = run_threshold_sweep(yaml_path)

    report = render_sweep_report(result)
    # Required column-header substrings:
    for expected in ("threshold", "tp", "fp", "tn", "fn", "P", "R", "F1"):
        assert expected in report, f"missing required column header: {expected}"
    # Required summary substrings:
    assert "Best F1:" in report
    assert "Suggested .env value:" in report
    assert "BAD_ANSWER_FAITHFULNESS_THRESHOLD=" in report
    assert f"{result['best_threshold']}" in report

    # The CLI prints this; verify capsys-via-print works through render+print:
    print(report)
    captured = capsys.readouterr()
    assert "Best F1:" in captured.out


# ----- TH9: render_sweep_report includes small-N caveat when n_labeled < 50 -----


def test_render_sweep_report_shows_small_n_caveat_below_50(tmp_path: Path) -> None:
    yaml_path = tmp_path / "calibration_set.yaml"
    _write_synthetic_yaml(yaml_path)  # 30 entries
    result = run_threshold_sweep(yaml_path)

    report = render_sweep_report(result)
    assert "small-N calibration" in report


def test_render_sweep_report_omits_caveat_above_50() -> None:
    # Synthesize an n=60 result dict directly (faster than building a 60-entry YAML).
    result = {
        "sweep": [
            {"threshold": 0.5, "tp": 1, "fp": 0, "tn": 1, "fn": 0, "p": 1.0, "r": 1.0, "f1": 1.0},
        ],
        "best_threshold": 0.5,
        "best_f1": 1.0,
        "n_labeled": 60,
        "prompt_version": PROMPT_VERSION,
        "judge_model": "claude-haiku-4-5-20251001",
    }
    report = render_sweep_report(result)
    assert "small-N calibration" not in report
