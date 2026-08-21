"""Pathway features (Context.md §14.3, §10.4).

Built from Reactome, filtered to human (that filter drops ~95% of the source
file — see data/reactome.py).

Caution: Reactome is a hierarchy, so a naive "number of pathways this gene
belongs to" counts the same biology repeatedly at several levels of
granularity, and rewards well-annotated genes rather than biologically central
ones. ``ReactomePathwaysRelation.txt`` is downloaded so features can be
computed at a chosen depth instead. :func:`build_pathway_features` uses it to
collapse each gene's pathway memberships to the count of distinct ROOT
categories they map to — a gene annotated to fifty leaf pathways under two
root categories scores 2, not 50.

Milestone 4 (see milestone4_plan.md §2.1) does not wire
``path__overlap_with_known_disease_genes`` or
``path__n_disease_relevant_pathways`` into the feature table: both need a
per-disease "known disease genes" seed set, and this repo has no
leakage-reviewed definition of one for all ten configured diseases (the only
precedent — five hardcoded Parkinson's genes in ``milestone1.py`` — is
documented there as a pipeline sanity check, not a reusable feature input).
:func:`pathway_overlap_with_known_genes` is implemented and tested below so
that gap is isolated to "what gene list to pass", not to whether the
computation works.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import polars as pl

from target_prioritization.config import FeaturesConfig
from target_prioritization.data.reactome import load_ensembl_to_pathway, load_pathway_relations
from target_prioritization.utils.logging import get_logger, log_dropped

__all__ = [
    "DIMENSION_COLUMN",
    "MISSING_COLUMN",
    "N_PATHWAYS_COLUMN",
    "OVERLAP_COLUMN",
    "PATHWAY_COUNT_SATURATION",
    "build_pathway_features",
    "pathway_memberships",
    "pathway_overlap_with_known_genes",
]

log = get_logger(__name__)

N_PATHWAYS_COLUMN = "path__n_pathways"
MISSING_COLUMN = "missing__pathways"
OVERLAP_COLUMN = "path__overlap_with_known_disease_genes"

# dim__pathways (configs/model.yaml's baseline_weights "pathway_score",
# Context.md §17.1) — a saturating transform of root-category count, same
# shape as dim__evidence_diversity (genetics.py). Illustrative, like every
# baseline_weights term (model.yaml's own caveat): most genes touch a
# handful of root categories, so 5 is a documented, not tuned, ceiling.
PATHWAY_COUNT_SATURATION = 5
DIMENSION_COLUMN = "dim__pathways"


@lru_cache(maxsize=1)
def _load_human_pathway_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Cached ``(gene -> pathway, parent -> child)`` frames.

    Both are per-gene/per-pathway facts, not per-disease ones, but
    :func:`build_pathway_features` is called once per disease by
    ``features.build_features.build_feature_table``. Caching here means a
    ten-disease run parses the ~178k-row human Reactome mapping once instead
    of ten times, without changing any call signature upstream.
    """
    mapping, report = load_ensembl_to_pathway()
    if report is not None:
        report.log()
    relations = load_pathway_relations()
    return mapping, relations


def _build_root_finder(relations: pl.DataFrame) -> Callable[[str], str]:
    """Return a memoized ``pathway_id -> root_pathway_id`` function.

    A pathway with no incoming parent edge in *relations* is a root; walking
    parent pointers from any other pathway terminates there. Reactome's
    hierarchy is a per-species forest, not expected to contain cycles — a
    pathway ID revisited mid-walk is treated as its own root as a pragmatic
    fallback, not silently looped on forever.
    """
    parent_of: dict[str, str] = dict(
        zip(
            relations.get_column("child_pathway_id").to_list(),
            relations.get_column("parent_pathway_id").to_list(),
            strict=True,
        )
    )
    cache: dict[str, str] = {}

    def root_of(pathway_id: str) -> str:
        if pathway_id in cache:
            return cache[pathway_id]
        visited: list[str] = []
        current = pathway_id
        while current in parent_of and current not in cache and current not in visited:
            visited.append(current)
            current = parent_of[current]
        root = cache.get(current, current)
        for node in visited:
            cache[node] = root
        cache[pathway_id] = root
        return root

    return root_of


def _with_root_pathway(mapping: pl.DataFrame, relations: pl.DataFrame) -> pl.DataFrame:
    root_of = _build_root_finder(relations)
    return mapping.with_columns(
        pl.col("pathway_id").map_elements(root_of, return_dtype=pl.String).alias("root_pathway_id")
    )


def pathway_memberships(gene_ids: list[str]) -> pl.DataFrame:
    """Reactome memberships for *gene_ids*, each row carrying its root category.

    The single source of truth for "which pathways is this gene in, and which
    root category does each roll up to." :func:`build_pathway_features` counts
    distinct ``root_pathway_id`` here to produce
    :data:`N_PATHWAYS_COLUMN`; ``detail_data.build_target_pathways`` renders
    the same rows as browsable evidence. Extracted so the number shown in the
    UI and the list shown beneath it cannot disagree — a displayed list of
    forty pathways under a count of twenty-two would read as a bug in the
    score, not a difference in what is being counted.

    No filtering on ``evidence_code``: inferred (:data:`INFERRED_EVIDENCE_CODE`)
    annotations are kept, because the feature has always counted them and
    dropping them here would silently change the score.

    Args:
        gene_ids: Unversioned Ensembl gene IDs.

    Returns:
        The human Reactome mapping restricted to *gene_ids*, with a
        ``root_pathway_id`` column added. Empty (with the mapping's schema)
        when *gene_ids* is empty.
    """
    mapping, relations = _load_human_pathway_data()
    relevant = mapping.filter(pl.col("ensembl_gene_id").is_in(gene_ids))
    return _with_root_pathway(relevant, relations)


