"""Browsable evidence detail precompute (Context.md §21).

Context.md §21's target-detail view asks for *relevant pathways*, *tissue
expression* and a *protein interaction summary* as things a reader can look
at, not only as the aggregate numbers ``path__n_pathways``, ``expr__*`` and
``net__*`` that reach ``disease_target_features.parquet``. The underlying
facts are already downloaded — Reactome carries pathway names, GTEx carries
per-tissue median TPM, STRING carries scored interaction pairs — but they
live only in ``data/raw/``, which is ~3 GB and excluded from the container
image by ``.dockerignore``. Exactly the problem ``app_data.py`` solves for
disease descriptions, and solved the same way: bake the display facts, once,
into small artifacts under ``data/processed/`` that ship inside the image.

**Presentation data, not features.** Nothing here is joined into a model's
feature matrix, so nothing here needs leakage review or a retrain. Pathway
*names* as a feature would need both; pathway names as display evidence need
neither. ``services.evidence_detail`` reads these artifacts; no training code
imports this module.

**Why the pathway artifact is grouped by root category.** ``path__n_pathways``
counts distinct *root* Reactome categories, not raw membership rows
(``features/pathways.py``'s module docstring). A flat list of every membership
would show forty rows under a count of twenty-two and read as a bug in the
score. Both sides now come from ``features.pathways.pathway_memberships``, so
the number of root groups rendered equals the counted feature by construction.

**What this module deliberately does not deliver.** §21's fourth detail item,
supporting literature, is not here. The only literature signal this repo has
downloaded is Open Targets' EuropePMC co-mention *score* — there are no
titles, dates or abstracts to browse, and retrieving them is Context.md
§30.1, a separate feature needing a new data source. It is declared in
``presentation.NOT_BUILDABLE`` instead, the same mechanism already used for
direction of effect and calibrated confidence, so the UI states the absence
rather than rendering an empty panel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import polars as pl

from target_prioritization.data import gtex, string_db
from target_prioritization.data.open_targets import release_tag
from target_prioritization.data.reactome import load_pathway_names
from target_prioritization.features.pathways import pathway_memberships
from target_prioritization.utils.logging import get_logger, log_dropped
from target_prioritization.utils.paths import DATA_PROCESSED

__all__ = [
    "INTERACTIONS_PATH",
    "PARTNERS_PER_TARGET",
    "PARTNER_MIN_SCORE",
    "PATHWAYS_PATH",
    "TISSUES_PATH",
    "build_detail_data",
    "build_target_interactions",
    "build_target_pathways",
    "build_target_tissue_expression",
]

log = get_logger(__name__)

PATHWAYS_PATH = DATA_PROCESSED / "target_pathways.parquet"
TISSUES_PATH = DATA_PROCESSED / "target_tissue_expression.parquet"
INTERACTIONS_PATH = DATA_PROCESSED / "target_interactions.parquet"

# STRING's "high confidence" band. `net__*` features are built at MEDIUM (400)
# because centrality over a sparser graph is a different measurement; a
# displayed partner list is a different job, where a reader scanning fifteen
# names is better served by fewer, stronger edges. The threshold is recorded
# in provenance because it changes what is shown.
PARTNER_MIN_SCORE = string_db.HIGH_CONFIDENCE

# Enough to characterize a hub without turning the panel into a data dump.
PARTNERS_PER_TARGET = 15


def build_target_pathways(target_ids: list[str]) -> pl.DataFrame:
    """Reactome memberships per target, each row tagged with its root category.

    Args:
        target_ids: Unversioned Ensembl gene IDs to restrict the output to.

    Returns:
        ``target_id``, ``root_pathway_id``, ``root_pathway_name``,
        ``pathway_id``, ``pathway_name``, ``pathway_url``, sorted by
        ``target_id`` then root then pathway name. One row per
        (target, pathway); a target with no Reactome annotation is absent
        rather than present-with-nulls, which the service reads as "no
        evidence recorded" (Context.md §32.3).
    """
    schema = {
        "target_id": pl.String,
        "root_pathway_id": pl.String,
        "root_pathway_name": pl.String,
        "pathway_id": pl.String,
        "pathway_name": pl.String,
        "pathway_url": pl.String,
    }
    if not target_ids:
        return pl.DataFrame(schema=schema)

    memberships = pathway_memberships(target_ids)
    if memberships.is_empty():
        return pl.DataFrame(schema=schema)

    # Root IDs resolve to pathways that a gene need not itself be annotated
    # to, so root names come from the pathway dictionary, not from the
    # membership rows.
    names = load_pathway_names().select(
        pl.col("pathway_id").alias("root_pathway_id"),
        pl.col("pathway_name").alias("root_pathway_name"),
    )

    result = (
        memberships.select(
            pl.col("ensembl_gene_id").alias("target_id"),
            "root_pathway_id",
            "pathway_id",
            "pathway_name",
            "pathway_url",
        )
        # The mapping lists a (gene, pathway) pair once per evidence code.
        .unique(subset=["target_id", "pathway_id"], keep="first")
        .join(names.unique(subset=["root_pathway_id"]), on="root_pathway_id", how="left")
        .with_columns(pl.col("root_pathway_name").fill_null(pl.col("root_pathway_id")))
        .select(*schema.keys())
        .sort(["target_id", "root_pathway_name", "pathway_name"])
    )

    log_dropped(
        log,
        stage="detail_pathway_coverage",
        reason="gene has no Reactome pathway annotation",
        count=len(target_ids) - result.get_column("target_id").n_unique(),
        total=len(target_ids),
    )
    return result


def build_target_tissue_expression(target_ids: list[str]) -> pl.DataFrame:
    """GTEx median TPM per target per tissue, in long form.

    Every tissue is kept rather than a top-N slice: the panel's job is to let
    a reader see that a gene is broadly expressed or sharply restricted, and a
    truncated list cannot show the second thing. ``expr__tissue_specificity``
    summarizes the same rows as one number.

    Args:
        target_ids: Unversioned Ensembl gene IDs to restrict the output to.

    Returns:
        ``target_id``, ``tissue``, ``median_tpm`` (Float32 — GTEx medians
        carry nothing like Float64 precision and this is the largest of the
        three artifacts), sorted by ``target_id`` then descending TPM so the
        service can slice the top tissues without re-sorting.
    """
    schema = {"target_id": pl.String, "tissue": pl.String, "median_tpm": pl.Float32}
    if not target_ids:
        return pl.DataFrame(schema=schema)

    long = gtex.load_median_tpm_long()
    result = (
        long.filter(pl.col("ensembl_gene_id").is_in(target_ids))
        .select(
            pl.col("ensembl_gene_id").alias("target_id"),
            "tissue",
            pl.col("median_tpm").cast(pl.Float32),
        )
        .sort(["target_id", "median_tpm"], descending=[False, True])
    )

    log_dropped(
        log,
        stage="detail_expression_coverage",
        reason="gene absent from the GTEx median-TPM matrix",
        count=len(target_ids) - result.get_column("target_id").n_unique(),
        total=len(target_ids),
    )
    return result


def build_target_interactions(
    target_ids: list[str],
    *,
    min_score: int = PARTNER_MIN_SCORE,
    top_n: int = PARTNERS_PER_TARGET,
) -> pl.DataFrame:
    """Top scoring STRING partners per target, as a symmetric relation.

    ``load_gene_level_edges`` deduplicates ``(A, B)`` and ``(B, A)`` into one
    undirected row, which is right for counting degree and wrong for a lookup
    keyed on one endpoint — B would be missing from A's partner list half the
    time. Both directions are re-expanded here before ranking.

    Partners are restricted to *target_ids*: a partner outside the app's
    universe has no gene symbol to show and no page to link to, so it would
    render as an unusable row. The count dropped is logged, since it means the
    list is "top partners among ranked targets," not "top partners in STRING."

    Args:
        target_ids: Unversioned Ensembl gene IDs, used for both endpoints.
        min_score: Minimum STRING combined score.
        top_n: Partners kept per target, highest score first.

    Returns:
        ``target_id``, ``partner_target_id``, ``score`` (UInt16), sorted by
        ``target_id`` then descending score. Gene symbols are resolved by the
        service from the feature table, the app's authoritative symbol source.
    """
    schema = {"target_id": pl.String, "partner_target_id": pl.String, "score": pl.UInt16}
    if not target_ids:
        return pl.DataFrame(schema=schema)

    edges, report = string_db.load_gene_level_edges(min_score=min_score)
    report.log()

    both_directions = pl.concat(
        [
            edges.select(
                pl.col("gene1").alias("target_id"),
                pl.col("gene2").alias("partner_target_id"),
                "score",
            ),
            edges.select(
                pl.col("gene2").alias("target_id"),
                pl.col("gene1").alias("partner_target_id"),
                "score",
            ),
        ]
    )

    in_universe = both_directions.filter(
        pl.col("target_id").is_in(target_ids) & pl.col("partner_target_id").is_in(target_ids)
    )
    log_dropped(
        log,
        stage="detail_interaction_universe",
        reason="one endpoint is not a ranked target in the feature table",
        count=both_directions.height - in_universe.height,
        total=both_directions.height,
    )

    return (
        in_universe.sort(["target_id", "score"], descending=[False, True])
        .group_by("target_id", maintain_order=True)
        .head(top_n)
        .select(
            "target_id",
            "partner_target_id",
            pl.col("score").cast(pl.UInt16),
        )
        .sort(["target_id", "score"], descending=[False, True])
    )


def build_detail_data(
    target_ids: list[str],
) -> tuple[dict[str, pl.DataFrame], dict[str, Any]]:
    """Build all three detail artifacts and their shared provenance.

    Args:
        target_ids: Every distinct ``target_id`` in the feature table — the
            set the API can be asked about.

    Returns:
        ``(frames, provenance)``, where *frames* is keyed by output filename
        stem and *provenance* records the release, the parameters that change
        what is shown, and per-artifact coverage.
    """
    pathways = build_target_pathways(target_ids)
    tissues = build_target_tissue_expression(target_ids)
    interactions = build_target_interactions(target_ids)

    n_targets = len(target_ids)
    provenance = {
        "dataset_version": release_tag(),
        "generated_at": datetime.now(UTC).isoformat(),
        "n_targets_requested": n_targets,
        "parameters": {
            "partner_min_score": PARTNER_MIN_SCORE,
            "partners_per_target": PARTNERS_PER_TARGET,
        },
        "artifacts": {
            "target_pathways": {
                "rows": pathways.height,
                "targets_covered": pathways.get_column("target_id").n_unique(),
                "root_categories": pathways.get_column("root_pathway_id").n_unique(),
            },
            "target_tissue_expression": {
                "rows": tissues.height,
                "targets_covered": tissues.get_column("target_id").n_unique(),
                "tissues": tissues.get_column("tissue").n_unique(),
            },
            "target_interactions": {
                "rows": interactions.height,
                "targets_covered": interactions.get_column("target_id").n_unique(),
            },
        },
        "notes": (
            "Presentation data for Context.md §21's target-detail view; never a model "
            "feature. Pathway rows are grouped by root category so their group count "
            "equals path__n_pathways. Supporting literature is NOT included — see "
            "presentation.NOT_BUILDABLE and Context.md §30.1."
        ),
    }
    return (
        {
            "target_pathways": pathways,
            "target_tissue_expression": tissues,
            "target_interactions": interactions,
        },
        provenance,
    )
