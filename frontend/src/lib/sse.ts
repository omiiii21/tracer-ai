/**
 * Async generator over a fetch ReadableStream of Server-Sent Events.
 *
 * SSE wire format: each frame is separated by a blank line (\n\n);
 * each frame contains an "event: NAME" line and a "data: JSON" line.
 *
 * The browser native EventSource only supports GET; tracer-ai posts
 * the chat query in a JSON body, so we hand-roll the parser per
 * Phase 3 RESEARCH §4 / Pitfall 7.5.
 *
 * Example frame:
 *   event: token
 *   data: {"text": "hello"}
 *
 *   event: final
 *   data: {"trace_id": "...", ...}
 */
export async function* sseStream(
  url: string,
  init: RequestInit,
): AsyncGenerator<{ event: string; data: unknown }> {
  const res = await fetch(url, {
    ...init,
    headers: { ...(init.headers ?? {}), Accept: "text/event-stream" },
  });
  if (!res.ok) {
    throw new Error(`sseStream: HTTP ${res.status} ${res.statusText}`);
  }
  if (!res.body) throw new Error("sseStream: response has no body");
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      if (!frame.trim()) continue;
      const eventMatch = frame.match(/^event:\s*(.+)$/m);
      const dataMatch = frame.match(/^data:\s*(.+)$/m);
      const event = eventMatch ? eventMatch[1] : "message";
      const dataRaw = dataMatch ? dataMatch[1] : "{}";
      let data: unknown;
      try {
        data = JSON.parse(dataRaw);
      } catch {
        data = dataRaw;
      }
      yield { event, data };
    }
  }
}
