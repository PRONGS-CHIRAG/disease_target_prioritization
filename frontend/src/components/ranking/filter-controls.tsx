"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export interface RankingFilterValues {
  minGenetics: number;
  druggable: boolean;
  tissue: boolean;
  completeness: number;
  safety: boolean;
}

export function FilterControls({
  values,
  onChange,
  safetyForced,
  evidenceCategoryCount,
}: {
  values: RankingFilterValues;
  onChange: <K extends keyof RankingFilterValues>(key: K, value: RankingFilterValues[K]) => void;
  /** True when the "Safety-first" scenario is active — the checkbox is
   * shown checked and disabled, since a scenario changing a FILTER (not a
   * weight) must stay honest about which is happening
   * (milestone5_plan.md invariant 4). */
  safetyForced: boolean;
  evidenceCategoryCount: number;
}) {
  return (
    <div className="space-y-4 rounded-md border border-border bg-card p-4">
      <h3 className="font-heading text-sm font-semibold">Filters</h3>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-normal text-muted-foreground">
              Minimum genetics evidence
            </Label>
            <span className="font-mono text-xs tabular-nums">{values.minGenetics.toFixed(2)}</span>
          </div>
          <Slider
            value={[values.minGenetics]}
            min={0}
            max={1}
            step={0.05}
            onValueChange={([v]) => onChange("minGenetics", v)}
          />
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-normal text-muted-foreground">
              Minimum evidence completeness (of {evidenceCategoryCount})
            </Label>
            <span className="font-mono text-xs tabular-nums">{values.completeness.toFixed(2)}</span>
          </div>
          <Slider
            value={[values.completeness]}
            min={0}
            max={1}
            step={1 / evidenceCategoryCount}
            onValueChange={([v]) => onChange("completeness", v)}
          />
        </div>

        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={values.druggable}
            onCheckedChange={(checked) => onChange("druggable", checked === true)}
          />
          Require small-molecule druggability
        </label>

        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={values.tissue}
            onCheckedChange={(checked) => onChange("tissue", checked === true)}
          />
          Require detectable expression in disease-relevant tissue
        </label>

        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={safetyForced || values.safety}
            disabled={safetyForced}
            onCheckedChange={(checked) => onChange("safety", checked === true)}
          />
          Hide targets with a recorded safety concern
        </label>

        <Tooltip>
          <TooltipTrigger asChild>
            <label className="flex cursor-not-allowed items-center gap-2 text-sm text-muted-foreground/60">
              <Checkbox checked={false} disabled />
              Target family
            </label>
          </TooltipTrigger>
          <TooltipContent className="max-w-64">
            Not available in this release — needs target.targetClass, which is unrelated to
            Reactome/GTEx/STRING. Left visible rather than hidden so the gap is obvious.
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
