"""Phase 5 eval module -- LLM-as-judge + (Wave 2) dispatcher + calibration."""

from tracer_ai.eval.calibrate import (
    CalibrationEntry,
    render_sweep_report,
    run_label,
    run_threshold_sweep,
)
from tracer_ai.eval.dispatcher import EvalDispatcher
from tracer_ai.eval.llm_judge import (
    PROMPT_VERSION,
    SUBMIT_EVAL_TOOL,
    AnthropicJudge,
    MockJudge,
    get_judge_semaphore,
)
from tracer_ai.eval.protocols import EvalScores, Judge, ToolUseParseError

__all__ = [
    "PROMPT_VERSION",
    "SUBMIT_EVAL_TOOL",
    "AnthropicJudge",
    "CalibrationEntry",
    "EvalDispatcher",
    "EvalScores",
    "Judge",
    "MockJudge",
    "ToolUseParseError",
    "get_judge_semaphore",
    "render_sweep_report",
    "run_label",
    "run_threshold_sweep",
]
