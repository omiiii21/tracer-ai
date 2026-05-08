// frontend/src/pages/Queue.tsx
// Phase 5 FBCK-03/04/06 — bad-answer queue. Wireframe: docs/wireframes/bad-answer-queue.md.
//
// Tabs split User-flagged (feedback=down) vs. Judge-flagged
// (max_faithfulness=THRESHOLD, sort_by=faithfulness_asc). Threshold is read
// from GET /admin/eval-config (D-5.13: single source of truth — backend filter
// uses the same value, drift = bug). Mark Resolved calls Plan 05-02's
// PATCH /feedback/{trace_id}/resolved and invalidates the queue + dashboard
// + queue-health caches so the dashboard 5th KpiCard (FBCK-07) refreshes
// immediately. The Promote button is a Phase-6-stub (CLI-05 wires it).

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Text, Title } from "@tremor/react";
import { useNavigate } from "react-router-dom";

import { getEvalConfig, getTraces, markResolved } from "@/api/traces";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import type {
  EvalConfigResponse,
  TraceListItem,
  TraceListResponse,
} from "@/types/trace";

type Tab = "user" | "judge";

// Phase 4 wireframe contract: faithfulness color thresholds.
//   < 0.50  → red    ("destructive")
//   < 0.75  → amber  ("outline" — Badge has no "warning" variant)
//   ≥ 0.75  → green  ("default")
// Note: Badge component supports {default, secondary, destructive, outline}
// only — "warning" is NOT a valid variant so we use "outline" with custom
// border tint by class for the amber band.
function faithfulnessVariant(
  score: number | null,
): "destructive" | "outline" | "default" {
  if (score === null) return "outline";
  if (score < 0.5) return "destructive";
  if (score < 0.75) return "outline";
  return "default";
}

export function Queue(): React.ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = React.useState<Tab>("user");

  // 1. Pull threshold from /admin/eval-config (D-5.13: single source of truth).
  //    Falls back to 0.6 (project default) if the endpoint is unreachable so
  //    the page degrades gracefully — backend filter is still authoritative.
  const { data: cfg } = useQuery<EvalConfigResponse, Error>({
    queryKey: ["eval-config"],
    queryFn: getEvalConfig,
    staleTime: 30_000,
  });
  const threshold = cfg?.threshold ?? 0.6;

  // 2. User-flagged tab: feedback=down; default sort (created_at_desc).
  const userQuery = useQuery<TraceListResponse, Error>({
    queryKey: ["queue", "user"],
    queryFn: () => getTraces({ feedback: "down", limit: 50 }),
    staleTime: 0, // FBCK-02: thumbs-down lands within seconds
    refetchOnWindowFocus: true,
    enabled: tab === "user",
  });

  // 3. Judge-flagged tab: max_faithfulness=THRESHOLD + sort_by=faithfulness_asc.
  //    queryKey spreads `threshold` as a separate array member (D-4.18 pattern;
  //    threshold change triggers refetch).
  const judgeQuery = useQuery<TraceListResponse, Error>({
    queryKey: ["queue", "judge", threshold],
    queryFn: () =>
      getTraces({
        max_faithfulness: threshold,
        sort_by: "faithfulness_asc",
        limit: 50,
      }),
    staleTime: 0,
    refetchOnWindowFocus: true,
    enabled: tab === "judge",
  });

  // 4. Mark Resolved mutation — Plan 05-02 PATCH /feedback/{trace_id}/resolved.
  //    onSuccess invalidates:
  //      - ["queue"]         → queue page re-fetches; resolved row disappears
  //      - ["dashboard-kpis"] → dashboard KPI strip re-fetches (legacy key
  //                            preserved for forward-compat with any KPI-strip
  //                            queries that happen to use that key)
  //      - ["queue-health"]  → dashboard 5th KpiCard (FBCK-07) refreshes
  //                            within a tick instead of waiting for the 30s
  //                            polling tick — operator-visible feedback loop.
  const resolveMutation = useMutation({
    mutationFn: (traceId: string) => markResolved(traceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queue"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
      queryClient.invalidateQueries({ queryKey: ["queue-health"] });
    },
  });

  // 5. Promote-stub mutation — Phase 6 CLI-05 will replace with real backend
  //    call to POST /admin/regression-set. Currently a no-op; the button is
  //    disabled with a tooltip pointing to Phase 6 (preserves the wireframe
  //    contract without falsely promising functionality).
  const promoteMutation = useMutation({
    mutationFn: async (_traceId: string): Promise<void> => {
      // No-op for now; backend hookup in Phase 6.
    },
    onSuccess: () => {
      // TODO Phase 6: invalidate regression-set query
    },
  });

  const activeQuery = tab === "user" ? userQuery : judgeQuery;
  const items = activeQuery.data?.items ?? [];

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Bad-Answer Queue
        </h1>
        <Text>
          Triage low-quality traces. Threshold = {threshold.toFixed(2)} (from
          GET /admin/eval-config; calibrate with{" "}
          <code className="font-mono text-xs bg-muted px-1 py-0.5 rounded">
            tracer-ai calibrate threshold
          </code>
          ).
        </Text>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList>
          <TabsTrigger value="user">User-flagged</TabsTrigger>
          <TabsTrigger value="judge">
            Judge-flagged (faithfulness &lt; {threshold.toFixed(2)})
          </TabsTrigger>
        </TabsList>
        <TabsContent value={tab} className="mt-4">
          {activeQuery.isLoading ? (
            <Skeleton className="h-48 w-full" />
          ) : activeQuery.isError ? (
            <Card className="border-rose-300 bg-rose-50">
              <Title>Failed to load queue</Title>
              <Text>{activeQuery.error?.message ?? "Unknown error"}</Text>
            </Card>
          ) : items.length === 0 ? (
            <Card>
              <Title>Empty</Title>
              <Text>
                No {tab === "user" ? "user-flagged" : "judge-flagged"} traces
                in the current window. Either nothing has gone wrong or
                feedback / eval has not been recorded yet.
              </Text>
            </Card>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Query</TableHead>
                  <TableHead className="text-right">Faithfulness</TableHead>
                  <TableHead>Rating</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((it: TraceListItem) => (
                  <TableRow key={it.trace_id}>
                    <TableCell className="font-mono text-xs">
                      {new Date(it.started_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="max-w-md truncate">
                      <button
                        type="button"
                        onClick={() =>
                          navigate(`/dashboard/traces/${it.trace_id}`)
                        }
                        className="text-left hover:underline"
                      >
                        {it.query_text}
                      </button>
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge variant={faithfulnessVariant(it.faithfulness)}>
                        {it.faithfulness !== null
                          ? it.faithfulness.toFixed(2)
                          : "—"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          it.feedback_rating === -1
                            ? "destructive"
                            : "outline"
                        }
                      >
                        {it.feedback_rating === -1 ? "👎" : "—"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right space-x-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => resolveMutation.mutate(it.trace_id)}
                        disabled={resolveMutation.isPending}
                      >
                        ✓ Mark Resolved
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => promoteMutation.mutate(it.trace_id)}
                        disabled
                        title="Phase 6 CLI-05 will wire this"
                      >
                        ↑ Promote
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
