"""Smoke-import test (covers INFRA-01 per RESEARCH.md §Validation Architecture).

This test was Wave-0 in the validation architecture: it MUST pass once Wave 4
ships tracer_ai/config.py with the Settings class. Until then, the
config-import test is parametrized to skip gracefully.
"""

import importlib

import pytest


def test_package_version_exposed() -> None:
    """tracer_ai package exposes only __version__ (D-2.02)."""
    import tracer_ai

    assert hasattr(tracer_ai, "__version__")
    assert isinstance(tracer_ai.__version__, str)
    assert tracer_ai.__version__ == "0.1.0"


@pytest.mark.parametrize(
    "module_name",
    [
        "tracer_ai.errors",
        "tracer_ai.tracer",
        "tracer_ai.tracer.span",
        "tracer_ai.tracer.context",
        "tracer_ai.tracer.store",
        "tracer_ai.tracer.exporters",
        "tracer_ai.tracer.exporters.postgres",
        "tracer_ai.rag",
        "tracer_ai.eval",
        "tracer_ai.corpus",
        "tracer_ai.api",
        "tracer_ai.cli",
        "tracer_ai.cli.partition",
    ],
)
def test_module_importable(module_name: str) -> None:
    """Every module in the tracer_ai/ tree must be importable (INFRA-01)."""
    importlib.import_module(module_name)


def test_otel_attribute_constants_present() -> None:
    """Phase 2 stub of tracer/span.py carries the OTel constants block (D-2.40).

    `gen_ai.system` MUST NOT appear as a runtime constant — only as a
    commented-out DEPRECATED line, which Python doesn't expose on the module.
    """
    from tracer_ai.tracer import span

    assert span.GEN_AI_PROVIDER_NAME == "gen_ai.provider.name"
    assert not hasattr(span, "GEN_AI_SYSTEM")
    # Spot-check rag.* constants
    assert span.RAG_EVAL_FAITHFULNESS == "rag.eval.faithfulness"
    assert span.RAG_PROMPT_TEMPLATE_ID == "rag.prompt_template.id"


def test_partition_helper_stub_raises() -> None:
    """Phase 2 ships partition.create_next_month_partition() as a stub raising NotImplementedError (D-2.18)."""
    from tracer_ai.cli.partition import create_next_month_partition

    with pytest.raises(NotImplementedError):
        create_next_month_partition()
