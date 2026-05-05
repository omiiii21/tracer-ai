import * as React from "react";
import { ProgressBar } from "@tremor/react";
import type { IngestStatus } from "@/lib/api";

/**
 * Tremor ProgressBar plus a counter row showing
 * `{processed} / {total} docs · {chunks_written} chunks · {elapsed}s elapsed`.
 * Renders inline below the ReindexButton during the `running` state machine
 * stage (Plan 09 UI-SPEC §4.5).
 */
export function IngestProgress({
  status,
}: {
  status: IngestStatus;
}): React.ReactElement {
  // Tick once a second to keep elapsed time fresh while polling at 2s.
  const [now, setNow] = React.useState<number>(() => Date.now());
  React.useEffect(() => {
    if (status.status !== "running") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [status.status]);

  const elapsedSec = status.started_at
    ? Math.max(0, Math.round((now - new Date(status.started_at).getTime()) / 1000))
    : 0;

  const docsLabel =
    typeof status.docs_total === "number"
      ? `${status.docs_processed} / ${status.docs_total} docs`
      : `${status.docs_processed} docs`;

  const chunksLabel = `${status.chunks_written.toLocaleString()} chunks`;

  return (
    <div data-testid="ingest-progress" className="space-y-1">
      <ProgressBar
        value={Math.max(0, Math.min(100, status.progress * 100))}
        color="amber"
      />
      <p className="text-xs text-muted-foreground">
        {docsLabel} · {chunksLabel} · {elapsedSec}s elapsed
      </p>
    </div>
  );
}
