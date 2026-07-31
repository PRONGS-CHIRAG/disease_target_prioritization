"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * "N of 6 categories," never a bare fraction (invariant 2,
 * milestone5_plan.md §3 — target_ranking.py's comment on
 * `app_evidence_completeness` is explicit that the denominator must travel
 * with the number). Takes the count/total the API already computed
 * (`evidence_completeness_count`/`_total`) rather than re-deriving them
 * from the fraction client-side, so rounding can't disagree with the
 * server.
 */
export function CompletenessBadge({
  count,
  total,
  className,
}: {
  count: number;
  total: number;
  className?: string;
}) {
  const low = count / total < 0.5;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-xs border px-1.5 py-0.5 font-mono text-xs tabular-nums",
            low
              ? "border-muted-foreground/30 text-muted-foreground"
              : "border-border text-foreground",
            className,
          )}
        >
          {count} of {total}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-56">
        Evidence categories with data for this target. A low count means understudied, not
        unpromising (Context.md §32.3) — check which categories are missing before reading it as
        a weak target.
      </TooltipContent>
    </Tooltip>
  );
}
