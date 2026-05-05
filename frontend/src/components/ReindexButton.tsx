import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IngestProgress } from "@/components/IngestProgress";
import { toast } from "@/components/ui/use-toast";
import { postIngest, getIngestStatus, type IngestStatus } from "@/lib/api";

type State = "idle" | "confirming" | "running" | "done" | "error";

const buttonVariant: Record<State, "default" | "destructive"> = {
  idle: "default",
  confirming: "default",
  running: "default",
  done: "default",
  error: "destructive",
};

/**
 * Re-index button driving the idle → confirming (3s) → running → done|error
 * state machine. Polls /admin/ingest/{job_id} every 2s via TanStack Query
 * `refetchInterval: 2000`. On succeeded: invalidates the corpus query and
 * shows a toast. (Plan 09 UI-SPEC §4.5)
 */
export function ReindexButton(): React.ReactElement {
  const queryClient = useQueryClient();
  const [state, setState] = React.useState<State>("idle");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Confirm-state revert timer
  const confirmTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const doneTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearConfirmTimer = () => {
    if (confirmTimerRef.current) {
      clearTimeout(confirmTimerRef.current);
      confirmTimerRef.current = null;
    }
  };

  React.useEffect(() => {
    return () => {
      clearConfirmTimer();
      if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    };
  }, []);

  const ingestMutation = useMutation({
    mutationFn: () => postIngest({ source: "claude-docs" }),
    onSuccess: (resp) => {
      setJobId(resp.ingest_job_id);
      setState("running");
      setErrorMessage(null);
    },
    onError: (err: Error) => {
      setState("error");
      setErrorMessage(err.message);
      toast({
        title: "Re-index failed",
        description: err.message,
        variant: "destructive",
      });
    },
  });

  const statusQuery = useQuery<IngestStatus, Error>({
    queryKey: ["ingest", jobId],
    queryFn: () => getIngestStatus(jobId as string),
    enabled: !!jobId && state === "running",
    refetchInterval: 2000,
  });

  // Drive the state machine off the polling result.
  React.useEffect(() => {
    const data = statusQuery.data;
    if (!data || state !== "running") return;
    if (data.status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: ["corpus"] });
      setState("done");
      toast({
        title: "Re-index complete",
        description: `${data.chunks_written.toLocaleString()} chunks written.`,
      });
      // Re-arm to idle in 3s.
      doneTimerRef.current = setTimeout(() => {
        setState("idle");
        setJobId(null);
      }, 3000);
    } else if (data.status === "failed") {
      setState("error");
      setErrorMessage(data.error ?? "Ingest failed");
      toast({
        title: "Re-index failed",
        description: data.error ?? "Ingest failed",
        variant: "destructive",
      });
    }
  }, [statusQuery.data, state, queryClient]);

  function handleClick() {
    if (state === "idle") {
      setState("confirming");
      clearConfirmTimer();
      confirmTimerRef.current = setTimeout(() => {
        setState((prev) => (prev === "confirming" ? "idle" : prev));
      }, 3000);
      return;
    }
    if (state === "confirming") {
      clearConfirmTimer();
      ingestMutation.mutate();
      return;
    }
    if (state === "error") {
      setState("idle");
      setErrorMessage(null);
      setJobId(null);
      return;
    }
    if (state === "done") {
      setState("idle");
      setJobId(null);
    }
    // running: button is disabled; click is a no-op
  }

  const label: Record<State, string> = {
    idle: "Re-index corpus",
    confirming: "Click again to confirm",
    running: "Indexing…",
    done: "Re-index complete",
    error: "Re-index failed — retry",
  };

  return (
    <div className="space-y-2">
      <Button
        variant={buttonVariant[state]}
        disabled={state === "running"}
        onClick={handleClick}
        data-testid="reindex-button"
        data-state={state}
        className="w-full"
      >
        {state === "running" ? (
          <span className="inline-flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            {label[state]}
          </span>
        ) : (
          label[state]
        )}
      </Button>
      {state === "running" && statusQuery.data ? (
        <IngestProgress status={statusQuery.data} />
      ) : null}
      {state === "error" && errorMessage ? (
        <p className="text-xs text-rose-600">{errorMessage}</p>
      ) : null}
    </div>
  );
}
