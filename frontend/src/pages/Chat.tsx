import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  MessageList,
  type ChatMessage,
} from "@/components/MessageList";
import { MessageInput } from "@/components/MessageInput";
import { postChat, type SSEEvent } from "@/lib/api";

const EXAMPLES = [
  "How does prompt caching work?",
  "What is tool use?",
  "Show me a streaming example.",
];

function genId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Chat page — owns local Message[] state, opens an SSE connection to
 * POST /chat on submit, mutates the trailing assistant message on each
 * `event: token` frame, and finalizes on `event: final`. Submitting a
 * second question after the first response completes appends a new
 * user+assistant pair (multi-turn within session — CHAT-01).
 */
export function Chat() {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = React.useState(false);

  // Track the in-flight controller so unmount or new submission can abort.
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const submit = React.useCallback(async (question: string) => {
    if (streaming || !question.trim()) return;

    const userId = genId();
    const assistantId = genId();
    setMessages((prev) => [
      ...prev,
      { role: "user", id: userId, content: question },
      {
        role: "assistant",
        id: assistantId,
        content: "",
        streaming: true,
      },
    ]);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const stream = postChat({ question }, controller.signal);
      for await (const frame of stream as AsyncIterable<SSEEvent>) {
        if (frame.event === "token") {
          const token = frame.data.text;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && m.role === "assistant"
                ? { ...m, content: m.content + token }
                : m,
            ),
          );
        } else if (frame.event === "final") {
          const final = frame.data;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && m.role === "assistant"
                ? {
                    ...m,
                    streaming: false,
                    trace_id: final.trace_id,
                    cited_chunks: final.cited_chunks,
                    metadata: {
                      latency_ms: final.latency_ms,
                      input_tokens: final.input_tokens,
                      output_tokens: final.output_tokens,
                      estimated_cost_usd: final.estimated_cost_usd,
                    },
                  }
                : m,
            ),
          );
        } else if (frame.event === "error") {
          const message = frame.data.message ?? "Unknown error";
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && m.role === "assistant"
                ? { ...m, streaming: false, error: message }
                : m,
            ),
          );
        }
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Network error — please retry.";
      // If aborted, leave message as-is (component is unmounting).
      if (controller.signal.aborted) return;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.role === "assistant"
            ? { ...m, streaming: false, error: message }
            : m,
        ),
      );
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [streaming]);

  function handleRetry(messageId: string) {
    // Find the last user message before the failed assistant message and re-submit.
    const idx = messages.findIndex((m) => m.id === messageId);
    if (idx < 1) return;
    let userIdx = idx - 1;
    while (userIdx >= 0 && messages[userIdx].role !== "user") {
      userIdx -= 1;
    }
    if (userIdx < 0) return;
    const lastQ = messages[userIdx].content;
    // Remove the failed bubble + its preceding user (we'll re-append).
    setMessages((prev) =>
      prev.filter((m) => m.id !== messageId && m.id !== messages[userIdx].id),
    );
    void submit(lastQ);
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-16 px-4">
          <h1 className="text-2xl font-semibold tracking-tight mb-2">
            Ask a question about the Claude API or Agent SDK.
          </h1>
          <p className="text-sm text-muted-foreground mb-6">
            Powered by retrieval over the official Claude API + Agent SDK
            docs.
          </p>
          <div className="flex flex-wrap gap-2 justify-center max-w-2xl">
            {EXAMPLES.map((q) => (
              <Button
                key={q}
                variant="outline"
                size="sm"
                onClick={() => void submit(q)}
                disabled={streaming}
              >
                {q}
              </Button>
            ))}
          </div>
        </div>
      ) : (
        <MessageList messages={messages} onRetry={handleRetry} />
      )}
      <MessageInput
        onSubmit={(text) => void submit(text)}
        disabled={streaming}
      />
    </div>
  );
}
