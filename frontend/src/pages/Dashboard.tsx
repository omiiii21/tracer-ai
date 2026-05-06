// frontend/src/pages/Dashboard.tsx
// Phase 4 EXPL-03 — trace list dashboard. Wireframe: docs/wireframes/dashboard-list.md.

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AreaChart, Card, Metric, Text, Title } from "@tremor/react";
import { useNavigate } from "react-router-dom";

import { getTraces } from "@/api/traces";
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
    staleTime: 0,                  // D-4.18: dashboard always re-fetches
  });

  const items: TraceListItem[] = data?.items ?? [];
  const totalLatency =
    items.length > 0 ? _avg(items.map((i) => i.latency_ms)) : 0;
  const totalCost = items.reduce((acc, i) => acc + i.estimated_cost_usd, 0);
  const downCount = items.filter((i) => i.feedback_rating === -1).length;

  // Mini AreaChart placeholder — Phase 4 has no faithfulness data; render with
  // empty series. Phase 5 EVAL-04 will populate.
  const chartData = items.map((i) => ({
    time: new Date(i.started_at).toLocaleTimeString(),
    faithfulness: i.faithfulness ?? null,
  }));

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto p-8 space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <div className="grid grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
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

      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-4">
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
      </div>

      {/* Quality drift mini-chart (placeholder; Phase 5 fills in) */}
      <Card>
        <Title>Quality drift</Title>
        <Text>
          faithfulness over the visible window — populates in Phase 5
        </Text>
        <AreaChart
          data={chartData}
          index="time"
          categories={["faithfulness"]}
          colors={["emerald"]}
          showLegend={false}
          showGridLines={false}
          className="h-32 mt-4"
        />
      </Card>

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
