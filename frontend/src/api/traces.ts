// frontend/src/api/traces.ts
// Typed clients for GET /traces + GET /traces/{trace_id} (Phase 4 EXPL-01 / EXPL-02).
// Backend endpoints from docs/api.md §4 + §5; runtime contract enforced by Pydantic
// strict mode (extra="forbid").

import ky from "ky";
import type {
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
  if (typeof filters.max_latency_ms === "number")
    searchParams.max_latency_ms = filters.max_latency_ms;
  if (filters.cursor) searchParams.cursor = filters.cursor;
  return _api.get("traces", { searchParams }).json<TraceListResponse>();
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return _api.get(`traces/${traceId}`).json<TraceDetailResponse>();
}
