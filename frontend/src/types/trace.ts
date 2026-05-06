// TS mirrors of tracer_ai/api/schemas.py trace shapes (Phase 4 EXPL-01 / EXPL-02).
// Source-of-truth at runtime is the Pydantic schemas; this file mirrors them
// for the TanStack Query useQuery generic. Keep in sync with docs/api.md §4 + §5.

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
}

export interface TraceListFilters {
  query?: string;
  since?: string;                // ISO8601
  until?: string;
  feedback?: "up" | "down";
  min_faithfulness?: number;     // [0.0, 1.0]
  max_latency_ms?: number;
  cursor?: string;
}
