import { sseStream } from "./sse";

// === POST /chat — text/event-stream ===

export interface ChatRequest {
  question: string;
  thread_id?: string;
}

export interface Citation {
  idx: number;
  doc_url: string;
  section_title: string;
  text: string;
  score: number;
}

export interface ChatFinal {
  trace_id: string;
  cited_chunks: Citation[];
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export type SSEEvent =
  | { event: "token"; data: { text: string } }
  | { event: "final"; data: ChatFinal }
  | { event: "error"; data: { message: string } };

/**
 * POST /chat — yields SSEEvent objects parsed from the text/event-stream
 * response. The backend emits `event: token` frames followed by exactly one
 * `event: final` frame; on server-side error, an `event: error` frame is
 * emitted.
 */
export async function* postChat(
  req: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  for await (const frame of sseStream("/chat", {
    method: "POST",
    body: JSON.stringify(req),
    headers: { "Content-Type": "application/json" },
    signal,
  })) {
    yield frame as SSEEvent;
  }
}

// === POST /feedback ===

export interface FeedbackRequest {
  trace_id: string;
  rating: 1 | -1;
  comment?: string | null;
}

export interface FeedbackResponse {
  id: string;
  created_at: string;
}

export async function postFeedback(
  req: FeedbackRequest,
): Promise<FeedbackResponse> {
  const res = await fetch("/feedback", {
    method: "POST",
    body: JSON.stringify(req),
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`postFeedback failed: ${res.status}`);
  }
  return (await res.json()) as FeedbackResponse;
}

// === Admin types (consumed by /admin Plan 09 page) ===

export interface DocSummary {
  id: string;
  doc_section: string;
  source_url: string;
  chunk_count: number;
  ingested_at: string;
}

// Back-compat alias — Plan 08 introduced this name; Plan 09 uses DocSummary.
export type CorpusDoc = DocSummary;

export interface ChunkingConfig {
  chunk_size: number;
  overlap: number;
}

export interface CorpusState {
  doc_count: number;
  chunk_count: number;
  embedding_model: string;
  embedding_model_version: string;
  last_indexed_at: string | null;
  docs: DocSummary[];
  chunking_config?: ChunkingConfig;
}

export type IngestRequest = { source: "claude-docs" } | { urls: string[] };

export interface IngestResponse {
  ingest_job_id: string;
  status: "queued";
}

export interface IngestStatus {
  ingest_job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  started_at: string | null;
  finished_at: string | null;
  docs_processed: number;
  docs_total: number | null;
  chunks_written: number;
  progress: number;
  error?: string;
}

export interface ChunkingConfigPatch {
  chunk_size: number;
  overlap: number;
}

// === Admin endpoint wrappers (Plan 09) ===

export async function getCorpus(): Promise<CorpusState> {
  const r = await fetch("/admin/corpus");
  if (!r.ok) throw new Error(`getCorpus failed: ${r.status}`);
  return (await r.json()) as CorpusState;
}

export async function postIngest(req: IngestRequest): Promise<IngestResponse> {
  const r = await fetch("/admin/ingest", {
    method: "POST",
    body: JSON.stringify(req),
    headers: { "Content-Type": "application/json" },
  });
  if (r.status === 409) {
    throw new Error("Ingest already in progress");
  }
  if (!r.ok) throw new Error(`postIngest failed: ${r.status}`);
  return (await r.json()) as IngestResponse;
}

export async function getIngestStatus(jobId: string): Promise<IngestStatus> {
  const r = await fetch(`/admin/ingest/${jobId}`);
  if (!r.ok) throw new Error(`getIngestStatus failed: ${r.status}`);
  return (await r.json()) as IngestStatus;
}

export async function patchChunkingConfig(
  cfg: ChunkingConfig,
): Promise<ChunkingConfig> {
  const r = await fetch("/admin/chunking-config", {
    method: "PATCH",
    body: JSON.stringify(cfg),
    headers: { "Content-Type": "application/json" },
  });
  if (!r.ok) throw new Error(`patchChunkingConfig failed: ${r.status}`);
  return (await r.json()) as ChunkingConfig;
}
