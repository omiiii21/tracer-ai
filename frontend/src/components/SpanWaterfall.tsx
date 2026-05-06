// frontend/src/components/SpanWaterfall.tsx
// Hand-rolled span waterfall (D-4.15). Pure Tailwind CSS; no chart library.
// Each row = one span; bar absolute-positioned within the parent track.
// rag.eval row is rendered ONLY when an rag.eval span exists in the response
// (Phase 4 D-4.16: forward-compat for Phase 5 EVAL-04 — Phase 4 spans never
// include rag.eval, so the waterfall renders 4 rows in Phase 4).

import * as React from "react";

import { cn } from "@/lib/utils";
import type { SpanInDetail } from "@/types/trace";

interface SpanWaterfallProps {
  spans: SpanInDetail[];
  rootDurationMs: number;
  className?: string;
}

interface SpanRowProps {
  span: SpanInDetail;
  rootStartedAt: string;          // ISO8601
  rootDurationMs: number;
  isAsync: boolean;               // true for rag.eval (parent-line glyph differs)
  isLast: boolean;
  expanded: boolean;
  onToggle: () => void;
}

function _spanDurationMs(span: SpanInDetail): number {
  if (!span.ended_at) return 0;
  return new Date(span.ended_at).getTime() - new Date(span.started_at).getTime();
}

function SpanRow({
  span,
  rootStartedAt,
  rootDurationMs,
  isAsync,
  isLast,
  expanded,
  onToggle,
}: SpanRowProps): React.ReactElement {
  const spanStart = new Date(span.started_at).getTime();
  const spanEnd = span.ended_at
    ? new Date(span.ended_at).getTime()
    : spanStart;
  const rootStart = new Date(rootStartedAt).getTime();
  const leftPct = Math.max(0, ((spanStart - rootStart) / rootDurationMs) * 100);
  const widthPct = Math.max(0, ((spanEnd - spanStart) / rootDurationMs) * 100);
  const durationMs = spanEnd - spanStart;
  // Async spans (rag.eval) get a dashed parent-line glyph per wireframe.
  const glyph = isLast ? (isAsync ? "└╌╌" : "└─") : "├─";

  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          "relative flex items-center h-8 border-b border-border last:border-0",
          "w-full text-left hover:bg-muted/40 focus:outline-none focus:bg-muted/60",
        )}
        aria-expanded={expanded}
        aria-controls={`span-attrs-${span.span_id}`}
      >
        <span
          className="font-mono text-xs text-muted-foreground w-6 shrink-0 pl-1"
          aria-hidden="true"
        >
          {glyph}
        </span>
        <span className="font-mono text-xs text-muted-foreground w-36 shrink-0 truncate">
          {span.name}
        </span>
        <div className="relative flex-1 h-4 bg-muted/30 rounded-sm mx-2">
          <div
            className={cn(
              "absolute h-full rounded-sm",
              isAsync ? "bg-emerald-500" : "bg-blue-500",
            )}
            style={{
              left: `${leftPct}%`,
              width: `max(4px, ${widthPct}%)`,
            }}
          />
        </div>
        <span className="text-xs text-muted-foreground w-16 text-right pr-2 shrink-0 tabular-nums">
          {durationMs}ms
        </span>
      </button>
      {expanded && (
        <pre
          id={`span-attrs-${span.span_id}`}
          className="text-xs font-mono bg-muted p-2 rounded overflow-auto mx-4 my-1"
        >
          {JSON.stringify(span.attrs, null, 2)}
        </pre>
      )}
    </>
  );
}

export function SpanWaterfall({
  spans,
  rootDurationMs,
  className,
}: SpanWaterfallProps): React.ReactElement {
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());

  const toggle = React.useCallback((spanId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(spanId)) next.delete(spanId);
      else next.add(spanId);
      return next;
    });
  }, []);

  // D-4.16: rag.eval row hidden when absent. Phase 4 spans never include it.
  // Sort by started_at ASC for deterministic top-down rendering.
  const sortedSpans = React.useMemo(() => {
    return [...spans].sort((a, b) =>
      new Date(a.started_at).getTime() - new Date(b.started_at).getTime(),
    );
  }, [spans]);

  if (sortedSpans.length === 0) {
    return (
      <div className={cn("text-sm text-muted-foreground p-4", className)}>
        No spans recorded for this trace.
      </div>
    );
  }

  // The first span is the root (rag.request) by started_at order.
  const rootStartedAt = sortedSpans[0].started_at;
  // rootDurationMs may be 0 if trace.latency_ms is null (in-flight). Coalesce to
  // wall-clock span duration of root for sensible scaling.
  const effectiveRootDurationMs =
    rootDurationMs > 0
      ? rootDurationMs
      : Math.max(1, _spanDurationMs(sortedSpans[0]));

  return (
    <div className={cn("flex flex-col", className)}>
      {sortedSpans.map((span, idx) => (
        <SpanRow
          key={span.span_id}
          span={span}
          rootStartedAt={rootStartedAt}
          rootDurationMs={effectiveRootDurationMs}
          isAsync={span.name === "rag.eval"}
          isLast={idx === sortedSpans.length - 1}
          expanded={expanded.has(span.span_id)}
          onToggle={() => toggle(span.span_id)}
        />
      ))}
    </div>
  );
}
