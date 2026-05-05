import { sseStream } from "./sse";

// === POST /chat — text/event-stream ===

export interface ChatRequest {
  question: string;
  thread_id?: string;
}

export interface Citation {
  idx: number;
  doc_id: string;
  doc_section: string;
  section_title: string;
  source_url: string;
  content: string;
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

// === Admin types (Plan 09 will use; declared here for one source of truth) ===

export interface CorpusDoc {
  id: string;
  doc_section: string;
  source_url: string;
  chunk_count: number;
  ingested_at: string;
}

export interface CorpusState {
  doc_count: number;
  chunk_count: number;
  embedding_model: string;
  embedding_model_version: string;
  last_indexed_at: string | null;
  docs: CorpusDoc[];
  chunking_config?: {
    chunk_size: number;
    overlap: number;
  };
}

export type IngestRequest = { source: "claude-docs" } | { urls: string[] };

export interface IngestResponse {
  ingest_job_id: string;
  status: "queued";
}

export interface IngestStatus {
  status: "queued" | "running" | "succeeded" | "failed";
  started_at: string | null;
  finished_at: string | null;
  docs_processed: number;
  docs_total: number;
  chunks_written: number;
  progress: number;
  error?: string;
}

export interface ChunkingConfigPatch {
  chunk_size: number;
  overlap: number;
}
