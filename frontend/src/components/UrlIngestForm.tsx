import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/use-toast";
import { postIngest } from "@/lib/api";

const URL_REGEX = /^https?:\/\//;

/**
 * URL-list ingest form. Each non-empty line is validated client-side against
 * `^https?://`. On submit, posts /admin/ingest with `{urls}`. Server-side
 * Pydantic re-validates (Plan 01) — defense in depth.
 */
export function UrlIngestForm(): React.ReactElement {
  const [text, setText] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const ingestMutation = useMutation({
    mutationFn: (urls: string[]) => postIngest({ urls }),
    onSuccess: () => {
      toast({
        title: "URL ingest queued",
        description: "Watch the re-index progress to see when it completes.",
      });
      setText("");
    },
    onError: (err: Error) => {
      setError(err.message);
      toast({
        title: "URL ingest failed",
        description: err.message,
        variant: "destructive",
      });
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const lines = text.split("\n");
    const urls: string[] = [];
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i].trim();
      if (line === "") continue;
      if (!URL_REGEX.test(line)) {
        setError(`Line ${i + 1}: not a URL`);
        return;
      }
      urls.push(line);
    }
    if (urls.length === 0) {
      setError("Enter at least one URL");
      return;
    }

    ingestMutation.mutate(urls);
  }

  return (
    <form onSubmit={handleSubmit} data-testid="url-ingest-form" className="space-y-2">
      <Label htmlFor="ingest-urls">Ingest URLs</Label>
      <Textarea
        id="ingest-urls"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="https://docs.anthropic.com/en/api/messages&#10;https://docs.anthropic.com/en/api/auth"
        rows={4}
        className="font-mono text-xs"
        aria-describedby={error ? "url-ingest-error" : undefined}
      />
      <p className="text-xs text-muted-foreground">
        One URL per line. Must start with http:// or https://.
      </p>
      {error ? (
        <p
          id="url-ingest-error"
          className="text-xs text-rose-600"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      <Button
        type="submit"
        variant="outline"
        size="sm"
        disabled={!text.trim() || ingestMutation.isPending}
      >
        {ingestMutation.isPending ? "Submitting…" : "Add URLs"}
      </Button>
    </form>
  );
}
