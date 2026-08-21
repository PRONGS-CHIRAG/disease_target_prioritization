"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ApiErrorNotice, LoadingBlock } from "@/components/page-states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useEvidenceDetail, type EvidenceDetailResponse } from "@/hooks/use-evidence-detail";
import { apiErrorMessage } from "@/lib/api-client";

/**
 * Context.md §21's target-detail evidence, as things you can read rather than
 * as the aggregates `path__n_pathways` / `expr__*` / `net__*` that the score
 * is built from.
 *
 * Rendered only on /evidence, never inside the compact card on /compare —
 * which is also why it fetches through its own weight-independent query
 * instead of riding along on `/api/evidence`.
 */
export function EvidenceDetailPanels({
  diseaseId,
  targetId,
}: {
  diseaseId: string;
  targetId: string;
}) {
  const { data, isLoading, error } = useEvidenceDetail(diseaseId, targetId);

  if (isLoading) return <LoadingBlock rows={6} />;
  if (error || !data) {
    return <ApiErrorNotice message={apiErrorMessage(error, "Could not load evidence detail.")} />;
  }

  return (
    <div className="@container space-y-6">
      <PathwayPanel detail={data} />
      <TissuePanel detail={data} />
      <PartnerPanel detail={data} diseaseId={diseaseId} />
      <LiteraturePanel detail={data} />
    </div>
  );
}

function PanelHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </h3>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="mt-2 text-xs text-muted-foreground">{children}</p>;
}

/** Grouped by root Reactome category, because that is the unit
 * `path__n_pathways` counts — a flat list of every membership would show far
 * more rows than the number displayed beside it. */
