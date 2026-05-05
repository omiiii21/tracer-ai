import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Callout } from "@tremor/react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CorpusCards } from "@/components/CorpusCards";
import { DocList } from "@/components/DocList";
import { ReindexButton } from "@/components/ReindexButton";
import { UrlIngestForm } from "@/components/UrlIngestForm";
import { ChunkingConfigForm } from "@/components/ChunkingConfigForm";
import { getCorpus, type CorpusState } from "@/lib/api";

/**
 * Admin orchestrator — fetches corpus state via TanStack Query, renders the
 * 4 KPI cards + DocList + action panel (ReindexButton / UrlIngestForm /
 * ChunkingConfigForm). Empty-corpus path surfaces an amber Tremor Callout.
 * (Plan 09 ADMN-01..04)
 */
export function Admin(): React.ReactElement {
  const queryClient = useQueryClient();
  const corpusQuery = useQuery<CorpusState, Error>({
    queryKey: ["corpus"],
    queryFn: getCorpus,
    staleTime: 30_000,
  });

  if (corpusQuery.isLoading) {
    return (
      <div className="max-w-7xl mx-auto p-8 space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Corpus</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (corpusQuery.isError || !corpusQuery.data) {
    return (
      <div className="max-w-7xl mx-auto p-8 space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Corpus</h1>
        <Card className="border-rose-300 bg-rose-50">
          <CardHeader>
            <CardTitle className="text-base text-rose-700">
              Failed to load corpus state
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-rose-700">
              {corpusQuery.error?.message ?? "Unknown error"}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                void queryClient.invalidateQueries({ queryKey: ["corpus"] })
              }
            >
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const corpus = corpusQuery.data;
  const isEmpty = corpus.chunk_count === 0;

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Corpus</h1>

      {isEmpty ? (
        <Callout
          title="No corpus yet"
          icon={AlertTriangle}
          color="amber"
          data-testid="empty-corpus-banner"
        >
          Run <code className="font-mono text-xs">tracer-ai ingest --source claude-docs</code> from
          the CLI, or click <strong>Re-index corpus</strong> to ingest the default
          Claude docs source.
        </Callout>
      ) : null}

      <CorpusCards corpus={corpus} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <DocList docs={corpus.docs} chunkCount={corpus.chunk_count} />
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <ReindexButton />
              <UrlIngestForm />
              <ChunkingConfigForm initial={corpus.chunking_config} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
