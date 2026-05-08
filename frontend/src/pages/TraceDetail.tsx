// frontend/src/pages/TraceDetail.tsx
// Phase 4 EXPL-04 — trace detail. Wireframe: docs/wireframes/dashboard-detail.md.
// Phase 5 FBCK-05 — adds diagnosis-tag Select on the Feedback tab. Allowed
// values are the locked Phase 1 contract (Retrieval / PromptAssembly / LLM /
// CorpusStale / Other; docs/trace-schema.md feedback.user §). Selection POSTs
// a new feedback row via POST /feedback (existing endpoint already accepts
// diagnosis_tag — see tracer_ai/api/feedback.py + schemas.py).
//
// Open Question 4 resolution (RESEARCH.md): Phase 5 ACCEPTS the duplicate-row
// UX — a Select-change creates a new feedback row with the same rating + new
// diagnosis_tag. Last write wins on the queue (queue queries naturally show
// the most recent via ORDER BY started_at DESC). For v2, add
// PATCH /feedback/{feedback_id} to update in place.

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Metric, Text, Title } from "@tremor/react";
import { Link, useParams } from "react-router-dom";

import { getTrace, postFeedback } from "@/api/traces";
import { SpanWaterfall } from "@/components/SpanWaterfall";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

// Phase 5 FBCK-05 — locked allowed values per docs/trace-schema.md feedback.user
// section. Backend stores `diagnosis_tag: str | None` (no Literal constraint;
// reserved-but-flexible per Phase 1) so calibration may add categories without
// a migration. The frontend pins the v1 set explicitly.
const DIAGNOSIS_TAGS = [
  "Retrieval",
  "PromptAssembly",
  "LLM",
  "CorpusStale",
  "Other",
] as const;
type DiagnosisTag = (typeof DIAGNOSIS_TAGS)[number];

function DiagnosisTagPanel({
  traceId,
  current,
  feedbackRating,
}: {
  traceId: string;
  current: string | null;
  feedbackRating: 1 | -1 | null;
}): React.ReactElement {
  const [tag, setTag] = React.useState<DiagnosisTag | "none">(
    (current as DiagnosisTag | null) ?? "none",
  );
  const [error, setError] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const submitMutation = useMutation({
    mutationFn: async (newTag: DiagnosisTag | "none") => {
      // POST /feedback with the existing rating + the new diagnosis_tag.
      // The Phase 4 POST /feedback endpoint already accepts diagnosis_tag.
      // If the trace has no prior rating we default to -1 (operator-tagged
      // = bad); otherwise we preserve the existing rating. Last-write-wins
      // on the queue side (Open Question 4 resolution).
      const ratingToSend: 1 | -1 = feedbackRating ?? -1;
      await postFeedback({
        trace_id: traceId,
        rating: ratingToSend,
        diagnosis_tag: newTag === "none" ? null : newTag,
      });
    },
    onSuccess: () => {
      // Invalidate the detail query so the diagnosis_tag re-renders from the
      // latest feedback row, plus the queue and queue-health caches so the
      // operator's downstream views stay consistent.
      queryClient.invalidateQueries({ queryKey: ["trace", traceId] });
      queryClient.invalidateQueries({ queryKey: ["queue"] });
      queryClient.invalidateQueries({ queryKey: ["queue-health"] });
      setError(null);
    },
    onError: (e: Error) => {
      setError(e.message ?? "Failed to save diagnosis tag");
    },
  });

  return (
    <div className="mt-4 flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <Text>Diagnosis tag:</Text>
        <Select
          value={tag}
          onValueChange={(v) => {
            const newTag = v as DiagnosisTag | "none";
            setTag(newTag);
            submitMutation.mutate(newTag);
          }}
        >
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Tag diagnosis" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">— none —</SelectItem>
            {DIAGNOSIS_TAGS.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {submitMutation.isPending && (
          <Text className="text-xs">Saving…</Text>
        )}
      </div>
      {error && (
        <Text className="text-xs text-rose-600">Error: {error}</Text>
      )}
      <Text className="text-xs text-muted-foreground">
        Selecting a tag records a new feedback row with the current rating +
        diagnosis_tag (Phase 5 FBCK-05; last-write-wins on the queue).
      </Text>
    </div>
  );
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
  // Phase 5 EVAL-04 ships rag.eval; this effect now activates live.
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
            {/* Phase 5 FBCK-05 — diagnosis-tag Select. data.diagnosis_tag is
                detail-only (TraceDetailResponse) — sourced from the most-recent
                feedback row; backend wires this in a follow-up step (frontend
                degrades gracefully to "— none —" when the backend hasn't
                surfaced it yet). */}
            <DiagnosisTagPanel
              traceId={trace.trace_id}
              current={data.diagnosis_tag ?? null}
              feedbackRating={trace.feedback_rating}
            />
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