function PathwayPanel({ detail }: { detail: EvidenceDetailResponse }) {
  const groups = detail.pathway_groups ?? [];

  return (
    <section>
      <div className="flex flex-wrap items-center gap-2">
        <PanelHeading>Relevant pathways</PanelHeading>
        {groups.length > 0 && (
          <Badge variant="secondary" className="font-mono text-[11px] font-normal tabular-nums">
            {detail.n_root_categories} categories
          </Badge>
        )}
      </div>
      {groups.length === 0 ? (
        <EmptyNote>
          No Reactome pathway annotation for this gene — about half of ranked targets have none.
          This is missing evidence, not evidence of an inactive gene.
        </EmptyNote>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted-foreground">
            Reactome memberships, grouped by root category. The category count is exactly what{" "}
            <span className="font-mono">path__n_pathways</span> contributes to the score.
          </p>
          <ul className="mt-3 space-y-2">
            {groups.map((group) => (
              <li key={group.root_pathway_id}>
                <details className="group rounded-md border border-border bg-card">
                  <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-sm">
                    <span className="min-w-0 truncate font-medium">{group.root_pathway_name}</span>
                    <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                      {(group.pathways ?? []).length}
                    </span>
                  </summary>
                  <ul className="space-y-1 border-t border-border px-3 py-2">
                    {(group.pathways ?? []).map((pathway) => (
                      <li key={pathway.pathway_id} className="text-xs">
                        <Link
                          href={pathway.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-baseline gap-1 hover:underline"
                        >
                          <span className="min-w-0">{pathway.name}</span>
                          <ExternalLink className="size-3 shrink-0 self-center opacity-50" aria-hidden />
                        </Link>
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

const TISSUES_COLLAPSED = 10;

/** A bar per tissue, disease-relevant ones marked. Bars are scaled to the
 * gene's own maximum, so the shape shows whether expression is broad or
 * restricted — the thing a top-N table cannot show. */
function TissuePanel({ detail }: { detail: EvidenceDetailResponse }) {
  const [expanded, setExpanded] = useState(false);
  const tissues = detail.tissues ?? [];
  const unmatched = detail.relevant_tissues_unmatched ?? [];
  const shown = expanded ? tissues : tissues.slice(0, TISSUES_COLLAPSED);
  const max = tissues.length > 0 ? Math.max(...tissues.map((t) => t.median_tpm), 0) : 0;

  return (
    <section>
      <PanelHeading>Tissue expression</PanelHeading>
      {tissues.length === 0 ? (
        <EmptyNote>This gene is absent from the GTEx median-TPM matrix.</EmptyNote>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted-foreground">
            GTEx median TPM, highest first. Tissues this disease names as relevant are marked — the
            same match that produced <span className="font-mono">expr__relevant_tissue_tpm</span>.
          </p>
          <ul className="mt-3 space-y-1">
            {shown.map((tissue) => (
              <li key={tissue.tissue} className="flex items-center gap-2 text-xs">
                <span
                  className={
                    tissue.is_relevant
                      ? "min-w-0 flex-1 truncate font-medium text-foreground"
                      : "min-w-0 flex-1 truncate text-muted-foreground"
                  }
                  title={tissue.tissue}
                >
                  {tissue.tissue.replaceAll("_", " ")}
                </span>
                <span
                  aria-hidden
                  className="h-1.5 w-16 shrink-0 overflow-hidden rounded-xs bg-muted @sm:w-28"
                >
                  <span
                    className={tissue.is_relevant ? "block h-full bg-primary" : "block h-full bg-muted-foreground/40"}
                    style={{ width: `${max > 0 ? (tissue.median_tpm / max) * 100 : 0}%` }}
                  />
                </span>
                <span className="w-14 shrink-0 text-right font-mono tabular-nums">
                  {tissue.median_tpm.toFixed(1)}
                </span>
                {tissue.is_relevant && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-label="Disease-relevant tissue" />
                    </TooltipTrigger>
                    <TooltipContent>Named as relevant for this disease</TooltipContent>
                  </Tooltip>
                )}
              </li>
            ))}
          </ul>
          {tissues.length > TISSUES_COLLAPSED && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 h-7 px-2 text-xs"
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "Show fewer" : `Show all ${tissues.length} tissues`}
            </Button>
          )}
        </>
      )}
      {unmatched.length > 0 && (
        <EmptyNote>
          No GTEx tissue matches {unmatched.map((t) => `"${t}"`).join(", ")} for this disease, so
          the relevant-tissue signal is structurally absent here — GTEx has no synovial data at
          all. Not a low value: no value.
        </EmptyNote>
      )}
    </section>
  );
}

/** STRING partners. A partner that is not itself a candidate for the selected
 * disease is deliberately not a link — there is no (disease, target) row for
 * it, so its evidence page would 404. */
function PartnerPanel({
  detail,
  diseaseId,
}: {
  detail: EvidenceDetailResponse;
  diseaseId: string;
}) {
  const partners = detail.partners ?? [];

  return (
    <section>
      <PanelHeading>Protein interaction partners</PanelHeading>
      {partners.length === 0 ? (
        <EmptyNote>
          No STRING interaction at or above confidence {detail.partner_min_score} where the partner
          is also a ranked target.
        </EmptyNote>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted-foreground">
            Highest-confidence STRING partners (combined score ≥ {detail.partner_min_score}) that
            are also candidates in this dataset. Interaction is not evidence of shared disease
            role.
          </p>
          <ul className="mt-3 flex flex-wrap gap-1.5">
            {partners.map((partner) => (
              <li key={partner.target_id}>
                {partner.is_candidate ? (
                  <Link
                    href={`/evidence?disease=${encodeURIComponent(diseaseId)}&target=${encodeURIComponent(partner.target_id)}`}
                    className="inline-flex items-baseline gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-xs hover:bg-accent"
                  >
                    <span className="font-medium">{partner.gene_symbol}</span>
                    <span className="font-mono tabular-nums text-muted-foreground">{partner.score}</span>
                  </Link>
                ) : (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-baseline gap-1.5 rounded-md border border-dashed border-border px-2 py-1 text-xs text-muted-foreground">
                        <span>{partner.gene_symbol}</span>
                        <span className="font-mono tabular-nums">{partner.score}</span>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      Not a candidate for this disease — no evidence page to open.
                    </TooltipContent>
                  </Tooltip>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** What this repo actually has: a co-mention score. The absence of titles and
 * abstracts is stated by `not_buildable` in the card above; this panel offers
 * the search rather than pretending to answer it. */
function LiteraturePanel({ detail }: { detail: EvidenceDetailResponse }) {
  const { literature } = detail;

  return (
    <section>
      <PanelHeading>Supporting literature</PanelHeading>
      <p className="mt-1 text-xs text-muted-foreground">
        Only a Europe PMC co-mention score is integrated — no titles, dates or abstracts are
        retrieved. Co-mention counts reward well-studied genes, so this is the weakest evidence
        here.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span>
          <span className="text-muted-foreground">Co-mention score </span>
          <span className="font-mono tabular-nums">
            {literature.europepmc_score == null ? "—" : literature.europepmc_score.toFixed(3)}
          </span>
        </span>
        <span>
          <span className="text-muted-foreground">Publications </span>
          <span className="font-mono tabular-nums">
            {literature.europepmc_evidence_count == null
              ? "—"
              : Math.round(literature.europepmc_evidence_count).toLocaleString()}
          </span>
        </span>
        <Link
          href={literature.search_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 underline"
        >
          Search Europe PMC
          <ExternalLink className="size-3 shrink-0" aria-hidden />
        </Link>
      </div>
    </section>
  );
}
