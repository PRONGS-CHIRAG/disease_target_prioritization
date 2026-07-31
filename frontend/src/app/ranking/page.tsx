"use client";

import { Download, GitCompareArrows } from "lucide-react";
import { useCallback, useMemo, useState, Suspense } from "react";

import { FilterControls, type RankingFilterValues } from "@/components/ranking/filter-controls";
import { MAX_COMPARE, RankingTable } from "@/components/ranking/ranking-table";
import { ScenarioControls } from "@/components/ranking/scenario-controls";
import { ApiErrorNotice, LoadingBlock, SelectDiseasePrompt } from "@/components/page-states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import { useDiseaseId } from "@/hooks/use-disease-id";
import { useDiseaseDetail } from "@/hooks/use-diseases";
import { linkedWeightsQueryString } from "@/hooks/use-linked-weights";
import { useMeta } from "@/hooks/use-meta";
import { useRanking, type RankedTarget, type RankingRequestBody } from "@/hooks/use-rank";
import { useRankingState } from "@/hooks/use-ranking-state";
import { apiErrorMessage } from "@/lib/api-client";
import { exportRankingCsv } from "@/lib/csv-export";
import { resolveScenarioWeights } from "@/lib/scenario";
import { useRouter } from "next/navigation";

// nuqs's useQueryState reads useSearchParams internally, which bails out
// of static prerendering without a Suspense boundary — required even for
// an all-client-component page under `output: "export"`
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout).
export default function RankingPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={3} />}>
      <RankingContent />
    </Suspense>
  );
}

