import * as React from "react";
import {
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Title,
} from "@tremor/react";
import { ExternalLink } from "lucide-react";
import { formatRelative } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { DocSummary } from "@/lib/api";

/**
 * Document table — Tremor Table; default sort by doc.id ascending. When the
 * docs list is empty AND chunk_count is 0, render Skeleton rows + a centered
 * "No documents indexed yet." message (Plan 09 UI-SPEC §4.4 / §4.8).
 */
export function DocList({
  docs,
  chunkCount,
}: {
  docs: DocSummary[];
  chunkCount: number;
}): React.ReactElement {
  const sortedDocs = React.useMemo(
    () => [...docs].sort((a, b) => a.id.localeCompare(b.id)),
    [docs],
  );

  const isEmptyCorpus = sortedDocs.length === 0 && chunkCount === 0;

  return (
    <Card data-testid="doc-list">
      <Title>Documents</Title>
      {isEmptyCorpus ? (
        <div className="mt-4 space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
          <p className="text-sm text-muted-foreground text-center pt-2">
            No documents indexed yet.
          </p>
        </div>
      ) : (
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Doc ID</TableHeaderCell>
              <TableHeaderCell>Section</TableHeaderCell>
              <TableHeaderCell className="text-right">Chunks</TableHeaderCell>
              <TableHeaderCell>Source</TableHeaderCell>
              <TableHeaderCell>Last ingested</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedDocs.map((doc) => (
              <TableRow key={doc.id} data-testid="doc-row">
                <TableCell className="font-mono text-xs">{doc.id}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{doc.doc_section}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  {doc.chunk_count.toLocaleString()}
                </TableCell>
                <TableCell>
                  {doc.source_url ? (
                    <a
                      href={doc.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline truncate max-w-[24ch]"
                      title={doc.source_url}
                    >
                      <ExternalLink className="h-3 w-3 shrink-0" />
                      <span className="truncate">{doc.source_url}</span>
                    </a>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {doc.ingested_at
                    ? formatRelative(new Date(doc.ingested_at), new Date())
                    : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
