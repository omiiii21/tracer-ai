// frontend/src/pages/Dashboard.tsx
// Phase 4 EXPL-03 — trace list dashboard. Wireframe: docs/wireframes/dashboard-list.md.
// Phase 5 DASH-01..06 + FBCK-07 — adds 5th KpiCard "Queue Health" (live numbers
// from GET /admin/queue-health; D-5.16) + QualityCharts component (4 Tremor
// time-series charts fed by GET /traces/timeseries; D-5.07 connectNulls=false
// load-bearing on the faithfulness chart so judge-error gaps are visually
// distinct from low scores).

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AreaChart, Card, LineChart, Metric, Text, Title } from "@tremor/react";
import { useNavigate } from "react-router-dom";

import { getQueueHealth, getTimeseries, getTraces } from "@/api/traces";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  QueueHealthResponse,
  TimeseriesResponse,
  TraceListFilters,
  TraceListItem,
  TraceListResponse,
} from "@/types/trace";

function _formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

function _formatCost(usd: number): string {
  return `$${usd.toFixed(5)}`;
}

function _avg(numbers: number[]): number {
  return numbers.length === 0
    ? 0
    : numbers.reduce((a, b) => a + b, 0) / numbers.length;
}

type TimeseriesWindow = "1h" | "24h" | "7d" | "30d";

// Phase 5 DASH-01..04 + DASH-06 — 4 Tremor time-series charts fed by
// GET /traces/timeseries. The faithfulness chart uses connectNulls={false}
// (D-5.07; load-bearing): empty buckets land as NULL faithfulness rows and
// render as visible gaps so judge-error / no-traffic windows are visually
// distinct from low scores (Pitfall #4 mitigation in the visual layer).
function QualityCharts(): React.ReactElement {
  const [window, setWindow] = React.useState<TimeseriesWindow>("24h");

  // queryKey spreads `window` as a separate array member (D-4.18 pattern;
  // window change triggers refetch).
  const { data, isLoading, isError, error } = useQuery<
    TimeseriesResponse,
    Error
  >({
    queryKey: ["timeseries", window],
    queryFn: () => getTimeseries(window),
    staleTime: 0,
    refetchOnWindowFocus: true,
  });

  // Map the API response into Tremor's expected shape (one row per bucket
  // with index field + named numeric fields). Tremor Line/Area accept
  // null values inside number-typed series, so faithfulness_mean=null
  // produces a gap when connectNulls={false}.
  const chartData = (data?.buckets ?? []).map((b) => ({
    time: new Date(b.bucket_start).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    "Latency p50 (ms)": b.latency_p50,
    "Latency p95 (ms)": b.latency_p95,
    "Cost ($)": b.cost_sum,
    Faithfulness: b.faithfulness_mean,
    "Feedback down ratio": b.feedback_down_ratio,
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Text>Window:</Text>
        <Select
          value={window}
          onValueChange={(v) => setWindow(v as TimeseriesWindow)}
        >
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1h">Last hour</SelectItem>
            <SelectItem value="24h">Last 24h</SelectItem>
            <SelectItem value="7d">Last 7d</SelectItem>
            <SelectItem value="30d">Last 30d</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : isError ? (
        <Card className="border-rose-300 bg-rose-50">
          <Title>Failed to load timeseries</Title>
          <Text>{error?.message ?? "Unknown error"}</Text>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* DASH-01 — latency p50 / p95 */}
          <Card>
            <Title>Latency p50 / p95</Title>
            <LineChart
              data={chartData}
              index="time"
              categories={["Latency p50 (ms)", "Latency p95 (ms)"]}
              colors={["blue", "rose"]}
              connectNulls={false}
              showLegend
              valueFormatter={(n) => `${Math.round(n)}ms`}
              className="h-48 mt-4"
            />
          </Card>

          {/* DASH-02 — cost over time */}
          <Card>
            <Title>Cost over time</Title>
            <AreaChart
              data={chartData}
              index="time"
              categories={["Cost ($)"]}
              colors={["emerald"]}
              connectNulls={false}
              valueFormatter={(n) => `$${n.toFixed(4)}`}
              className="h-48 mt-4"
            />
          </Card>

          {/* DASH-03 — faithfulness mean. connectNulls={false} is LOAD-BEARING
              (D-5.07): gaps = judge errors or no traffic; both diagnostically
              distinct from low scores. */}
          <Card>
            <Title>Faithfulness mean</Title>
            <Text className="text-xs">
              Gaps = judge errors or no traffic; both diagnostically distinct
              from low scores
            </Text>
            <LineChart
              data={chartData}
              index="time"
              categories={["Faithfulness"]}
              colors={["emerald"]}
              connectNulls={false}
              minValue={0}
              maxValue={1}
              className="h-48 mt-4"
            />
          </Card>

          {/* DASH-04 — feedback down ratio */}
          <Card>
            <Title>Feedback down ratio</Title>
            <LineChart
              data={chartData}
              index="time"
              categories={["Feedback down ratio"]}
              colors={["rose"]}
              connectNulls={false}
              valueFormatter={(n) => `${(n * 100).toFixed(1)}%`}
              className="h-48 mt-4"
            />
          </Card>
        </div>
      )}
    </div>
  );
}

