"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DIMENSION_COLOR_VAR, DIMENSION_ORDER, type DimensionKey } from "@/lib/dimensions";
import { cn } from "@/lib/utils";

export interface ScoreStripSegment {
  key: DimensionKey;
  label: string;
  /** contrib__<dimension> — this segment's exact share of the total. */
  value: number;
}

/**
 * The app's signature element (frontend-design skill, milestone5_plan.md
 * §2.4): a horizontal stack of the exact per-dimension contributions that
 * SUM to the score (`WeightedBaseline.explain` — "contributions sum
 * exactly to the score, no approximation," models/baseline.py). Rendered
 * next to every score in the app, at three sizes, so the product's core
 * claim — a prioritization score is not a black box, it is five numbers
 * added together — is something you SEE, not just read in a limitations
 * panel. Segments missing from `segments` (a dimension with no evidence)
 * simply contribute no width; this is a stacked bar, not a percentage
 * chart, so absence reads as absence.
 */
export function ScoreStrip({
  segments,
  size = "md",
  className,
}: {
  segments: ScoreStripSegment[];
  size?: "micro" | "md" | "lg";
  className?: string;
}) {
  const total = segments.reduce((sum, s) => sum + Math.max(s.value, 0), 0);
  const height = size === "micro" ? "h-1.5" : size === "md" ? "h-3" : "h-5";
  const ordered = DIMENSION_ORDER.map((key) => segments.find((s) => s.key === key)).filter(
    (s): s is ScoreStripSegment => s !== undefined,
  );

  return (
    <div
      className={cn("flex w-full overflow-hidden rounded-xs bg-muted", height, className)}
      role="img"
      aria-label={`Score breakdown: ${ordered.map((s) => `${s.label} ${s.value.toFixed(3)}`).join(", ")}`}
    >
      {ordered.map((segment, i) => {
        const widthPct = total > 0 ? (Math.max(segment.value, 0) / total) * 100 : 0;
        if (widthPct <= 0) return null;
        const bar = (
          <div
            key={segment.key}
            className={cn(
              "h-full min-w-px transition-[flex-basis]",
              i > 0 && "border-l border-background/60",
            )}
            style={{ backgroundColor: DIMENSION_COLOR_VAR[segment.key], flexBasis: `${widthPct}%` }}
          />
        );
        if (size === "micro") return bar;
        return (
          <Tooltip key={segment.key}>
            <TooltipTrigger asChild>{bar}</TooltipTrigger>
            <TooltipContent className="font-mono text-xs">
              {segment.label}: {segment.value.toFixed(3)}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
