import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/use-toast";
import { patchChunkingConfig, type ChunkingConfig } from "@/lib/api";

/**
 * PATCH /admin/chunking-config form. Two number inputs (chunk_size 100..4000,
 * overlap 0..500). Initial values are derived from corpus.chunking_config or
 * fall back to 900/100. On success: success toast + invalidates corpus query.
 */
export function ChunkingConfigForm({
  initial,
}: {
  initial?: ChunkingConfig;
}): React.ReactElement {
  const queryClient = useQueryClient();
  const [chunkSize, setChunkSize] = React.useState<number>(
    initial?.chunk_size ?? 900,
  );
  const [overlap, setOverlap] = React.useState<number>(initial?.overlap ?? 100);
  const [fieldError, setFieldError] = React.useState<string | null>(null);

  // Sync if upstream corpus changes.
  React.useEffect(() => {
    if (initial) {
      setChunkSize(initial.chunk_size);
      setOverlap(initial.overlap);
    }
  }, [initial]);

  const mutation = useMutation({
    mutationFn: (cfg: ChunkingConfig) => patchChunkingConfig(cfg),
    onSuccess: () => {
      toast({
        title: "Chunking settings saved.",
        description: "They'll apply on the next re-index.",
      });
      void queryClient.invalidateQueries({ queryKey: ["corpus"] });
    },
    onError: (err: Error) => {
      setFieldError(err.message);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldError(null);
    if (
      Number.isNaN(chunkSize) ||
      chunkSize < 100 ||
      chunkSize > 4000
    ) {
      setFieldError("chunk_size must be between 100 and 4000");
      return;
    }
    if (Number.isNaN(overlap) || overlap < 0 || overlap > 500) {
      setFieldError("overlap must be between 0 and 500");
      return;
    }
    mutation.mutate({ chunk_size: chunkSize, overlap });
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="chunking-config-form"
      className="space-y-3"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Chunking
      </p>
      <div className="space-y-2">
        <Label htmlFor="chunk-size">chunk_size</Label>
        <Input
          id="chunk-size"
          type="number"
          min={100}
          max={4000}
          step={50}
          value={chunkSize}
          onChange={(e) => setChunkSize(Number(e.target.value))}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="overlap">overlap</Label>
        <Input
          id="overlap"
          type="number"
          min={0}
          max={500}
          step={10}
          value={overlap}
          onChange={(e) => setOverlap(Number(e.target.value))}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        New values apply on the next re-index.
      </p>
      {fieldError ? (
        <p className="text-xs text-rose-600" role="alert">
          {fieldError}
        </p>
      ) : null}
      <Button
        type="submit"
        variant="outline"
        size="sm"
        disabled={mutation.isPending}
      >
        {mutation.isPending ? "Saving…" : "Save settings"}
      </Button>
    </form>
  );
}
