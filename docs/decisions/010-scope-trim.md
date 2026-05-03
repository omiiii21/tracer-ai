# ADR 010: Scope-Trim Plan — What Gets Cut First if Budget Slips >25%

## Status

Accepted — 2026-05-04

## Context

tracer-ai's build budget target is **~12 hours of focused work** across Phases 0–7. A 25% slip — i.e., projected hours exceeding **15** — triggers this trim plan. The purpose is to **reduce decision fatigue at the moment of the slip**: when a phase is overrunning, the worst time to design a cut order is in the middle of the overrun. A pre-codified, ordered cut list lets the operator make a fast, defensible reduction without re-litigating priorities under time pressure.

The trim is **reversible**. If a later phase finishes under budget, a previously-cut item can be re-added. The cuts are also **listed but not pre-approved** — invoking the trim plan still requires updating PROJECT.md "Out of Scope" with the reason, so the cut is a deliberate act, not an automatic one.

This ADR addresses [DSGN-09](../../.planning/REQUIREMENTS.md) — risk and scope-trim plan.

## Options Considered

- **Codified cut order (chosen):** A ranked list of items to drop, in order, when the trigger fires. Reduces decision fatigue at the slip moment; preserves the load-bearing demo path and observability core.
- **No plan, ad-hoc cuts (rejected):** Invites scope creep + delivery risk. The operator would face every cut as a fresh judgment call under time pressure — exactly the worst conditions for good prioritization.
- **Cut by phase (rejected):** "Drop Phase 7" is too coarse — Phase 7 polish is not all equal value. The cut order below preserves the highest-value Phase 7 item (the clean-state acceptance test) while dropping lower-value polish.

## Decision

If projected build hours exceed **15** (a **25%** slip vs the ~12-hour target), invoke the trim plan **in this order**:

1. **DEMO-02** (GIF/screenshots), **DEMO-03** (cost widget), **DEMO-04** (JSON-export button) — keep README + the clean-state acceptance test only. The README + clean-state test together demonstrate "it boots green on a fresh machine"; the GIFs and cost widget are polish.
2. **DASH-04** (manual feedback ratio chart over time) — keep the KPI tile only. The KPI shows the current ratio; the chart was redundant historical context.
3. **FBCK-05** (per-stage failure diagnosis tag UI) — keep the schema column on the trace, drop the UI for setting it. The schema preserves the v2 data; the UI is the sacrifice.
4. **CLI-04** (markdown report from `tracer-ai eval`) — keep the JSON output only. JSON is the load-bearing CI artifact; markdown is human-friendly polish.
5. **EVAL-06** (judge calibration set size) — drop from ~30 hand-labeled traces to ~15. Halving the calibration set degrades threshold tuning quality but keeps the calibration step itself in scope.

Cuts are **listed but not pre-approved** — invoking the trim plan requires updating `.planning/PROJECT.md` "Out of Scope" and noting the reason. Cuts are **reversible** if a later phase finishes under budget.

## Consequences

**Positive:**
- Predictable cut order — the slip-moment decision shrinks from "what should I cut?" to "how many of the listed cuts do I need?".
- Preserves the load-bearing demo path: README + clean-state test together prove portability.
- Preserves the observability core: eval pipeline, judge, bad-answer queue, and the regression CLI all survive the cut order.
- Schema-vs-UI splits (FBCK-05, CLI-04) preserve future-feature optionality at low present-cost.

**Negative:**
- Cut items lose polish — README without GIFs is plainer; dashboard without the historical feedback chart is less rich. Reversal requires explicit PROJECT.md update — friction is intentional.
- The 25% trigger is a heuristic. The real signal is "the operator believes the budget is at risk"; the percentage is a sharper version of that intuition.
- Halving the calibration set in step 5 noticeably degrades threshold tuning. Last-resort cut for exactly that reason.

**Mandatory follow-ups:**
- [ ] If invoked, update `.planning/PROJECT.md` "Out of Scope" with the cut item(s) and the reason.
- [ ] If reversed (later phase finishes under budget), update PROJECT.md again to record the re-instatement.

## References

- [.planning/research/FEATURES.md §"P3 / Defer"](../../.planning/research/FEATURES.md) — cut-source candidates.
- [.planning/PROJECT.md §"Out of Scope"](../../.planning/PROJECT.md) — canonical cut record.
- [.planning/REQUIREMENTS.md](../../.planning/REQUIREMENTS.md) — DEMO-*, DASH-*, FBCK-*, CLI-*, EVAL-* requirement entries.
- [ADR 009: Auth and Deployment](./009-auth-deployment-direction.md) — sibling operational ADR.