function RankingContent() {
  const router = useRouter();
  const [diseaseId] = useDiseaseId();
  const { data: disease } = useDiseaseDetail(diseaseId);
  const { data: meta, isLoading: metaLoading } = useMeta();
  const [state, setState] = useRankingState();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [visibleRows, setVisibleRows] = useState<RankedTarget[]>([]);

  const customWeights = useMemo(
    () => ({
      genetics: state.wGenetics,
      evidence_diversity: state.wEvidenceDiversity,
      functional: state.wFunctional,
      literature: state.wLiterature,
      druggability: state.wDruggability,
    }),
    [state.wGenetics, state.wEvidenceDiversity, state.wFunctional, state.wLiterature, state.wDruggability],
  );

  const safetyForced = meta ? state.scenario === meta.safety_first.slug : false;
  const weights = resolveScenarioWeights(state.scenario, customWeights, meta);

  const requestBody: RankingRequestBody | null =
    diseaseId && weights
      ? {
          disease_id: diseaseId,
          top_n: state.top,
          weights,
          sort_by: state.sort,
          filters: {
            min_genetics_evidence: state.minGenetics > 0 ? state.minGenetics : null,
            require_druggable: state.druggable,
            relevant_tissue: state.tissue,
            min_evidence_completeness: state.completeness > 0 ? state.completeness : null,
            exclude_safety_concerns: safetyForced || state.safety,
            target_family: null,
          },
        }
      : null;

  const { data: ranking, isLoading, error } = useRanking(requestBody);

  const toggleSelected = useCallback((targetId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(targetId)) next.delete(targetId);
      else if (next.size < MAX_COMPARE) next.add(targetId);
      return next;
    });
  }, []);

  const onFilterChange = <K extends keyof RankingFilterValues>(key: K, value: RankingFilterValues[K]) => {
    const map: Record<keyof RankingFilterValues, keyof typeof state> = {
      minGenetics: "minGenetics",
      druggable: "druggable",
      tissue: "tissue",
      completeness: "completeness",
      safety: "safety",
    };
    void setState({ [map[key]]: value });
  };

  const onCustomWeightChange = (dimension: string, value: number) => {
    const map: Record<string, keyof typeof state> = {
      genetics: "wGenetics",
      evidence_diversity: "wEvidenceDiversity",
      functional: "wFunctional",
      literature: "wLiterature",
      druggability: "wDruggability",
    };
    const key = map[dimension];
    if (key) void setState({ [key]: value });
  };

  if (!diseaseId) return <SelectDiseasePrompt />;
  if (metaLoading || !meta) return <LoadingBlock rows={3} />;

  return (
    <div className="space-y-6">
      <header>
        <p className="font-mono text-xs text-muted-foreground">{diseaseId}</p>
        <h1 className="mt-1 font-heading text-2xl font-semibold">
          Target ranking{disease ? ` — ${disease.name}` : ""}
        </h1>
      </header>

      <ScenarioControls
        meta={meta}
        scenario={state.scenario}
        onScenarioChange={(slug) => void setState({ scenario: slug as typeof state.scenario })}
        customWeights={customWeights}
        onCustomWeightsChange={onCustomWeightChange}
        weightsUsed={ranking?.weights_used}
      />

      <FilterControls
        values={state}
        onChange={onFilterChange}
        safetyForced={safetyForced}
        evidenceCategoryCount={meta.evidence_categories.length}
      />

      <div className="flex flex-wrap items-end justify-between gap-4 rounded-md border border-border bg-card p-4">
        <div>
          <Label className="text-xs font-normal text-muted-foreground">Sort by</Label>
          <RadioGroup
            className="mt-2 flex gap-4"
            value={state.sort}
            onValueChange={(v) => void setState({ sort: v as typeof state.sort })}
          >
            <label className="flex items-center gap-1.5 text-sm">
              <RadioGroupItem value="weighted_baseline" /> Weighted baseline (exact contributions)
            </label>
            <label className="flex items-center gap-1.5 text-sm">
              <RadioGroupItem value="xgboost_held_out" /> XGBoost held-out
            </label>
          </RadioGroup>
        </div>
        <div className="w-56 space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-normal text-muted-foreground">Show top N</Label>
            <span className="font-mono text-xs tabular-nums">{state.top}</span>
          </div>
          <Slider
            value={[state.top]}
            min={10}
            max={200}
            step={10}
            onValueChange={([v]) => void setState({ top: v })}
          />
        </div>
      </div>

      {state.sort === "xgboost_held_out" && (
        <Alert>
          <AlertTitle>Cross-disease popularity caveat</AlertTitle>
          <AlertDescription>
            milestone2.md §1: cross-disease target popularity accounts for most of the XGBoost
            score for most targets (novel-only NDCG@10 0.009 vs. 0.696 primary). A high score
            here is a weaker disease-specific claim than the weighted-baseline score.
          </AlertDescription>
        </Alert>
      )}

      {isLoading && <LoadingBlock rows={8} />}
      {error && <ApiErrorNotice message={apiErrorMessage(error, "Could not load the ranking.")} />}

      {ranking && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              Showing {ranking.targets.length} of {ranking.total_candidates.toLocaleString()}{" "}
              candidates. Evidence completeness counts all six categories — genetics, functional,
              druggability, pathway, expression and network — out of 6 total.
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={ranking.targets.length === 0}
                onClick={() =>
                  exportRankingCsv(visibleRows.length ? visibleRows : ranking.targets, {
                    diseaseName: disease?.name ?? diseaseId,
                    diseaseId,
                    totalCandidates: ranking.total_candidates,
                    sortBy: ranking.sort_by,
                  })
                }
              >
                <Download className="size-3.5" aria-hidden />
                Export {ranking.targets.length} of {ranking.total_candidates.toLocaleString()} (CSV)
              </Button>
              <Button
                size="sm"
                disabled={selected.size < 2}
                onClick={() =>
                  router.push(
                    `/compare?disease=${encodeURIComponent(diseaseId)}&targets=${Array.from(selected)
                      .map(encodeURIComponent)
                      .join(",")}${ranking ? `&${linkedWeightsQueryString(ranking.weights_used)}` : ""}`,
                  )
                }
              >
                <GitCompareArrows className="size-3.5" aria-hidden />
                Compare {selected.size > 0 ? selected.size : ""} selected
              </Button>
            </div>
          </div>

          {ranking.targets.length === 0 ? (
            <p className="rounded-md border border-dashed border-border bg-card px-4 py-3 text-sm text-muted-foreground">
              No targets survive the current filters.
            </p>
          ) : (
            <RankingTable
              targets={ranking.targets}
              diseaseId={diseaseId}
              dimensionLabels={meta.dimension_labels}
              weightsUsed={ranking.weights_used}
              selected={selected}
              onToggleSelected={toggleSelected}
              onRowsChange={setVisibleRows}
            />
          )}
        </>
      )}
    </div>
  );
}
