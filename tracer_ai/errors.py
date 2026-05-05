"""Cross-cutting error types (Phase 2 stub; Phase 3 fills bodies as adapters land).

errors.py is a leaf module per docs/module-deps.md -- zero imports from sibling
tracer_ai modules.
"""


class TracerAIError(Exception):
    """Base exception for tracer-ai. Subclasses defined per phase as needed."""


class CorpusEmbeddingMismatchError(RuntimeError):
    """CORP-04 fail-fast: persisted chunks were written with a different embedding model.

    Raised by ``tracer_ai.api.lifespan`` during startup before the api binds the
    port. Pitfall 7.3 / ADR 003 mitigation -- silent garbage-retrieval would
    otherwise occur because cosine distance against a vector embedded by a
    different model has no semantic meaning.
    """
