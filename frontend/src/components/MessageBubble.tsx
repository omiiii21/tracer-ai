import * as React from "react";
import { cn } from "@/lib/utils";
import { CitationAccordion } from "@/components/Citation";
import {
  MetadataStrip,
  type MetadataStripProps,
} from "@/components/MetadataStrip";
import type { Citation as CitationType } from "@/lib/api";

export interface MessageBubbleProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "content" | "role"> {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  cited_chunks?: CitationType[];
  metadata?: Omit<MetadataStripProps, "traceId">;
  trace_id?: string;
  error?: string;
  onRetry?: () => void;
}

/**
 * Renders a single chat bubble. User bubbles right-aligned with
 * primary background; assistant bubbles left-aligned with card
 * background, accordion + metadata strip rendered after streaming
 * completes.
 *
 * While `streaming === true`, an animated cursor `▋` is appended
 * and the bubble has aria-live="polite" so assistive tech announces
 * the streamed text. The cursor is removed when streaming flips to
 * false to avoid re-announcement.
 */
export const MessageBubble = React.forwardRef<
  HTMLDivElement,
  MessageBubbleProps
>(
  (
    {
      className,
      role,
      content,
      streaming = false,
      cited_chunks,
      metadata,
      trace_id,
      error,
      onRetry,
      ...props
    },
    ref,
  ) => {
    if (role === "user") {
      return (
        <div
          ref={ref}
          className={cn("flex justify-end mb-4", className)}
          data-role="user"
          {...props}
        >
          <div className="bg-primary text-primary-foreground rounded-lg px-4 py-2 max-w-[80%] text-sm whitespace-pre-wrap break-words">
            {content}
          </div>
        </div>
      );
    }

    const isError = !!error;

    return (
      <div
        ref={ref}
        role="article"
        aria-live={streaming ? "polite" : undefined}
        className={cn("flex justify-start mb-6", className)}
        data-role="assistant"
        data-streaming={streaming ? "true" : "false"}
        {...props}
      >
        <div
          className={cn(
            "rounded-lg px-4 py-3 max-w-[85%] w-full text-sm border",
            isError
              ? "border-rose-300 bg-rose-50"
              : "bg-card border-border",
          )}
        >
          <div className="prose prose-sm prose-zinc max-w-none whitespace-pre-wrap break-words">
            <span data-testid="assistant-content">{content}</span>
            {streaming && (
              <span
                aria-hidden="true"
                className="inline-block ml-0.5 motion-safe:animate-pulse"
              >
                ▋
              </span>
            )}
          </div>
          {isError && (
            <div className="mt-3 flex items-center gap-2">
              <p className="text-xs text-rose-700">{error}</p>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="text-xs font-medium text-rose-700 hover:underline"
                >
                  Retry
                </button>
              )}
            </div>
          )}
          {!streaming && cited_chunks && cited_chunks.length > 0 && (
            <CitationAccordion chunks={cited_chunks} />
          )}
          {!streaming && metadata && trace_id && (
            <MetadataStrip traceId={trace_id} {...metadata} />
          )}
        </div>
      </div>
    );
  },
);
MessageBubble.displayName = "MessageBubble";
