"use client";

import Link from "next/link";

import { CompletenessBadge } from "@/components/completeness-badge";
import { EvidenceRadar } from "@/components/evidence/evidence-radar";
import { EvidenceValue } from "@/components/evidence-value";
import { ScoreStrip } from "@/components/score-strip";
import { Badge } from "@/components/ui/badge";
import type { EvidenceResponse } from "@/hooks/use-evidence";
import type { components } from "@/lib/api-types";
import { DIMENSION_ORDER } from "@/lib/dimensions";

type MetaResponse = components["schemas"]["MetaResponse"];

function EvidenceItemList({
  items: itemsProp,
  tone,
}: {
  items: EvidenceResponse["supporting"];
  tone: "supporting" | "contradicting";
}) {
  const items = itemsProp ?? [];
  if (items.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        {tone === "supporting" ? "No supporting factors identified." : "None identified."}
      </p>
    );
  }
  return (
    <ul className="space-y-1.5">
      {items.slice(0, 8).map((item, i) => (
        <li key={`${item.category}-${i}`} className="flex min-w-0 items-baseline justify-between gap-2 text-xs">
          <span className="min-w-0 truncate" title={`${item.category} (${item.source})`}>
            <span className="font-medium">{item.category}</span>{" "}
            <span className="text-muted-foreground">({item.source})</span>
          </span>
          <span className="shrink-0 font-mono tabular-nums">
            {typeof item.value === "number" ? item.value.toFixed(3) : (item.value ?? "—")}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function EvidenceCard({
  evidence,
  meta,
  compact = false,
  weightsNote,
}: {
  evidence: EvidenceResponse;
  meta: MetaResponse;
  compact?: boolean;
  /** States which weight set produced `evidence.score` — a bare number with
   * no source is ambiguous once more than one page can request evidence
   * under different weights (milestone5_plan.md §3, invariant 10). */
  weightsNote?: string;
}) {
  const contributionSegments = DIMENSION_ORDER.map((dim) => ({
    key: dim,
    label: meta.dimension_labels[dim] ?? dim,
    value: evidence.contributions[dim] ?? 0,
  }));
  // Pydantic's `Field(default_factory=...)` fields have no JSON Schema
  // `default`, so openapi-typescript marks them optional even though the
  // API always populates them — defaulted locally rather than threading
  // `?? []`/`?? {}` through every call site below.
  const missing = evidence.missing ?? [];
  const limitations = evidence.limitations ?? [];
  const sourceLinks = evidence.source_links ?? {};
  const notBuildable = evidence.not_buildable ?? {};

  return (
    // A query container, so every grid below responds to the width of THIS
    // card rather than the viewport's. The same card renders at ~1088px on
    // /evidence and at ~254px in a four-up /compare column; viewport
    // breakpoints (`sm:`) cannot tell those apart, which is what previously
    // put three stat boxes and a three-column dimension list into a 220px
    // card and overlapped their labels with their numbers.
    <div className="@container space-y-6">
      <header className="min-w-0">
        <p className="truncate font-mono text-xs text-muted-foreground">{evidence.target_id}</p>
        <h2 className="mt-0.5 font-heading text-xl font-semibold">{evidence.gene_symbol}</h2>
        {evidence.gene_name && <p className="text-xs break-words text-muted-foreground">{evidence.gene_name}</p>}
        {weightsNote && <p className="mt-1 text-xs text-muted-foreground">{weightsNote}</p>}
      </header>

      <div className="grid grid-cols-1 gap-3 @md:grid-cols-3">
        <StatBlock label="Weighted-baseline score" value={evidence.score.toFixed(3)} />
        <StatBlock
          label="XGBoost (held-out)"
          value={<EvidenceValue value={evidence.xgboost_score_held_out} className="text-lg" />}
        />
        <StatBlock
          label="Positive in N other diseases"
          value={<EvidenceValue value={evidence.n_other_diseases_positive} digits={0} className="text-lg" />}
        />
      </div>
      {evidence.rank != null && evidence.total_candidates != null && (
        <p className="text-xs text-muted-foreground">
          Overall rank: {evidence.rank} of {evidence.total_candidates.toLocaleString()} candidates
        </p>
      )}

      <section>
        <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Evidence breakdown
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Weighted-baseline score decomposed into its evidence dimensions — the segments sum exactly
          to the score.
        </p>
        <ScoreStrip segments={contributionSegments} size="lg" className="mt-3" />
        <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-1.5 @xs:grid-cols-2 @xl:grid-cols-3">
          {contributionSegments.map((s) => (
            <div key={s.key} className="flex min-w-0 items-center justify-between gap-2 text-xs">
              {/* min-w-0 + truncate on the label and shrink-0 on the value: the
                  value keeps its full precision and the label gives up space
                  first, so the two can never overlap however narrow the card. */}
              <dt className="min-w-0 truncate text-muted-foreground" title={s.label}>
                {s.label}
              </dt>
              <dd className="shrink-0 font-mono tabular-nums">{s.value.toFixed(3)}</dd>
            </div>
          ))}
        </dl>
      </section>

      {!compact && (
        <section>
          <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Evidence radar
          </h3>
          <p className="mt-1 max-w-md text-xs text-muted-foreground">
            A dimension at or near zero can mean weak evidence OR no evidence — a hollow, dashed
            point marks a dimension with nothing recorded; check missing evidence below before
            reading it as a negative finding.
          </p>
          <EvidenceRadar dimensionValues={evidence.dimension_values} dimensionLabels={meta.dimension_labels} />
        </section>
      )}

      <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2">
        <section>
          <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Strongest supporting evidence
          </h3>
          <div className="mt-2">
            <EvidenceItemList items={evidence.supporting} tone="supporting" />
          </div>
        </section>
        <section>
          <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Strongest negative evidence
          </h3>
          <div className="mt-2">
            <EvidenceItemList items={evidence.contradicting} tone="contradicting" />
          </div>
        </section>
      </div>

      <section>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Missing evidence
          </h3>
          <CompletenessBadge
            count={meta.evidence_categories.length - missing.length}
            total={meta.evidence_categories.length}
          />
        </div>
        {missing.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">No missing categories for this target.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {missing.map((category) => (
              <li key={category} className="capitalize">
                <span className="font-medium text-foreground">{category}</span>: no evidence recorded
                for this target
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Existing drug information
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          This is the clinical-development evidence the training label is built from — shown for
          context, not as ranking evidence.
        </p>
        <div className="mt-2 text-sm">
          <span className="font-mono">{evidence.label_n_drugs ?? 0}</span> drug(s) recorded for this
          disease family.
          {evidence.label_drug_names && <div className="mt-1 text-xs break-words">{evidence.label_drug_names}</div>}
          {evidence.label_max_clinical_stage != null && (
            <div className="mt-1 text-xs text-muted-foreground">
              Maximum clinical stage reached: {evidence.label_max_clinical_stage}
            </div>
          )}
        </div>
      </section>

      {!compact && (
        <section>
          <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Not yet available for any target
          </h3>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {Object.entries(notBuildable).map(([label, reason]) => (
              <li key={label}>
                <span className="font-medium text-foreground">{label}</span>: not yet integrated —{" "}
                {reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Source references
        </h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.entries(sourceLinks).map(([name, url]) => (
            <Badge key={name} variant="secondary" asChild className="font-normal">
              <Link href={url} target="_blank" rel="noopener noreferrer">
                {name}
              </Link>
            </Badge>
          ))}
        </div>
      </section>

      {!compact && (
        <section className="rounded-md border border-border bg-muted/40 p-4">
          <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Limitations
          </h3>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function StatBlock({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-card px-3 py-2.5">
      {/* hyphens-auto so "Positive in N other diseases" breaks inside the box
          instead of pushing its own border past the card edge. */}
      <div className="text-[11px] font-semibold tracking-wide break-words hyphens-auto text-muted-foreground uppercase">
        {label}
      </div>
      <div className="mt-0.5 truncate text-lg tabular-nums">{value}</div>
    </div>
  );
}
