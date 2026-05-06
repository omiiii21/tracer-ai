import * as React from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { cn } from "@/lib/utils";
import type { Citation as CitationType } from "@/lib/api";

/**
 * Inline `[N]` superscript marker — links to the corresponding
 * accordion-expanded chunk via fragment id `cite-N`.
 */
export function Citation({ idx }: { idx: number }) {
  return (
    <sup>
      <a
        href={`#cite-${idx}`}
        className="text-blue-600 hover:underline px-0.5"
        aria-label={`Citation ${idx}`}
      >
        [{idx}]
      </a>
    </sup>
  );
}

interface CitationAccordionProps {
  chunks: CitationType[];
  className?: string;
}

/**
 * Expandable accordion listing every cited chunk with section_title,
 * score, text, and doc_url click-through.
 */
export const CitationAccordion = React.forwardRef<
  HTMLDivElement,
  CitationAccordionProps
>(({ chunks, className }, ref) => {
  if (!chunks || chunks.length === 0) return null;
  return (
    <div ref={ref} className={cn("mt-3", className)}>
      <Accordion
        type="single"
        collapsible
        className="border-t border-border pt-2"
      >
        <AccordionItem value="sources" className="border-b-0">
          <AccordionTrigger className="text-xs font-medium uppercase tracking-wide">
            Sources ({chunks.length})
          </AccordionTrigger>
          <AccordionContent>
            {chunks.map((c) => (
              <div
                id={`cite-${c.idx}`}
                key={c.idx}
                className="mb-3 p-3 bg-muted rounded border border-border"
              >
                <div className="text-xs font-medium mb-1">
                  [{c.idx}] {c.section_title} · {c.score.toFixed(2)}
                </div>
                <pre className="font-mono text-xs whitespace-pre-wrap text-muted-foreground">
                  {c.text}
                </pre>
                {c.doc_url && (
                  <a
                    href={c.doc_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-blue-600 hover:underline mt-1 inline-block"
                  >
                    ↗ {c.doc_url}
                  </a>
                )}
              </div>
            ))}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
});
CitationAccordion.displayName = "CitationAccordion";