def pathway_overlap_with_known_genes(
    gene_ids: list[str],
    known_disease_genes: list[str],
) -> pl.DataFrame:
    """Share of a gene's root pathway categories shared with *known_disease_genes*.

    A candidate sitting in the same pathways as established disease genes is a
    more plausible target than one that shares none — the mechanism-level
    version of guilt by association. Overlap is computed on ROOT categories
    (see module docstring), not raw pathway IDs, for the same reason
    :func:`build_pathway_features` collapses to roots: two genes sharing one
    specific leaf reaction are more informative than two genes both merely
    tagged under a huge top-level category, but two genes sharing only a
    top-level category are still weak evidence, not none.

    If a candidate in *gene_ids* is itself present in *known_disease_genes*,
    its own root categories trivially overlap at 1.0 — callers doing
    guilt-by-association should exclude the candidate from
    *known_disease_genes* first (leave-one-out); this function does not do
    that itself, since it has no way to know which caller-supplied gene is
    "the one being scored" versus "a seed".

    Args:
        gene_ids: Unversioned Ensembl gene IDs to score.
        known_disease_genes: Unversioned Ensembl gene IDs treated as the seed
            set of established disease genes.

    Returns:
        ``target_id``, :data:`OVERLAP_COLUMN` in ``[0, 1]`` — null if the
        gene has no Reactome pathway annotation at all, 0.0 (not null) if it
        has pathway annotations but none overlap the seed set's root
        categories.
    """
    result_schema = {"target_id": pl.String, OVERLAP_COLUMN: pl.Float64}
    if not gene_ids:
        return pl.DataFrame(schema=result_schema)
    if not known_disease_genes:
        return pl.DataFrame({"target_id": gene_ids}).with_columns(
            pl.lit(None, dtype=pl.Float64).alias(OVERLAP_COLUMN)
        )

    mapping, relations = _load_human_pathway_data()
    relevant = set(gene_ids) | set(known_disease_genes)
    mapping = mapping.filter(pl.col("ensembl_gene_id").is_in(list(relevant)))
    with_roots = _with_root_pathway(mapping, relations)

    known_roots: set[str] = set(
        with_roots.filter(pl.col("ensembl_gene_id").is_in(known_disease_genes))
        .get_column("root_pathway_id")
        .unique()
        .to_list()
    )

    def overlap(roots: pl.Series) -> float | None:
        values = roots.to_list()
        if not values:
            return None
        return sum(1 for r in values if r in known_roots) / len(values)

    gene_roots = (
        with_roots.filter(pl.col("ensembl_gene_id").is_in(gene_ids))
        .group_by("ensembl_gene_id")
        .agg(pl.col("root_pathway_id").unique().alias("roots"))
        .with_columns(pl.col("roots").map_elements(overlap, return_dtype=pl.Float64).alias(OVERLAP_COLUMN))
        .rename({"ensembl_gene_id": "target_id"})
        .select("target_id", OVERLAP_COLUMN)
    )

    return pl.DataFrame({"target_id": gene_ids}, schema={"target_id": pl.String}).join(
        gene_roots, on="target_id", how="left"
    )


def build_pathway_features(
    gene_ids: list[str],
    config: FeaturesConfig | None = None,
) -> pl.DataFrame:
    """Derive pathway features. See ``groups.pathways`` in features.yaml.

    ``path__n_pathways`` counts distinct root Reactome categories per gene
    (module docstring), not raw membership rows. ``config`` is accepted for
    signature symmetry with the other feature builders and future
    config-driven parameters; nothing here reads from it today.

    Args:
        gene_ids: Unversioned Ensembl gene IDs.
        config: Unused today; accepted for symmetry with other builders.

    Returns:
        ``target_id``, :data:`N_PATHWAYS_COLUMN`, :data:`DIMENSION_COLUMN`
        (saturating transform of the count, in ``[0, 1]``),
        :data:`MISSING_COLUMN`. A gene absent from the human Reactome
        mapping gets a null count, never a zero (Context.md §32.3 —
        absence of evidence is not evidence of absence).
    """
    del config  # unused today; kept for call-site symmetry (see docstring)
    result_schema = {
        "target_id": pl.String,
        N_PATHWAYS_COLUMN: pl.UInt32,
        DIMENSION_COLUMN: pl.Float64,
        MISSING_COLUMN: pl.Int8,
    }
    if not gene_ids:
        return pl.DataFrame(schema=result_schema)

    with_roots = pathway_memberships(gene_ids)

    counts = (
        with_roots.group_by("ensembl_gene_id")
        .agg(pl.col("root_pathway_id").n_unique().cast(pl.UInt32).alias(N_PATHWAYS_COLUMN))
        .rename({"ensembl_gene_id": "target_id"})
    )

    result = pl.DataFrame({"target_id": gene_ids}, schema={"target_id": pl.String}).join(
        counts, on="target_id", how="left"
    )
    result = result.with_columns(
        (pl.col(N_PATHWAYS_COLUMN) / PATHWAY_COUNT_SATURATION).clip(0.0, 1.0).alias(DIMENSION_COLUMN)
    )

    log_dropped(
        log,
        stage="pathway_coverage",
        reason="gene has no Reactome pathway annotation",
        count=result.filter(pl.col(N_PATHWAYS_COLUMN).is_null()).height,
        total=len(gene_ids),
    )

    return result.with_columns(pl.col(N_PATHWAYS_COLUMN).is_null().cast(pl.Int8).alias(MISSING_COLUMN))
