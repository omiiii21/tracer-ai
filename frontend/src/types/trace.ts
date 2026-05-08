// TS mirrors of tracer_ai/api/schemas.py trace shapes (Phase 4 EXPL-01 / EXPL-02 +
// Phase 5 quality-feedback extensions).
// Source-of-truth at runtime is the Pydantic schemas; this file mirrors them
// for the TanStack Query useQuery generic. Keep in sync with docs/api.md §4 + §5
// + Phase 5 §6/§7/§8 (timeseries, admin/eval-config, admin/queue-health, PATCH resolved).

export interface TraceListItem {
  trace_id: string;
  started_at: string;       // ISO8601
  query_text: string;
  latency_ms: number;
  estimated_cost_usd: number;
  faithfulness: number | null;
  feedback_rating: 1 | -1 | null;
}

export interface TraceListResponse {
  items: TraceListItem[];
  next_cursor: string | null;
}

export interface SpanInDetail {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  started_at: string;            // ISO8601
  ended_at: string | null;
  attrs: Record<string, unknown>;
}

export interface SpanPayload {
  payload: Record<string, unknown>;
}

export interface TraceDetailResponse {
  trace: TraceListItem;
  spans: SpanInDetail[];
  payloads: Record<string, SpanPayload>;   // keyed by span_id (string)
  // Phase 5 FBCK-05 — DETAIL-ONLY field (NOT on TraceListItem). Sourced from the
  // most-recent (MAX(created_at)) feedback row for the trace_id; backend adds
  // this in a follow-up wiring step. Field is optional so the UI degrades
  // gracefully (Select shows "— none —") when the backend hasn't surfaced it yet.
  diagnosis_tag?: string | null;
}

export interface TraceListFilters {
  query?: string;
  since?: string;                // ISO8601
  until?: string;
  feedback?: "up" | "down";
  min_faithfulness?: number;     // [0.0, 1.0]
  max_faithfulness?: number;     // [0.0, 1.0]   — Phase 5 FBCK-03 (Judge-flagged tab)
  max_latency_ms?: number;
  sort_by?: "created_at_desc" | "faithfulness_asc";  // Phase 5 FBCK-06
  cursor?: string;
  limit?: number;
}

// === Phase 5 quality-feedback types ===

export interface TimeseriesBucket {
  bucket_start: string;                 // ISO 8601
  latency_p50: number | null;
  latency_p95: number | null;
  cost_sum: number;
  faithfulness_mean: number | null;     // null when no eval-scored traces in bucket
  feedback_down_ratio: number | null;   // null when no rated traces in bucket
  request_count: number;
}

export interface TimeseriesResponse {
  window: "1h" | "24h" | "7d" | "30d";
  buckets: TimeseriesBucket[];
}

export interface EvalConfigResponse {
  threshold: number;                    // [0.0, 1.0] BAD_ANSWER_FAITHFULNESS_THRESHOLD
  judge_prompt_version: string;
  judge_model: string;
  calibration_date: string | null;
}

export interface FeedbackResolveResponse {
  trace_id: string;
  resolved_at: string;                  // ISO 8601
  rows_updated: number;
}

export interface QueueHealthResponse {
  queue_size: number;            // count of unresolved thumbs-down feedback rows
  resolved_this_week: number;    // count of feedback rows resolved in last 7 days
}
