// frontend/src/pages/TraceDetail.tsx
// Phase 4 EXPL-04 — trace detail. Wireframe: docs/wireframes/dashboard-detail.md.

import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Metric, Text, Title } from "@tremor/react";
import { Link, useParams } from "react-router-dom";

import { getTrace } from "@/api/traces";
import { SpanWaterfall } from "@/components/SpanWaterfall";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import type { TraceDetailResponse } from "@/types/trace";

function _formatCost(usd: number): string {
  return `$${usd.toFixed(5)}`;
}

export function TraceDetail(): React.ReactElement {
  const { trace_id } = useParams<{ trace_id: string }>();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery<
    TraceDetailResponse,
    Error
  >({
    queryKey: ["trace", trace_id],
    queryFn: () => getTrace(trace_id!),
    enabled: Boolean(trace_id),
  });

  // D-4.18 + D-4.16: one-shot 5s refetch when rag.eval span exists but is in-flight.
  // In Phase 4 rag.eval never appears → this useEffect is a no-op (forward-compat).
  const evalSpan = data?.spans.find((s) => s.name === "rag.eval");
  const evalPending = Boolean(evalSpan && !evalSpan.ended_at);
  React.useEffect(() => {
    if (!evalPending || !trace_id) return;
    const timer = setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["trace", trace_id] });
    }, 5000);
    return () => clearTimeout(timer);
  }, [evalPending, trace_id, queryClient]);

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto p-8 space-y-6">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <Link
          to="/dashboard"
          className="text-sm text-muted-foreground hover:underline mb-4 inline-block"
        >
          ← Back to dashboard
        </Link>
        <Card className="border-rose-300 bg-rose-50">
          <Title>Failed to load trace</Title>
          <Text>{error?.message ?? "Unknown error"}</Text>
        </Card>
      </div>
    );
  }

  const trace = data.trace;
  const spans = data.spans;
  const payloads = data.payloads;
  const rootDurationMs = trace.latency_ms;

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-6">
      <Link
        to="/dashboard"
        className="text-sm text-muted-foreground hover:underline mb-2 inline-block"
      >
        ← Back to dashboard
      </Link>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight font-mono">
          {trace.trace_id}
        </h1>
        <p className="text-muted-foreground text-sm mt-1 truncate">
          {trace.query_text}
        </p>
      </div>

      {/* Header KPI card */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <Title>LATENCY</Title>
          <Metric>{trace.latency_ms}ms</Metric>
        </Card>
        <Card>
          <Title>COST</Title>
          <Metric>{_formatCost(trace.estimated_cost_usd)}</Metric>
        </Card>
        <Card>
          <Title>FAITHFULNESS</Title>
          <Metric>
            {trace.faithfulness !== null ? trace.faithfulness.toFixed(2) : "—"}
          </Metric>
          {trace.faithfulness === null && <Text>Eval pending (Phase 5)</Text>}
        </Card>
        <Card>
          <Title>FEEDBACK</Title>
          <Metric>
            <Badge
              variant={
                trace.feedback_rating === 1
                  ? "default"
                  : trace.feedback_rating === -1
                    ? "destructive"
                    : "outline"
              }
            >
              {trace.feedback_rating === 1
                ? "up"
                : trace.feedback_rating === -1
                  ? "down"
                  : "—"}
            </Badge>
          </Metric>
        </Card>
      </div>

      {/* Tabs: Spans / Payloads / Feedback */}
      <Tabs defaultValue="spans" className="w-full">
        <TabsList>
          <TabsTrigger value="spans">Spans</TabsTrigger>
          <TabsTrigger value="payloads">Payloads</TabsTrigger>
          <TabsTrigger value="feedback">Feedback</TabsTrigger>
        </TabsList>

        <TabsContent value="spans" className="mt-4">
          <Card>
            <SpanWaterfall spans={spans} rootDurationMs={rootDurationMs} />
          </Card>
        </TabsContent>

        <TabsContent value="payloads" className="mt-4 space-y-4">
          {spans
            .filter((s) => payloads[s.span_id] !== undefined)
            .map((s) => (
              <div key={s.span_id}>
                <p className="text-xs font-mono font-semibold mb-1">
                  {s.name}
                </p>
                <pre className="text-xs font-mono bg-muted p-2 rounded overflow-auto">
                  {JSON.stringify(payloads[s.span_id].payload, null, 2)}
                </pre>
              </div>
            ))}
          {Object.keys(payloads).length === 0 && (
            <p className="text-sm text-muted-foreground">
              No payloads recorded for this trace.
            </p>
          )}
        </TabsContent>

        <TabsContent value="feedback" className="mt-4">
          <Card>
            <Title>Feedback for this trace</Title>
            <Text>
              {trace.feedback_rating === 1
                ? "User gave thumbs up."
                : trace.feedback_rating === -1
                  ? "User gave thumbs down."
                  : "No feedback recorded yet."}
            </Text>
            <Text className="mt-2 text-xs text-muted-foreground">
              Phase 5 FBCK-05 will surface diagnosis tag + comment here.
            </Text>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
