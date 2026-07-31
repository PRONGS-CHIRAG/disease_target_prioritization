import type { RankedTarget } from "@/hooks/use-rank";

function csvCell(value: string | number | null | undefined): string {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Exports exactly the rows on screen — never the full ranking — so the
 * file can't drift from what the user is looking at (milestone5_plan.md
 * §2.7). The filename and a header comment both state the partial count,
 * since a 50-row CSV silently read as "the whole ranking" is the failure
 * mode this is guarding against.
 */
export function exportRankingCsv(
  rows: RankedTarget[],
  opts: { diseaseName: string; diseaseId: string; totalCandidates: number; sortBy: string },
) {
  const header = [
    "rank",
    "gene_symbol",
    "target_id",
    "gene_name",
    "score",
    "sort_by",
    "weighted_baseline_score",
    "xgboost_score_held_out",
    "genetics",
    "evidence_diversity",
    "functional",
    "literature",
    "druggability",
    "evidence_completeness_count",
    "evidence_completeness_total",
    "n_other_diseases_positive",
  ];
  const lines = rows.map((t) =>
    [
      t.rank,
      t.gene_symbol,
      t.target_id,
      t.gene_name,
      t.score,
      t.sort_by,
      t.weighted_baseline_score,
      t.xgboost_score_held_out,
      t.evidence.genetics,
      t.evidence.evidence_diversity,
      t.evidence.functional,
      t.evidence.literature,
      t.evidence.druggability,
      t.evidence_completeness_count,
      t.evidence_completeness_total,
      t.n_other_diseases_positive,
    ]
      .map(csvCell)
      .join(","),
  );
  const comment = `# ${opts.diseaseName} (${opts.diseaseId}) — ${rows.length} of ${opts.totalCandidates} candidates — sorted by ${opts.sortBy} — not a full export`;
  const csv = [comment, header.join(","), ...lines].join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${opts.diseaseId}_ranking_${rows.length}-of-${opts.totalCandidates}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
