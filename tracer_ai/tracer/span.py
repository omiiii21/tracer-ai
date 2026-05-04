"""OTel-aligned + RAG-specific attribute name constants (Phase 2 stub).

This module ships ONLY the attribute-name constants block from
docs/trace-schema.md (Python attribute constants section). Span emission
helpers, dataclasses, and lifecycle methods land in Phase 4 TRCR-01..04.

Per ADR 005: NO `opentelemetry-sdk` runtime dependency. Constants are bare
strings; downstream code consumes them as JSONB attribute keys.

Per D-2.40 / ADR 005: the OTel GenAI legacy provider-identifier attribute
(see the comment-line marker below) is DEPRECATED in the current spec. Use
`gen_ai.provider.name` (= "anthropic") for tracer-ai's LLM spans instead.
The deprecated marker is preserved on a single COMMENTED-OUT line below so
the pre-commit grep gate (Wave 5, comment-stripping pre-filter per threat
T-2-01-04) treats this file as clean.
"""

# DEPRECATED: gen_ai.system  (kept commented-out for posterity; D-2.40)

# OTel GenAI namespace (Development stability — see docs/trace-schema.md)
GEN_AI_PROVIDER_NAME: str = "gen_ai.provider.name"
GEN_AI_OPERATION_NAME: str = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL: str = "gen_ai.request.model"
GEN_AI_USAGE_INPUT_TOKENS: str = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS: str = "gen_ai.usage.output_tokens"

# rag.* custom namespace (tracer-ai-specific; see docs/trace-schema.md)
RAG_RETRIEVED_CHUNKS: str = "rag.retrieved_chunks"
RAG_RETRIEVAL_SCORE_MEAN: str = "rag.retrieval.score.mean"
RAG_RETRIEVAL_SCORE_MIN: str = "rag.retrieval.score.min"
RAG_PROMPT_TEMPLATE_ID: str = "rag.prompt_template.id"
RAG_EVAL_FAITHFULNESS: str = "rag.eval.faithfulness"
RAG_EVAL_RELEVANCE: str = "rag.eval.relevance"
RAG_EVAL_JUDGE_MODEL: str = "rag.eval.judge_model"
RAG_EVAL_JUDGE_PROMPT_VERSION: str = "rag.eval.judge_prompt_version"
RAG_EVAL_JUDGE_COST_USD: str = "rag.eval.judge_cost_usd"

# feedback namespace
FEEDBACK_DIAGNOSIS_TAG: str = "feedback.diagnosis_tag"
