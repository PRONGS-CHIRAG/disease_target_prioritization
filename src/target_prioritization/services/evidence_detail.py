"""Browsable evidence detail for one (disease, target) — Context.md §21.

``evidence_summary.build_evidence_card`` answers "why did this target score
what it scored." This module answers the different question §21's target-detail
view also asks: "what is the evidence, concretely?" — which pathways by name,
which tissues at what expression, which interaction partners. Those facts reach
the feature table only as the aggregates ``path__n_pathways``, ``expr__*`` and
``net__*``; the named rows behind them are precomputed by ``detail_data`` into
three small artifacts under ``data/processed/``.

**Read strategy: scan, do not cache.** Unlike ``api/cache.py``'s frames, these
are never needed whole — one request wants one target. Measured on the real
artifacts, a filtered ``scan_parquet`` costs 1-2 ms against 77 MB of resident
memory to hold all three, so the row-group filter wins on both counts. The
artifacts are written sorted by ``target_id`` (``detail_data``) so that filter
prunes rather than scanning everything.

**Tissue relevance is not re-derived here.** ``expr__relevant_tissue_tpm`` was
produced by ``features.expression.match_relevant_tissue_columns``; this module
calls the same function, so the tissues the UI highlights are exactly the ones
the feature aggregated. Matching disease tissue names a second, subtly
different way would put a highlight next to a number that disagrees with it.

**A tissue list can be legitimately empty.** GTEx has no synovial-tissue data
at all, so rheumatoid arthritis has no matchable relevant tissue (milestone4.md
§1). That is returned as an explicit unmatched-tissue list rather than an empty
highlight, so the UI can say so — Context.md §32.3, absence of evidence is not
evidence of absence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import polars as pl

from target_prioritization.config import DiseaseSpec, load_diseases
from target_prioritization.data.open_targets import release_tag
from target_prioritization.detail_data import (
    INTERACTIONS_PATH,
    PARTNER_MIN_SCORE,
    PATHWAYS_PATH,
    TISSUES_PATH,
)
from target_prioritization.features.expression import match_relevant_tissue_columns
from target_prioritization.services.target_ranking import FEATURES_PATH

__all__ = [
    "EvidenceDetail",
    "InteractionPartner",
    "LiteratureSummary",
    "PathwayGroup",
    "PathwayRef",
    "TissueValue",
    "build_evidence_detail",
]

# Europe PMC's own search UI. A deep link is not literature retrieval
# (Context.md §30.1) — it hands the reader the query rather than answering it,
# which is why supporting literature stays in presentation.NOT_BUILDABLE.
_EUROPE_PMC_SEARCH = "https://europepmc.org/search?query="


@dataclass(slots=True)
class PathwayRef:
    """One Reactome pathway a target is annotated to."""

    pathway_id: str
    name: str
    url: str


@dataclass(slots=True)
class PathwayGroup:
    """Pathways for one root Reactome category.

    The number of groups equals ``path__n_pathways``, which counts distinct
    root categories rather than memberships (``features/pathways.py``).
    """

    root_pathway_id: str
    root_pathway_name: str
    pathways: list[PathwayRef] = field(default_factory=list)


@dataclass(slots=True)
class TissueValue:
    """Median TPM in one GTEx tissue, and whether this disease cares about it."""

    tissue: str
    median_tpm: float
    is_relevant: bool


@dataclass(slots=True)
class InteractionPartner:
    """A high-confidence STRING partner of the target."""

    target_id: str
    gene_symbol: str
    score: int
    #: Whether this partner is itself a candidate for the SELECTED disease.
    #: False means the UI must not link to its evidence page — there is no
    #: (disease, target) row for it, and /api/evidence would 404.
    is_candidate: bool


@dataclass(slots=True)
class LiteratureSummary:
    """What this repo actually has for literature: a co-mention score.

    No titles, dates or abstracts — see the module docstring of
    ``detail_data`` and ``presentation.NOT_BUILDABLE``.
    """

    europepmc_score: float | None
    europepmc_evidence_count: float | None
    search_url: str


@dataclass(slots=True)
class EvidenceDetail:
    """Everything §21's detail view can show for one (disease, target)."""

    disease_id: str
    disease_name: str
    target_id: str
    gene_symbol: str
    pathway_groups: list[PathwayGroup]
    n_root_categories: int
    tissues: list[TissueValue]
    relevant_tissues_matched: dict[str, list[str]]
    relevant_tissues_unmatched: list[str]
    partners: list[InteractionPartner]
    partner_min_score: int
    literature: LiteratureSummary
    dataset_version: str


def _disease(disease_id: str) -> DiseaseSpec:
    for spec in load_diseases().diseases:
        if spec.efo_id == disease_id:
            return spec
    raise KeyError(f"Unknown disease_id {disease_id!r}")


def _scan_for_target(path: Path, target_id: str) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/build_evidence_detail.py first."
        )
    return pl.scan_parquet(path).filter(pl.col("target_id") == target_id).collect()


