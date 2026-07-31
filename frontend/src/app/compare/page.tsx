"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useMemo, Suspense } from "react";

import { EvidenceCard } from "@/components/evidence/evidence-card";
import { ApiErrorNotice, LoadingBlock, SelectDiseasePrompt } from "@/components/page-states";
import { ScoreStrip } from "@/components/score-strip";
import { Button } from "@/components/ui/button";
import { useDiseaseId } from "@/hooks/use-disease-id";
import type { EvidenceRequestBody } from "@/hooks/use-evidence";
import { useEvidenceBatch } from "@/hooks/use-evidence-batch";
import { useLinkedWeights } from "@/hooks/use-linked-weights";
import { useMeta } from "@/hooks/use-meta";
import { useTargetIds } from "@/hooks/use-target-ids";
import { apiErrorMessage } from "@/lib/api-client";
import { DIMENSION_ORDER } from "@/lib/dimensions";

// nuqs's useQueryState reads useSearchParams internally, which bails out
// of static prerendering without a Suspense boundary — required even for
// an all-client-component page under `output: "export"`
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout).
export default function ComparePage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <CompareContent />
    </Suspense>
  );
}

function CompareContent() {
  const [diseaseId] = useDiseaseId();
  const [targetIds, setTargetIds] = useTargetIds();
  const { data: meta, isLoading: metaLoading } = useMeta();
  // Set only when this page was reached via "Compare N selected" from the
  // ranking page — carries that response's server-normalized weights so
  // these scores match the rows the user selected there.
  const linkedWeights = useLinkedWeights();

  const requests: (EvidenceRequestBody | null)[] = useMemo(
    () =>
      targetIds.map((targetId) =>
        diseaseId && meta
          ? { disease_id: diseaseId, target_id: targetId, weights: linkedWeights ?? meta.default_weights }
          : null,
      ),
    [targetIds, diseaseId, meta, linkedWeights],
  );
  const results = useEvidenceBatch(requests);

  const removeTarget = (targetId: string) => void setTargetIds(targetIds.filter((id) => id !== targetId));

  if (!diseaseId) return <SelectDiseasePrompt />;
  if (targetIds.length < 2) {
    return (
      <p className="rounded-md border border-dashed border-border bg-card px-4 py-3 text-sm text-muted-foreground">
        Select 2-4 targets to compare from the{" "}
        <Link href={`/ranking?disease=${encodeURIComponent(diseaseId)}`} className="underline">
          Target ranking
        </Link>{" "}
        page.
      </p>
    );
  }
  if (metaLoading || !meta) return <LoadingBlock rows={6} />;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-heading text-2xl font-semibold">Compare targets</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          {targetIds.length} targets, evaluated under{" "}
          {linkedWeights ? "the weights active on the ranking page you linked from" : "the API's default weights"} (
          {DIMENSION_ORDER.map((d) => meta.dimension_labels[d] ?? d).join(", ")}).
        </p>
      </header>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">Gene</th>
              <th className="px-3 py-2 font-medium">Score</th>
              <th className="px-3 py-2 font-medium">Rank</th>
            </tr>
          </thead>
          <tbody>
            {results.map((result, i) => {
              const evidence = result.data;
              return (
                <tr key={targetIds[i]} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-medium">{evidence?.gene_symbol ?? targetIds[i]}</td>
                  <td className="w-64 px-3 py-2">
                    {evidence && (
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs tabular-nums">{evidence.score.toFixed(3)}</span>
                        <ScoreStrip
                          size="micro"
                          className="w-24"
                          segments={DIMENSION_ORDER.map((dim) => ({
                            key: dim,
                            label: meta.dimension_labels[dim] ?? dim,
                            value: evidence.contributions[dim] ?? 0,
                          }))}
                        />
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs tabular-nums text-muted-foreground">
                    {evidence?.rank ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div
        className="grid grid-cols-1 gap-6"
        style={{ gridTemplateColumns: `repeat(${targetIds.length}, minmax(0, 1fr))` }}
      >
        {results.map((result, i) => {
          const targetId = targetIds[i];
          return (
            <div key={targetId} className="min-w-0 rounded-md border border-border bg-card p-4">
              <div className="mb-2 flex justify-end">
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6"
                  aria-label={`Remove ${targetId} from comparison`}
                  onClick={() => removeTarget(targetId)}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
              {result.isLoading && <LoadingBlock rows={4} />}
              {result.error && (
                <ApiErrorNotice message={apiErrorMessage(result.error, "Could not load this target.")} />
              )}
              {result.data && <EvidenceCard evidence={result.data} meta={meta} compact />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
