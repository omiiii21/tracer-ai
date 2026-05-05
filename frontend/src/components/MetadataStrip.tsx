import { Link } from "react-router-dom";
import { ThumbsFeedback } from "@/components/ThumbsFeedback";

export interface MetadataStripProps {
  traceId: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

/**
 * Bottom-of-message badge strip. Format strings are load-bearing —
 * CHAT-03 e2e regex assertions require:
 *   /\d+\s*ms/                  -> e.g. "2810ms"
 *   /\d+\s*→\s*\d+\s*tok/       -> e.g. "1240→96 tok"
 *   /\$\d+\.\d+/                -> e.g. "$0.0043"
 */
export function MetadataStrip({
  traceId,
  latency_ms,
  input_tokens,
  output_tokens,
  estimated_cost_usd,
}: MetadataStripProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 pt-2 border-t border-border text-xs text-muted-foreground">
      <span>{latency_ms}ms</span>
      <span aria-hidden="true">·</span>
      <span>
        {input_tokens}→{output_tokens} tok
      </span>
      <span aria-hidden="true">·</span>
      <span>${estimated_cost_usd.toFixed(4)}</span>
      <ThumbsFeedback traceId={traceId} />
      <Link
        to={`/traces/${traceId}`}
        className="hover:underline ml-auto"
      >
        trace ↗
        <span className="sr-only"> View full trace for this answer</span>
      </Link>
    </div>
  );
}
