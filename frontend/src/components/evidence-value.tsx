"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * Renders a dimension/evidence value the ONE way this is allowed to be
 * rendered anywhere in the app (invariant 1, milestone5_plan.md §3): a
 * `null` is "no evidence recorded," never coerced to 0 — a dash with a
 * tooltip, never a bare `{value ?? 0}`. No other component in this
 * codebase should format a nullable evidence number directly; route it
 * through here so the convention can't drift page to page.
 */
export function EvidenceValue({
  value,
  digits = 3,
  className,
}: {
  value: number | null | undefined;
  digits?: number;
  className?: string;
}) {
  if (value === null || value === undefined) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn("font-mono text-muted-foreground/70", className)} aria-label="No evidence recorded">
            —
          </span>
        </TooltipTrigger>
        <TooltipContent>No evidence recorded for this category (not the same as a weak score).</TooltipContent>
      </Tooltip>
    );
  }
  return <span className={cn("font-mono tabular-nums", className)}>{value.toFixed(digits)}</span>;
}