export function Dashboard(): React.ReactElement {
  const navigate = useNavigate();
  const [filters, setFilters] = React.useState<TraceListFilters>({});
  // Spread filter fields into the queryKey to detect field-level changes
  // (RESEARCH Pitfall 7 — object reference would not invalidate cache).
  // EXPL-01: queryKey MUST include all 5 filter dimensions (query, time range,
  // feedback, faithfulness, latency bucket) so each one independently invalidates.
  const queryKey = React.useMemo(
    () => [
      "traces",
      filters.query ?? "",
      filters.since ?? "",
      filters.until ?? "",
      filters.feedback ?? "",
      filters.min_faithfulness ?? "",
      filters.max_latency_ms ?? "",
    ],
    [filters],
  );
  const { data, isLoading, isError, error } = useQuery<
    TraceListResponse,
    Error
  >({
    queryKey,
    queryFn: () => getTraces(filters),
    staleTime: 0, // D-4.18: dashboard always re-fetches
  });

  // Phase 5 FBCK-07 — live queue-health from Plan 05-03 GET /admin/queue-health.
  // Polls every 30s; staleTime: 0 means the Mark-Resolved mutation in Queue.tsx
  // (which invalidates ["queue-health"]) will trigger an immediate refetch.
  const { data: queueHealth } = useQuery<QueueHealthResponse, Error>({
    queryKey: ["queue-health"],
    queryFn: getQueueHealth,
    refetchInterval: 30_000,
    staleTime: 0,
  });

  const items: TraceListItem[] = data?.items ?? [];
  const totalLatency =
    items.length > 0 ? _avg(items.map((i) => i.latency_ms)) : 0;
  const totalCost = items.reduce((acc, i) => acc + i.estimated_cost_usd, 0);
  const downCount = items.filter((i) => i.feedback_rating === -1).length;

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto p-8 space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <Card className="border-rose-300 bg-rose-50">
          <Title>Failed to load traces</Title>
          <Text>{error?.message ?? "Unknown error"}</Text>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>

      {/* KPI strip — 5 cards wide on lg viewports; wraps to 3+2 on md (D-5.16). */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <Card>
          <Title>TRACES</Title>
          <Metric>{items.length}</Metric>
          <Text>in current view</Text>
        </Card>
        <Card>
          <Title>AVG LATENCY</Title>
          <Metric>{Math.round(totalLatency)}ms</Metric>
          <Text>across visible</Text>
        </Card>
        <Card>
          <Title>TOTAL COST</Title>
          <Metric>{_formatCost(totalCost)}</Metric>
          <Text>across visible</Text>
        </Card>
        <Card>
          <Title>THUMBS DOWN</Title>
          <Metric>{downCount}</Metric>
          <Text>flagged answers</Text>
        </Card>
        {/* FBCK-07 — live queue-health (D-5.16). Two stacked numbers from the
            single GET /admin/queue-health response; refetches every 30s and on
            mutation (Mark-Resolved in Queue.tsx invalidates ["queue-health"]). */}
        <Card>
          <Title>QUEUE HEALTH</Title>
          <Metric>
            Queue: {queueHealth?.queue_size ?? "—"}
          </Metric>
          <Text>
            Resolved (7d): {queueHealth?.resolved_this_week ?? "—"}
          </Text>
        </Card>
      </div>

      {/* Phase 5 DASH-01..04 + DASH-06 — 4 Tremor time-series charts replacing
          the Phase 4 AreaChart placeholder. */}
      <QualityCharts />

      {/* Filter bar — EXPL-01 requires query, time range, feedback, faithfulness, latency bucket */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex flex-col">
          <label className="text-xs text-muted-foreground mb-1">Query</label>
          <Input
            placeholder="ILIKE substring"
            value={filters.query ?? ""}
            onChange={(e) =>
              setFilters({ ...filters, query: e.target.value || undefined })
            }
            className="w-64"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-muted-foreground mb-1">Since</label>
          <Input
            type="datetime-local"
            value={filters.since ?? ""}
            onChange={(e) =>
              setFilters({ ...filters, since: e.target.value || undefined })
            }
            className="w-52"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-muted-foreground mb-1">Until</label>
          <Input
            type="datetime-local"
            value={filters.until ?? ""}
            onChange={(e) =>
              setFilters({ ...filters, until: e.target.value || undefined })
            }
            className="w-52"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-muted-foreground mb-1">Feedback</label>
          <Select
            value={filters.feedback ?? "any"}
            onValueChange={(v) =>
              setFilters({
                ...filters,
                feedback: v === "any" ? undefined : (v as "up" | "down"),
              })
            }
          >
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any</SelectItem>
              <SelectItem value="up">Up</SelectItem>
              <SelectItem value="down">Down</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col w-56">
          <label className="text-xs text-muted-foreground mb-1">
            Min faithfulness: {filters.min_faithfulness ?? 0}
          </label>
          <Slider
            defaultValue={[filters.min_faithfulness ?? 0]}
            max={1}
            step={0.05}
            onValueChange={(v) =>
              setFilters({
                ...filters,
                min_faithfulness: v[0] === 0 ? undefined : v[0],
              })
            }
          />
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-muted-foreground mb-1">
            Max latency (ms)
          </label>
          <Input
            type="number"
            min={0}
            placeholder="e.g. 5000"
            value={filters.max_latency_ms ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                max_latency_ms: e.target.value
                  ? parseInt(e.target.value, 10)
                  : undefined,
              })
            }
            className="w-36"
          />
        </div>
      </div>

      {/* Trace table */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Time</TableHead>
            <TableHead>Query</TableHead>
            <TableHead className="text-right">Latency</TableHead>
            <TableHead className="text-right">Cost</TableHead>
            <TableHead className="text-right">Faithfulness</TableHead>
            <TableHead>Feedback</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={6}
                className="text-center text-muted-foreground py-8"
              >
                No traces match the current filters.
              </TableCell>
            </TableRow>
          ) : (
            items.map((item) => (
              <TableRow
                key={item.trace_id}
                onClick={() => navigate(`/dashboard/traces/${item.trace_id}`)}
                className="cursor-pointer hover:bg-muted/50"
              >
                <TableCell className="font-mono text-xs">
                  {_formatTime(item.started_at)}
                </TableCell>
                <TableCell className="max-w-md truncate">
                  {item.query_text}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {item.latency_ms}ms
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {_formatCost(item.estimated_cost_usd)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {item.faithfulness !== null
                    ? item.faithfulness.toFixed(2)
                    : "—"}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      item.feedback_rating === 1
                        ? "default"
                        : item.feedback_rating === -1
                          ? "destructive"
                          : "outline"
                    }
                  >
                    {item.feedback_rating === 1
                      ? "up"
                      : item.feedback_rating === -1
                        ? "down"
                        : "—"}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
