// frontend/src/api/traces.ts
// Typed clients for the trace-explorer + quality-feedback endpoints.
// Phase 4 EXPL-01 / EXPL-02 → GET /traces, GET /traces/{trace_id}.
// Phase 5 → GET /traces/timeseries, GET /admin/eval-config, GET /admin/queue-health,
//           PATCH /feedback/{trace_id}/resolved, POST /feedback (with diagnosis_tag).
// Backend endpoints from docs/api.md §4 + §5 + Phase 5 §6/§7/§8; runtime contract
// enforced by Pydantic strict mode (extra="forbid").

import ky from "ky";
import type {
  EvalConfigResponse,
  FeedbackResolveResponse,
  QueueHealthResponse,
  TimeseriesResponse,
  TraceDetailResponse,
  TraceListFilters,
  TraceListResponse,
} from "@/types/trace";

const _api = ky.create({
  // Vite dev server proxies /traces, /chat, /feedback, /admin to FastAPI per
  // vite.config.ts. In production the api is served from the same origin.
  prefixUrl: "",
  retry: { limit: 1 },
  timeout: 15_000,
});

export async function getTraces(
  filters: TraceListFilters,
): Promise<TraceListResponse> {
  const searchParams: Record<string, string | number> = {};
  if (filters.query) searchParams.query = filters.query;
  if (filters.since) searchParams.since = filters.since;
  if (filters.until) searchParams.until = filters.until;
  if (filters.feedback) searchParams.feedback = filters.feedback;
  if (typeof filters.min_faithfulness === "number")
    searchParams.min_faithfulness = filters.min_faithfulness;
  if (typeof filters.max_faithfulness === "number")
    searchParams.max_faithfulness = filters.max_faithfulness;
  if (typeof filters.max_latency_ms === "number")
    searchParams.max_latency_ms = filters.max_latency_ms;
  if (filters.sort_by) searchParams.sort_by = filters.sort_by;
  if (filters.cursor) searchParams.cursor = filters.cursor;
  if (typeof filters.limit === "number") searchParams.limit = filters.limit;
  return _api.get("traces", { searchParams }).json<TraceListResponse>();
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return _api.get(`traces/${traceId}`).json<TraceDetailResponse>();
}

// === Phase 5 quality-feedback clients ===

export async function getTimeseries(
  window: "1h" | "24h" | "7d" | "30d" = "24h",
): Promise<TimeseriesResponse> {
  return _api
    .get("traces/timeseries", { searchParams: { window } })
    .json<TimeseriesResponse>();
}

export async function getEvalConfig(): Promise<EvalConfigResponse> {
  return _api.get("admin/eval-config").json<EvalConfigResponse>();
}

// Live queue-health endpoint (Plan 05-03 GET /admin/queue-health). Replaces the
// "static 0 placeholder" gap; the dashboard 5th KpiCard reads queue_size +
// resolved_this_week from this endpoint with a 30s polling interval (FBCK-07).
export async function getQueueHealth(): Promise<QueueHealthResponse> {
  return _api.get("admin/queue-health").json<QueueHealthResponse>();
}

export async function markResolved(
  traceId: string,
): Promise<FeedbackResolveResponse> {
  return _api
    .patch(`feedback/${traceId}/resolved`)
    .json<FeedbackResolveResponse>();
}

// POST /feedback — also accepts diagnosis_tag for Phase 5 FBCK-05 (TraceDetail
// Feedback tab). Mirrors the existing lib/api.ts postFeedback shape but routes
// through the ky client (consolidated retry/timeout policy).
export interface PostFeedbackRequest {
  trace_id: string;
  rating: 1 | -1;
  comment?: string | null;
  diagnosis_tag?: string | null;
}

export interface PostFeedbackResponse {
  id: string;
  created_at: string;
}

export async function postFeedback(
  body: PostFeedbackRequest,
): Promise<PostFeedbackResponse> {
  return _api.post("feedback", { json: body }).json<PostFeedbackResponse>();
}
