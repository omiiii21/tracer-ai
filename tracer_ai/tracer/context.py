"""Context propagation helpers (Phase 2 stub; Phase 4 TRCR-04 fills).

Per docs/sequence-diagrams.md (Pitfall #1 mitigation): the eval branch will
snapshot OTel context BEFORE rag.request root span ends so rag.eval becomes
a child span, not an orphan root.
"""
