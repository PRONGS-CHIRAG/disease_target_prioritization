"use client";

import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiErrorNotice, LoadingBlock, SelectDiseasePrompt } from "@/components/page-states";
import { ReadoutStrip } from "@/components/readout-strip";
import { useDiseaseDetail } from "@/hooks/use-diseases";
import { useDiseaseId } from "@/hooks/use-disease-id";
import { apiErrorMessage } from "@/lib/api-client";

// nuqs's useQueryState reads useSearchParams internally, which bails out
// of static prerendering without a Suspense boundary — required even for
// an all-client-component page under `output: "export"`
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout).
export default function OverviewPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <OverviewContent />
    </Suspense>
  );
}

function OverviewContent() {
  const [diseaseId] = useDiseaseId();
  const { data: disease, isLoading, error } = useDiseaseDetail(diseaseId);

  if (!diseaseId) return <SelectDiseasePrompt />;
  if (isLoading) return <LoadingBlock rows={6} />;
  if (error || !disease) {
    return <ApiErrorNotice message={apiErrorMessage(error, "Could not load this disease.")} />;
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-xs text-muted-foreground">{disease.disease_id}</p>
        <h1 className="mt-1 font-heading text-3xl font-semibold">{disease.name}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          {disease.description || "No description available for this release."}
        </p>
      </header>

      <ReadoutStrip
        items={[
          {
            label: "Candidate targets",
            value: disease.n_associated_targets?.toLocaleString() ?? "—",
          },
          {
            label: "Evidence categories built",
            value: `${disease.evidence_categories_built} of ${disease.evidence_categories_total}`,
          },
          {
            label: "Data release",
            value: disease.dataset_version ?? "—",
            caption: disease.extraction_date ? `Extracted ${disease.extraction_date}` : undefined,
          },
        ]}
      />

      <section>
        <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Therapeutic area
        </h2>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {disease.therapeutic_areas && disease.therapeutic_areas.length > 0 ? (
            disease.therapeutic_areas.map((area) => (
              <Badge key={area} variant="secondary" className="font-normal capitalize">
                {area}
              </Badge>
            ))
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          )}
        </div>
      </section>

      <section>
        <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Evidence-source coverage
        </h2>
        <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
          All six evidence categories Context.md §21/§38.2 specify are built as of Milestone 4 —
          Reactome, GTEx and STRING are integrated alongside Open Targets.
        </p>
        <div className="mt-3 overflow-hidden rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Note</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {disease.evidence_coverage.map((row) => (
                <TableRow key={row.category}>
                  <TableCell className="font-medium capitalize">{row.category}</TableCell>
                  <TableCell>
                    <Badge variant={row.built ? "default" : "outline"} className="font-normal">
                      {row.built ? "Built" : "Not yet integrated"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{row.note || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <p className="max-w-2xl rounded-md border border-border bg-muted/40 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
        Scores are prioritization hypotheses from public evidence, not validated scientific
        conclusions. See the Limitations panel in the sidebar.
      </p>
    </div>
  );
}
