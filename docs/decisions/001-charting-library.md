# ADR 001: Charting Library — Tremor v3

## Status

Accepted — 2026-05-04

## Context

The tracer-ai dashboard surfaces multiple time-series visualizations: faithfulness mean over time, latency p50/p95, cost per request rolled up by hour, and the manual feedback ratio (thumbs-up / thumbs-down) over rolling windows. These power the dashboard requirements (`DASH-01` through `DASH-04`) and feedback-tracking views (`FBCK-*`). The frontend is a Vite + React 18 + TypeScript SPA already committed to Tailwind v3 and shadcn/ui (Radix-based components), so the chart library must be Tailwind-native and not conflict with shadcn's PostCSS configuration.

For a portfolio-grade build with a ~12-hour budget, chart-authoring velocity matters more than maximal customization. We need declarative, copy-pastable chart components that harmonize with the existing component palette out of the box.

This decision resolves [GSD-OPEN-1](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **Tremor v3 (chosen):** `@tremor/react@^3.0.0`. Recharts-backed; declarative `AreaChart` / `LineChart` / `BarChart` components with a Tailwind color API (`colors={["blue", "emerald", "rose"]}`). Tremor Blocks supplies pre-built KPI grids and chart panels.
- **Recharts directly (rejected):** ~40 LOC per chart vs Tremor's ~10 LOC; manual Tailwind theming via inline SVG style props; no pre-built dashboard layouts. Acceptable as the escape hatch (it is already a Tremor peer dependency) but not as the primary surface.
- **Visx (rejected):** Airbnb's D3-React primitives. ~2x development time for equivalent charts; too low-level for portfolio velocity. Reserve for genuinely custom visualizations (force graphs, custom waterfalls) — not needed in v1.

## Decision

tracer-ai will use **Tremor v3** (`@tremor/react@^3.0.0`) as the primary charting library for all dashboard time-series and KPI components. Tremor wraps Recharts internally; raw Recharts (already a peer dependency) remains an in-package escape hatch for any custom chart not covered by Tremor's component set (e.g., score-distribution histograms in the bad-answer queue). All Tremor chart `colors` props use Tailwind palette names so the dashboard automatically inherits the shadcn/ui theme.

## Consequences

**Positive:**
- ~75% LoC reduction vs raw Recharts for common time-series charts.
- Tailwind-native color API means chart palettes auto-harmonize with shadcn/ui components — no parallel theme system.
- Tremor Blocks provides ready-made KPI card grids and chart panels — directly usable for the quality-metrics overview page.
- Recharts escape hatch is free (already installed as peer dep), so we are not locked out of custom visualizations.

**Negative:**
- **Tailwind v3 pin is mandatory.** Tremor v3 is incompatible with Tailwind v4; do NOT upgrade Tailwind in this project. shadcn/ui also targets v3, so the pin is reinforced.
- Bundle size adds ~180KB (Tremor + Recharts together). Acceptable for an internal dashboard; would be revisited only if the frontend grows public-facing surfaces.
- Tied to Recharts' release cadence transitively. If Recharts ships a breaking change, Tremor's pin lags briefly.

**Mandatory follow-ups:**
- [ ] Pin `tailwindcss` to `^3.4.x` in `frontend/package.json` (Phase 0 INFRA-02).
- [ ] Add Tremor's `tailwind.config.js` content paths so Tremor classes are not purged in production builds.

## References

- [.planning/research/STACK.md §"GSD-OPEN-1"](../../.planning/research/STACK.md)
- [.planning/research/SUMMARY.md §"Recommended Stack"](../../.planning/research/SUMMARY.md)
- [ADR 002: Vector Store](./002-vector-store.md) — sibling decision in the GSD-OPEN-N series.
