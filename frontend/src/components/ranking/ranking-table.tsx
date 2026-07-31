"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowUpDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { CompletenessBadge } from "@/components/completeness-badge";
import { EvidenceValue } from "@/components/evidence-value";
import { ScoreStrip } from "@/components/score-strip";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { linkedWeightsQueryString } from "@/hooks/use-linked-weights";
import type { RankedTarget } from "@/hooks/use-rank";
import type { components } from "@/lib/api-types";

const columnHelper = createColumnHelper<RankedTarget>();

const MAX_COMPARE = 4;

export function RankingTable({
  targets,
  diseaseId,
  dimensionLabels,
  weightsUsed,
  selected,
  onToggleSelected,
  onRowsChange,
}: {
  targets: RankedTarget[];
  diseaseId: string;
  dimensionLabels: components["schemas"]["MetaResponse"]["dimension_labels"];
  /** The server-normalized weights behind the CURRENT response — the mini
   * score strip multiplies each raw dim__ value by its weight so the
   * stack genuinely sums to `weighted_baseline_score` (the same
   * contrib__ = dim.fill_null(0) * weight formula models/baseline.py
   * uses), not just a proportional display of raw evidence strength,
   * which would misrepresent a high-value/low-weight dimension as more
   * influential than it actually is. */
  weightsUsed: Record<string, number>;
  selected: Set<string>;
  onToggleSelected: (targetId: string) => void;
  /** Reports the currently sorted/visible rows up so the page can build a
   * CSV export that matches exactly what's on screen. */
  onRowsChange?: (rows: RankedTarget[]) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "select",
        header: () => <span className="sr-only">Compare</span>,
        cell: ({ row }) => {
          const id = row.original.target_id;
          const isSelected = selected.has(id);
          const disabled = !isSelected && selected.size >= MAX_COMPARE;
          return (
            <Checkbox
              checked={isSelected}
              disabled={disabled}
              onCheckedChange={() => onToggleSelected(id)}
              aria-label={`Select ${row.original.gene_symbol} for comparison`}
            />
          );
        },
      }),
      columnHelper.accessor("rank", {
        header: "Rank",
        cell: (info) => <span className="font-mono tabular-nums">{info.getValue()}</span>,
      }),
      columnHelper.accessor("gene_symbol", {
        header: "Gene",
        cell: (info) => (
          <div>
            <div className="font-medium">{info.getValue()}</div>
            <div className="font-mono text-[11px] text-muted-foreground">
              {info.row.original.target_id}
            </div>
          </div>
        ),
      }),
      columnHelper.accessor("score", {
        header: "Score (active sort)",
        cell: (info) => {
          const t = info.row.original;
          // contrib__<dim> = dim.fill_null(0) * weight (models/baseline.py)
          // — null IS correctly 0 here, by the formula's own definition,
          // not a display placeholder standing in for missing data.
          const contribution = (dim: keyof typeof t.evidence) => (weightsUsed[dim] ?? 0) * (t.evidence[dim] ?? 0);
          const segments = [
            { key: "genetics" as const, label: dimensionLabels.genetics ?? "Genetics", value: contribution("genetics") },
            {
              key: "evidence_diversity" as const,
              label: dimensionLabels.evidence_diversity ?? "Evidence diversity",
              value: contribution("evidence_diversity"),
            },
            { key: "functional" as const, label: dimensionLabels.functional ?? "Functional", value: contribution("functional") },
            { key: "literature" as const, label: dimensionLabels.literature ?? "Literature", value: contribution("literature") },
            {
              key: "druggability" as const,
              label: dimensionLabels.druggability ?? "Druggability",
              value: contribution("druggability"),
            },
          ];
          return (
            <div className="w-32 space-y-1">
              <span className="font-mono text-sm tabular-nums">{info.getValue().toFixed(4)}</span>
              <ScoreStrip segments={segments} size="micro" />
            </div>
          );
        },
      }),
      columnHelper.accessor("weighted_baseline_score", {
        header: "Weighted baseline",
        cell: (info) => <span className="font-mono tabular-nums">{info.getValue().toFixed(4)}</span>,
      }),
      columnHelper.accessor("xgboost_score_held_out", {
        header: "XGBoost (held-out)",
        cell: (info) => <EvidenceValue value={info.getValue()} digits={4} />,
      }),
      columnHelper.accessor((row) => row.evidence.genetics, {
        id: "genetics",
        header: "Genetics",
        cell: (info) => <EvidenceValue value={info.getValue()} />,
      }),
      columnHelper.accessor((row) => row.evidence.functional, {
        id: "functional",
        header: "Functional",
        cell: (info) => <EvidenceValue value={info.getValue()} />,
      }),
      columnHelper.accessor((row) => row.evidence.literature, {
        id: "literature",
        header: "Literature",
        cell: (info) => <EvidenceValue value={info.getValue()} />,
      }),
      columnHelper.accessor((row) => row.evidence.druggability, {
        id: "druggability",
        header: "Druggability",
        cell: (info) => <EvidenceValue value={info.getValue()} />,
      }),
      columnHelper.accessor("evidence_completeness", {
        header: "Evidence completeness",
        cell: (info) => (
          <CompletenessBadge
            count={info.row.original.evidence_completeness_count}
            total={info.row.original.evidence_completeness_total}
          />
        ),
      }),
      columnHelper.accessor("n_other_diseases_positive", {
        header: "Positive in N other diseases",
        cell: (info) => <EvidenceValue value={info.getValue()} digits={0} />,
      }),
      columnHelper.display({
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <Button asChild variant="ghost" size="sm" className="h-7 text-xs">
            <Link
              href={`/evidence?disease=${encodeURIComponent(diseaseId)}&target=${encodeURIComponent(row.original.target_id)}&${linkedWeightsQueryString(weightsUsed)}`}
            >
              View evidence
            </Link>
          </Button>
        ),
      }),
    ],
    [selected, onToggleSelected, dimensionLabels, diseaseId, weightsUsed],
  );

  const table = useReactTable({
    data: targets,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  // A setState in the parent triggered from render (useMemo) is exactly
  // the anti-pattern React warns about — this has to run post-commit.
  useEffect(() => {
    onRowsChange?.(table.getRowModel().rows.map((r) => r.original));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targets, sorting]);

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id} className="whitespace-nowrap">
                  {header.isPlaceholder ? null : header.column.getCanSort() ? (
                    <button
                      type="button"
                      className="flex items-center gap-1 hover:text-foreground"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <ArrowUpDown className="size-3 text-muted-foreground" aria-hidden />
                    </button>
                  ) : (
                    flexRender(header.column.columnDef.header, header.getContext())
                  )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export { MAX_COMPARE };