def _pathway_groups(target_id: str) -> tuple[list[PathwayGroup], int]:
    rows = _scan_for_target(PATHWAYS_PATH, target_id)
    groups: list[PathwayGroup] = []
    for (root_id, root_name), group in rows.group_by(
        ["root_pathway_id", "root_pathway_name"], maintain_order=True
    ):
        groups.append(
            PathwayGroup(
                root_pathway_id=str(root_id),
                root_pathway_name=str(root_name),
                pathways=[
                    PathwayRef(
                        pathway_id=r["pathway_id"], name=r["pathway_name"], url=r["pathway_url"]
                    )
                    for r in group.iter_rows(named=True)
                ],
            )
        )
    groups.sort(key=lambda g: (-len(g.pathways), g.root_pathway_name))
    return groups, len(groups)


def _tissues(target_id: str, disease: DiseaseSpec) -> tuple[list[TissueValue], dict[str, list[str]], list[str]]:
    rows = _scan_for_target(TISSUES_PATH, target_id)
    all_tissues = rows.get_column("tissue").to_list()

    matched = match_relevant_tissue_columns(disease.relevant_tissues, all_tissues)
    relevant = {column for columns in matched.values() for column in columns}
    unmatched = [tissue for tissue, columns in matched.items() if not columns]

    # Already sorted by descending TPM in the artifact.
    values = [
        TissueValue(
            tissue=r["tissue"],
            median_tpm=float(r["median_tpm"]),
            is_relevant=r["tissue"] in relevant,
        )
        for r in rows.iter_rows(named=True)
    ]
    return values, {k: v for k, v in matched.items() if v}, unmatched


def _partners(target_id: str, disease_id: str) -> list[InteractionPartner]:
    rows = _scan_for_target(INTERACTIONS_PATH, target_id)
    if rows.is_empty():
        return []

    partner_ids = rows.get_column("partner_target_id").to_list()
    # Symbols are global; candidacy is per-disease. One scan answers both.
    lookup = (
        pl.scan_parquet(FEATURES_PATH)
        .filter(pl.col("target_id").is_in(partner_ids))
        .select("target_id", "gene_symbol", "disease_id")
        .collect()
    )
    symbols = dict(
        lookup.unique(subset=["target_id"], keep="first")
        .select("target_id", "gene_symbol")
        .iter_rows()
    )
    candidates = set(
        lookup.filter(pl.col("disease_id") == disease_id).get_column("target_id").to_list()
    )

    return [
        InteractionPartner(
            target_id=r["partner_target_id"],
            gene_symbol=symbols.get(r["partner_target_id"], r["partner_target_id"]),
            score=int(r["score"]),
            is_candidate=r["partner_target_id"] in candidates,
        )
        for r in rows.iter_rows(named=True)
    ]


def build_evidence_detail(
    disease_id: str,
    target_id: str,
    *,
    features: pl.DataFrame | None = None,
) -> EvidenceDetail:
    """Assemble the browsable detail for one (disease, target).

    Args:
        disease_id: An EFO/MONDO id configured in ``configs/diseases.yaml``.
        target_id: Unversioned Ensembl gene ID.
        features: Optional pre-loaded feature frame, the same injection seam
            ``rank_for_disease`` and ``build_evidence_card`` offer — used by
            the API to reuse its warmed frame and by tests to avoid disk.

    Returns:
        An :class:`EvidenceDetail`. Sections with no underlying rows come back
        empty rather than raising: a target can legitimately have no Reactome
        annotation (49% of ranked targets) or no high-confidence interaction.

    Raises:
        KeyError: *disease_id* is not configured, or the pair has no feature row.
        FileNotFoundError: A detail artifact has not been built.
    """
    disease = _disease(disease_id)

    row = (
        (features.lazy() if features is not None else pl.scan_parquet(FEATURES_PATH))
        .filter((pl.col("disease_id") == disease_id) & (pl.col("target_id") == target_id))
        .select("gene_symbol", "assoc_ds__europepmc_score", "assoc_ds__europepmc_evidence_count")
        .collect()
    )
    if row.is_empty():
        raise KeyError(f"No features for disease_id {disease_id!r} and target_id {target_id!r}")
    record = row.row(0, named=True)
    gene_symbol = record["gene_symbol"]

    groups, n_root_categories = _pathway_groups(target_id)
    tissues, matched, unmatched = _tissues(target_id, disease)

    return EvidenceDetail(
        disease_id=disease_id,
        disease_name=disease.name,
        target_id=target_id,
        gene_symbol=gene_symbol,
        pathway_groups=groups,
        n_root_categories=n_root_categories,
        tissues=tissues,
        relevant_tissues_matched=matched,
        relevant_tissues_unmatched=unmatched,
        partners=_partners(target_id, disease_id),
        partner_min_score=PARTNER_MIN_SCORE,
        literature=LiteratureSummary(
            europepmc_score=record["assoc_ds__europepmc_score"],
            europepmc_evidence_count=record["assoc_ds__europepmc_evidence_count"],
            search_url=_EUROPE_PMC_SEARCH + quote_plus(f'"{gene_symbol}" AND "{disease.name}"'),
        ),
        dataset_version=release_tag(),
    )
