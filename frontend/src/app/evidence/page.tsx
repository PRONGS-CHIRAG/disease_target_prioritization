"use client";

import { Suspense } from "react";

import { EvidenceCard } from "@/components/evidence/evidence-card";
import { ApiErrorNotice, LoadingBlock, SelectDiseasePrompt } from "@/components/page-states";
import { useDiseaseId } from "@/hooks/use-disease-id";
import { useEvidence, type EvidenceRequestBody } from "@/hooks/use-evidence";
import { useLinkedWeights } from "@/hooks/use-linked-weights";
import { useMeta } from "@/hooks/use-meta";
import { useTargetId } from "@/hooks/use-target-id";
import { apiErrorMessage } from "@/lib/api-client";

// nuqs's useQueryState reads useSearchParams internally, which bails out
// of static prerendering without a Suspense boundary — required even for
// an all-client-component page under `output: "export"`
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout).
export default function EvidencePage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <EvidenceContent />
    </Suspense>
  );
}

function EvidenceContent() {
  const [diseaseId] = useDiseaseId();
  const [targetId] = useTargetId();
  const { data: meta, isLoading: metaLoading } = useMeta();
  // Set only when this page was reached via a "View evidence" link from the
  // ranking page — carries that response's server-normalized weights so the
  // score shown here matches the row the user clicked, rather than silently
  // recomputing under the API's default weights (milestone5_plan.md §3,
  // invariant 10).
  const linkedWeights = useLinkedWeights();

  const request: EvidenceRequestBody | null =
    diseaseId && targetId && meta
      ? { disease_id: diseaseId, target_id: targetId, weights: linkedWeights ?? meta.default_weights }
      : null;
  const { data: evidence, isLoading, error } = useEvidence(request);

  if (!diseaseId) return <SelectDiseasePrompt />;
  if (!targetId) {
    return (
      <p className="rounded-md border border-dashed border-border bg-card px-4 py-3 text-sm text-muted-foreground">
        Select a target from the Target ranking page first.
      </p>
    );
  }
  if (metaLoading || isLoading || !meta) return <LoadingBlock rows={8} />;
  if (error || !evidence) {
    return <ApiErrorNotice message={apiErrorMessage(error, "Could not load evidence for this target.")} />;
  }

  return (
    <div className="max-w-3xl">
      <EvidenceCard
        evidence={evidence}
        meta={meta}
        weightsNote={
          linkedWeights
            ? "Scored with the weights active on the ranking page you linked from."
            : "Scored with the API's default weights — open from Target ranking to match its active scenario."
        }
      />
    </div>
  );
}
