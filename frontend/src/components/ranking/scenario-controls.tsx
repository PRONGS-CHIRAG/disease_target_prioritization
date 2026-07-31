"use client";

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { DIMENSION_ORDER } from "@/lib/dimensions";
import type { components } from "@/lib/api-types";
import { normalizeWeights } from "@/lib/weights";

type MetaResponse = components["schemas"]["MetaResponse"];

export function ScenarioControls({
  meta,
  scenario,
  onScenarioChange,
  customWeights,
  onCustomWeightsChange,
  weightsUsed,
}: {
  meta: MetaResponse;
  scenario: string;
  onScenarioChange: (slug: string) => void;
  customWeights: Record<string, number>;
  onCustomWeightsChange: (dimension: string, value: number) => void;
  /** The server-normalized weights actually applied to the last response —
   * displayed as the source of truth, never the raw slider positions
   * (`normalize_weights`'s docstring: the caller must display the
   * NORMALIZED values, or the contributions shown won't match). */
  weightsUsed: Record<string, number> | undefined;
}) {
  const isCustom = scenario === meta.custom_slug;
  const options = [
    ...meta.scenario_presets.map((p) => ({ slug: p.slug, label: p.label })),
    { slug: meta.safety_first.slug, label: meta.safety_first.label },
    { slug: meta.custom_slug, label: meta.custom_label },
  ];
  const normalizedCustom = normalizeWeights(customWeights);

  return (
    <div className="space-y-3 rounded-md border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="font-heading text-sm font-semibold">Scenario weights</h3>
          <p className="text-xs text-muted-foreground">
            Changes what the weighted-baseline score rewards. The held-out XGBoost score&rsquo;s
            weights cannot be adjusted at inference.
          </p>
        </div>
        <Select value={scenario} onValueChange={onScenarioChange}>
          <SelectTrigger className="w-64 font-sans text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.slug} value={o.slug} className="text-sm">
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isCustom && (
        <div className="grid grid-cols-1 gap-4 border-t border-border pt-3 sm:grid-cols-2">
          {DIMENSION_ORDER.map((dim) => (
            <div key={dim} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-normal text-muted-foreground">
                  {meta.dimension_labels[dim] ?? dim}
                </Label>
                <span className="font-mono text-xs tabular-nums">
                  {(normalizedCustom[dim] ?? 0).toFixed(3)}
                </span>
              </div>
              <Slider
                value={[customWeights[dim] ?? 0]}
                min={0}
                max={1}
                step={0.05}
                onValueChange={([v]) => onCustomWeightsChange(dim, v)}
              />
            </div>
          ))}
          <p className="col-span-full text-xs text-muted-foreground">
            Sliders need not sum to 1.0 — normalized automatically. Values above show the
            normalized weights that will actually be used.
          </p>
        </div>
      )}

      {weightsUsed && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-2 font-mono text-[11px] text-muted-foreground">
          <span className="font-sans font-medium text-foreground">Applied:</span>
          {DIMENSION_ORDER.filter((d) => d in weightsUsed).map((d) => (
            <span key={d}>
              {meta.dimension_labels[d] ?? d} {weightsUsed[d].toFixed(3)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
