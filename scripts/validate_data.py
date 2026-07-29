#!/usr/bin/env python
"""End-to-end validation of the downloaded datasets.

Checks that every source parses, that the four identifier joins actually
connect, and that the leakage denylist matches real columns in this release.

This is the "does the floor hold weight" check. Run it after every download and
whenever the Open Targets release is bumped — an upstream schema change shows
up here rather than as a strange number three stages downstream.

Usage:
    python scripts/validate_data.py
"""

from __future__ import annotations

import sys

import polars as pl
from rich.console import Console
from rich.table import Table

from target_prioritization.config import load_diseases, load_features
from target_prioritization.data import gtex, hgnc, open_targets, reactome, string_db
from target_prioritization.utils.logging import configure_logging

console = Console()

# Well-established Parkinson's genes (Context.md §4). Used as a smoke test:
# if these do not appear among the disease's associated targets, something is
# wrong with the join, not with the biology.
PARKINSONS_GENES = {
    "ENSG00000188906": "LRRK2",
    "ENSG00000145335": "SNCA",
    "ENSG00000177628": "GBA1",
    "ENSG00000185345": "PRKN",
    "ENSG00000158828": "PINK1",
}


def main() -> int:
    configure_logging()
    results: list[tuple[str, bool, str]] = []

    def check(name: str, fn) -> None:
        try:
            detail = fn()
            results.append((name, True, detail))
            console.print(f"[green]✓[/green] {name}: {detail}")
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            console.print(f"[red]✗[/red] {name}: {type(exc).__name__}: {exc}")

    console.rule("Open Targets")
    con = open_targets.connect()

    def _ot_targets() -> str:
        n = con.execute(
            f"SELECT count(*) FROM read_parquet('{open_targets.dataset_glob('target')}')"
        ).fetchone()[0]
        return f"{n:,} targets"

    def _ot_diseases() -> str:
        n = con.execute(
            f"SELECT count(*) FROM read_parquet('{open_targets.dataset_glob('disease')}')"
        ).fetchone()[0]
        return f"{n:,} diseases"

    def _ot_assoc() -> str:
        n = con.execute(
            "SELECT count(*) FROM read_parquet"
            f"('{open_targets.dataset_glob('association_by_datasource_direct')}')"
        ).fetchone()[0]
        return f"{n:,} association rows"

    check("open_targets/target", _ot_targets)
    check("open_targets/disease", _ot_diseases)
    check("open_targets/association_by_datasource_direct", _ot_assoc)

    console.rule("Disease resolution")

    def _diseases_resolved() -> str:
        config = load_diseases()
        if config.unresolved:
            raise ValueError(
                f"{len(config.unresolved)} unresolved: "
                f"{', '.join(d.key for d in config.unresolved)}. "
                "Run scripts/resolve_diseases.py"
            )
        return f"{len(config.resolved)}/{len(config.diseases)} resolved against release {config.resolved_against_release}"

    def _diseases_have_targets() -> str:
        config = load_diseases()
        glob = open_targets.dataset_glob("association_by_datasource_direct")
        rows = []
        for spec in config.resolved:
            n = con.execute(
                f"SELECT count(DISTINCT targetId) FROM read_parquet('{glob}') WHERE diseaseId = ?",
                [spec.efo_id],
            ).fetchone()[0]
            rows.append((spec.key, spec.efo_id, n))

        empty = [r for r in rows if r[2] == 0]
        table = Table(show_header=True, header_style="bold")
        table.add_column("Disease")
        table.add_column("ID")
        table.add_column("Targets", justify="right")
        for key, disease_id, n in rows:
            table.add_row(key, disease_id, f"{n:,}" if n else "[red]0[/red]")
        console.print(table)

        if empty:
            raise ValueError(f"{len(empty)} disease(s) have no associated targets")
        return f"all {len(rows)} diseases have associated targets"

    check("diseases resolved", _diseases_resolved)
    check("diseases have candidate targets", _diseases_have_targets)

    console.rule("Milestone 1 smoke test — Parkinson's disease")

    def _parkinsons_genes() -> str:
        spec = load_diseases().milestone_1_disease()
        glob = open_targets.dataset_glob("association_by_datasource_direct")
        found = con.execute(
            f"SELECT DISTINCT targetId FROM read_parquet('{glob}') WHERE diseaseId = ?",
            [spec.efo_id],
        ).fetchall()
        found_ids = {r[0] for r in found}
        hits = {g: s for g, s in PARKINSONS_GENES.items() if g in found_ids}
        missing = set(PARKINSONS_GENES) - set(hits)
        if missing:
            raise ValueError(f"known genes absent: {[PARKINSONS_GENES[g] for g in missing]}")
        return f"all {len(hits)} known genes present ({', '.join(sorted(hits.values()))})"

    check("known Parkinson's genes are candidates", _parkinsons_genes)

    console.rule("Identifier joins")

    def _gtex() -> str:
        frame = gtex.load_median_tpm()
        versioned = frame.filter(pl.col("ensembl_gene_id").str.contains(r"\.\d+$")).height
        if versioned:
            raise ValueError(f"{versioned} gene IDs still carry a version suffix")
        return (
            f"{frame.height:,} genes x {len(gtex.tissue_columns(frame))} tissues, IDs unversioned"
        )

    def _gtex_join() -> str:
        expr = gtex.load_median_tpm().select("ensembl_gene_id")
        glob = open_targets.dataset_glob("target")
        ot = con.execute(f"SELECT id FROM read_parquet('{glob}')").fetchall()
        ot_ids = pl.DataFrame({"ensembl_gene_id": [r[0] for r in ot]})
        overlap = expr.join(ot_ids, on="ensembl_gene_id", how="inner").height
        if overlap < 10_000:
            raise ValueError(f"only {overlap:,} genes join to Open Targets — expected >10,000")
        return f"{overlap:,} genes join to Open Targets targets"

    def _reactome() -> str:
        frame, report = reactome.load_ensembl_to_pathway()
        species = frame.get_column("species").unique().to_list()
        if species != ["Homo sapiens"]:
            raise ValueError(f"non-human species survived the filter: {species}")
        return (
            f"{frame.height:,} human gene-pathway rows "
            f"({report.total:,} before filtering, {report.unmapped:,} dropped)"
        )

    def _hgnc() -> str:
        lookup, _ = hgnc.load_symbol_lookup()
        # The rename that motivated including previous symbols at all.
        park2 = lookup.filter(pl.col("symbol") == "PARK2")
        if not park2.height:
            raise ValueError("retired symbol PARK2 did not resolve")
        gene = park2.get_column("ensembl_gene_id").to_list()[0]
        if gene != "ENSG00000185345":
            raise ValueError(f"PARK2 resolved to {gene}, expected PRKN's ENSG00000185345")
        return f"{lookup.height:,} symbol rows; retired PARK2 -> {gene} (PRKN)"

    def _string() -> str:
        edges, report = string_db.load_gene_level_edges()
        if edges.height < 100_000:
            raise ValueError(f"only {edges.height:,} gene-level edges — expected >100,000")
        return (
            f"{edges.height:,} gene-level edges; "
            f"{report.mapped:,}/{report.total:,} proteins mapped to genes "
            f"({report.mapped_fraction:.1%})"
        )

    check("GTEx parses and IDs are unversioned", _gtex)
    check("GTEx joins to Open Targets", _gtex_join)
    check("Reactome filtered to human", _reactome)
    check("HGNC resolves retired symbols", _hgnc)
    check("STRING ENSP -> ENSG network", _string)

    console.rule("Leakage guard")

    def _denylist_matches_reality() -> str:
        config = load_features()
        glob = open_targets.dataset_glob("association_by_datasource_direct")
        datasources = [
            r[0]
            for r in con.execute(
                f"SELECT DISTINCT aggregationValue FROM read_parquet('{glob}')"
            ).fetchall()
        ]
        columns = [f"assoc_ds__{d}_score" for d in datasources] + [
            "prio__max_clinical_stage",
            "assoc_overall__score",
        ]
        violations = config.leakage_guard.find_violations(columns)
        stale = config.leakage_guard.unmatched_required_rules(columns)
        if stale:
            raise ValueError(
                f"required denylist rule(s) match nothing in this release: "
                f"{[r.id for r in stale]} — an upstream rename is the usual cause"
            )
        blocked = sorted({c for cols in violations.values() for c in cols})
        return f"{len(violations)} rule(s) active, blocking: {', '.join(blocked)}"

    check("denylist matches real datasources", _denylist_matches_reality)

    con.close()

    failures = [r for r in results if not r[1]]
    console.rule("Summary")
    if failures:
        console.print(f"[red]{len(failures)}/{len(results)} checks failed.[/red]")
        return 1
    console.print(f"[green]All {len(results)} checks passed.[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
