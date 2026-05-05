import * as React from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

interface MessageInputProps {
  onSubmit: (text: string) => void;
  disabled?: boolean;
}

/**
 * Sticky-bottom chat input form. Enter sends; Shift+Enter inserts
 * a newline. Send button label flips to "Streaming…" while disabled
 * is true (i.e., a response is in flight).
 */
export function MessageInput({
  onSubmit,
  disabled = false,
}: MessageInputProps) {
  const [input, setInput] = React.useState("");

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setInput("");
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="sticky bottom-0 bg-background border-t border-border p-4"
    >
      <div className="flex gap-2 items-end max-w-4xl mx-auto">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question…"
          rows={2}
          className="resize-none flex-1"
          disabled={disabled}
          aria-label="Ask a question about the Claude API"
        />
        <Button
          type="submit"
          disabled={disabled || !input.trim()}
          className="self-end"
        >
          {disabled ? "Streaming…" : "Send"}
        </Button>
      </div>
    </form>
  );
}
