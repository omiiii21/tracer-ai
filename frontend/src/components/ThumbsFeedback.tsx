import * as React from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { postFeedback } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ThumbsFeedbackProps {
  traceId: string;
}

export function ThumbsFeedback({ traceId }: ThumbsFeedbackProps) {
  const [selected, setSelected] = React.useState<1 | -1 | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const { toast } = useToast();

  async function handleThumbsUp() {
    if (submitting) return;
    setSubmitting(true);
    try {
      await postFeedback({ trace_id: traceId, rating: 1, comment: null });
      setSelected(1);
      toast({
        title: "Feedback recorded — thanks!",
        variant: "success",
      });
    } catch {
      toast({
        title: "Couldn't record feedback. Please retry.",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  }

  function handleThumbsDownOpen() {
    setComment("");
    setDialogOpen(true);
  }

  async function handleThumbsDownSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      await postFeedback({
        trace_id: traceId,
        rating: -1,
        comment: comment.trim() || null,
      });
      setSelected(-1);
      setDialogOpen(false);
      toast({
        title: "Feedback recorded — thanks!",
        variant: "success",
      });
    } catch {
      toast({
        title: "Couldn't record feedback. Please retry.",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        aria-label="Thumbs up"
        aria-pressed={selected === 1}
        onClick={handleThumbsUp}
        disabled={submitting}
        className={cn(
          "p-1 rounded hover:bg-muted transition-colors",
          selected === 1 && "text-emerald-600",
          submitting && "opacity-50 cursor-not-allowed",
        )}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        aria-label="Thumbs down"
        aria-pressed={selected === -1}
        onClick={handleThumbsDownOpen}
        disabled={submitting}
        className={cn(
          "p-1 rounded hover:bg-muted transition-colors",
          selected === -1 && "text-rose-600",
          submitting && "opacity-50 cursor-not-allowed",
        )}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <form onSubmit={handleThumbsDownSubmit}>
            <DialogHeader>
              <DialogTitle>What went wrong?</DialogTitle>
              <DialogDescription>
                Optional — your comment helps improve retrieval and answers.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-2 my-4">
              <Label htmlFor="feedback-comment">Comment</Label>
              <Textarea
                id="feedback-comment"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                maxLength={1000}
                rows={4}
                placeholder="Tell us what went wrong (optional)…"
              />
              <p className="text-xs text-muted-foreground">
                {comment.length} / 1000
              </p>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Submitting…" : "Submit"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </span>
  );
}
