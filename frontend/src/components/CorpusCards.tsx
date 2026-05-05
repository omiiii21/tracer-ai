import * as React from "react";
import { Card, Metric, Text, Title } from "@tremor/react";
import { format, formatRelative } from "date-fns";
import type { CorpusState } from "@/lib/api";

/**
 * Four KPI cards summarizing corpus state: documents, chunks, embedding model,
 * last indexed. Renders the Plan 09 ADMN-01 contract surface — labels are
 * load-bearing for the e2e test (test_admin_renders_kpi_cards).
 */
export function CorpusCards({
  corpus,
}: {
  corpus: CorpusState;
}): React.ReactElement {
  const lastIndexedAt = corpus.last_indexed_at
    ? new Date(corpus.last_indexed_at)
    : null;

  return (
    <div
      data-testid="corpus-cards"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
    >
      <Card>
        <Title>DOCUMENTS</Title>
        <Metric>{corpus.doc_count}</Metric>
        <Text>
          {corpus.doc_count === 0
            ? "no documents yet — run re-index"
            : "documents indexed"}
        </Text>
      </Card>

      <Card>
        <Title>CHUNKS</Title>
        <Metric>{corpus.chunk_count.toLocaleString()}</Metric>
        <Text>{corpus.chunk_count === 0 ? "—" : "chunks"}</Text>
      </Card>

      <Card>
        <Title>EMBEDDING MODEL</Title>
        <Metric className="text-base">
          {corpus.embedding_model || "—"}
        </Metric>
        <Text>{corpus.embedding_model_version || "—"}</Text>
      </Card>

      <Card>
        <Title>LAST INDEXED</Title>
        <Metric>
          {lastIndexedAt
            ? formatRelative(lastIndexedAt, new Date())
            : "never indexed"}
        </Metric>
        <Text>{lastIndexedAt ? format(lastIndexedAt, "PPpp") : ""}</Text>
      </Card>
    </div>
  );
}
