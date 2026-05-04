# Wireframe: Bad-Answer Queue

ASCII wireframe + component inventory for the `/dashboard/queue` route — the operator's triage surface for answers flagged either by a user (thumbs-down) or by the LLM judge (faithfulness below threshold). The queue is the **input** to the closed-loop regression set: bad answers triaged here become regression cases promoted via Phase 6 CLI-05.

## Route

`/dashboard/queue`

## Bound API Endpoints

- `GET /traces?feedback=down` — User-flagged tab (sorted by `created_at DESC`).
- `GET /traces?min_faithfulness=0.6` — Judge-flagged tab (sorted by `faithfulness ASC`; the `min_faithfulness=0.6` filter is the calibration threshold from ADR 008 / D-12 — Phase 5 EVAL-06 may retune it).
- `POST /feedback` (Phase 5 FBCK-04 follow-up) — when "Mark Resolved" lands a resolution note. **Resolution endpoint is TBD in Phase 5; this wireframe documents the UI surface only.**
- Promote-to-regression-set CLI hook is wired in Phase 6 CLI-05 — the `Promote` button currently opens a Dialog and shows a Toast; backend hookup deferred.

## Component Inventory

| Region | Component | Library |
|--------|-----------|---------|
| Page header | `Card` (variant=ghost) | shadcn/ui |
| Queue title + count badge | `Badge` (variant=destructive when count > 0) | shadcn/ui |
| Source toggle (User-flagged / Judge-flagged) | `Tabs` | shadcn/ui |
| Queue table | `Table` (sorted by faithfulness ASC for judge-flagged; by created_at DESC for user-flagged) | shadcn/ui |
| Row: faithfulness badge | `Badge` (variant=destructive when < 0.6, warning when 0.6–0.75) | shadcn/ui |
| Row: rating badge | `Badge` (variant=destructive) | shadcn/ui |
| Row action — view trace | `Button` (variant=link) -> `/dashboard/traces/{trace_id}` | shadcn/ui |
| Row action — Mark Resolved | `Button` (variant=ghost) | shadcn/ui |
| Row action — Promote to Regression Set | `Button` (variant=primary) | shadcn/ui |
| Promote dialog | `Dialog` + `Textarea` (notes) + Submit `Button` | shadcn/ui |
| Resolved confirmation | `Toast` (variant=success) | shadcn/ui |

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  Dashboard › Queue   [42 bad answers]            [Chat] [Dashboard]      │
├──────────────────────────────────────────────────────────────────────────┤
│  [ User-flagged (17) ]  [ Judge-flagged (25) ]                           │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ started_at │ query                  │ faith │ rating │ actions  │    │
│  ├──────────────────────────────────────────────────────────────────┤    │
│  │ 04:13:02   │ What is prompt cachi…  │ 0.42  │  👎    │ ⓘ ✓ ⤴   │    │
│  │ 04:08:14   │ How do tools work in…  │ 0.51  │  —     │ ⓘ ✓ ⤴   │    │
│  │ 03:55:33   │ Are batches synchron…  │ 0.55  │  👎    │ ⓘ ✓ ⤴   │    │
│  │ 03:42:01   │ Vision: which models…  │ 0.58  │  —     │ ⓘ ✓ ⤴   │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                  [ Load more ]           │
│                                                                          │
│  Legend:  ⓘ View trace   ✓ Mark resolved   ⤴ Promote to regression set   │
└──────────────────────────────────────────────────────────────────────────┘
```

Promote dialog (centered, dimmed backdrop):

```text
                 ┌──────────────────────────────────────────────┐
                 │  Promote to Regression Set                ✕  │
                 ├──────────────────────────────────────────────┤
                 │  Trace: 660f9511…                            │
                 │  Query: "What is prompt caching?"            │
                 │  Faithfulness: 0.42  (judge-flagged)         │
                 │                                              │
                 │  Notes (optional):                           │
                 │  ┌──────────────────────────────────────┐    │
                 │  │ Retriever returned auth chunks      │    │
                 │  │ instead of prompt-caching chunks.   │    │
                 │  └──────────────────────────────────────┘    │
                 │                                              │
                 │                    [Cancel]   [Promote]      │
                 └──────────────────────────────────────────────┘
```

## States

| State | What shows |
|-------|------------|
| Loading | Tab bar visible; `Table` shows 5 skeleton rows; count badges show `—`. |
| Empty | When the active tab has zero rows: centered card "No bad answers in this queue 🎉" + a hint "Switch to the other tab to triage user-flagged answers" (or vice versa). The other tab's count badge remains visible. |
| Error | Inline `Alert` (variant=destructive) above the table; retry button re-issues `GET /traces` with the active filter; tab bar remains interactive. |
| Populated | Filled `Table` sorted per the active tab's rule (judge-flagged: `faithfulness ASC`; user-flagged: `created_at DESC`); count badges populated; `Load more` enabled when `next_cursor != null`. |

## Interactions

- **Switch tab:** changes the active filter. User-flagged tab calls `GET /traces?feedback=down`; Judge-flagged tab calls `GET /traces?min_faithfulness=0.6`. Tab selection mirrors to URL (`?source=user` vs `?source=judge`) for shareability.
- **Click row:** navigates to `/dashboard/traces/{trace_id}`.
- **View trace icon (ⓘ):** same as click row — navigates to trace detail.
- **Mark Resolved (✓):** records a resolution note locally and removes the row from the active queue with an optimistic update. The Phase 5 FBCK-04 endpoint will persist the resolution; until then the action is local-only and a `Toast` notes "Resolution recorded — will sync once Phase 5 FBCK-04 ships." (This honors the wireframe-as-contract for Phase 5 implementers.)
- **Promote to Regression Set (⤴):** opens the Promote `Dialog`. On Submit, Phase 6 CLI-05 will append a row to `/docs/eval/coverage_set.yaml` (or a sibling regression-cases file). Until that endpoint ships, the button shows a `Toast` "Promotion staged — Phase 6 CLI will persist." The Dialog captures the operator's notes regardless so they're not lost.
- **Faithfulness badge color:** red when `< 0.6` (the calibration threshold), amber when `0.6–0.75`, green elsewhere; thresholds match D-12 / ADR 008.
