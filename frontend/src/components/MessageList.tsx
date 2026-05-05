import * as React from "react";
import { MessageBubble } from "@/components/MessageBubble";
import type { Citation as CitationType } from "@/lib/api";
import { cn } from "@/lib/utils";

export type ChatMessage =
  | { role: "user"; id: string; content: string }
  | {
      role: "assistant";
      id: string;
      content: string;
      streaming: boolean;
      trace_id?: string;
      cited_chunks?: CitationType[];
      metadata?: {
        latency_ms: number;
        input_tokens: number;
        output_tokens: number;
        estimated_cost_usd: number;
      };
      error?: string;
    };

interface MessageListProps {
  messages: ChatMessage[];
  onRetry?: (messageId: string) => void;
  className?: string;
}

/**
 * Scrollable region of chat bubbles. Auto-scrolls to bottom when
 * content updates during streaming, and on every new message.
 */
export function MessageList({
  messages,
  onRetry,
  className,
}: MessageListProps) {
  const bottomRef = React.useRef<HTMLDivElement>(null);

  // Aggregate streamed content length so the effect runs on each token append.
  const totalContentLen = messages.reduce((acc, m) => acc + m.content.length, 0);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, totalContentLen]);

  return (
    <div
      role="log"
      aria-label="Chat history"
      className={cn(
        "flex-1 overflow-y-auto px-2 py-6 max-w-4xl mx-auto w-full",
        className,
      )}
    >
      {messages.map((m) => {
        if (m.role === "user") {
          return (
            <MessageBubble
              key={m.id}
              role="user"
              content={m.content}
            />
          );
        }
        return (
          <MessageBubble
            key={m.id}
            role="assistant"
            content={m.content}
            streaming={m.streaming}
            cited_chunks={m.cited_chunks}
            metadata={m.metadata}
            trace_id={m.trace_id}
            error={m.error}
            onRetry={onRetry ? () => onRetry(m.id) : undefined}
          />
        );
      })}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  );
}
