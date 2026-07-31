"""Tissue-expression features (Context.md §14.4, §10.6).

Built from GTEx v10 median TPM. The disease-relevant tissues come from
``relevant_tissues`` in ``configs/diseases.yaml`` — a Parkinson's target is more
interesting if it is expressed in brain than if it is merely expressed
somewhere.

Expression also carries safety signal in the opposite direction: a gene
expressed highly across many healthy tissues is a broader intervention and a
larger risk surface (Context.md §14.7).

``configs/diseases.yaml``'s tissue names are free text (``"sigmoid colon"``,
``"adipose tissue"``) and don't line up with GTEx's underscore-joined column
names (``Colon_Sigmoid``, ``Adipose_Subcutaneous``) under naive substring
matching — checked directly against the real files before writing
:func:`match_relevant_tissue_columns` (milestone4_plan.md §2.3). One tissue,
rheumatoid arthritis's ``"synovium"``, has **no** GTEx match at all — GTEx v10
simply does not profile synovial tissue. :func:`build_expression_features`
therefore logs an unmatched tissue and leaves
:data:`RELEVANT_TISSUE_TPM_COLUMN` null with :data:`MISSING_COLUMN` set,
rather than raising — a correction from an earlier version of this
docstring, which assumed (before checking) that an unmatched tissue name
would always be a data error rather than a genuine GTEx coverage gap.
"""

from __future__ import annotations

import re
from functools import cache

import polars as pl

from target_prioritization.data import gtex
from target_prioritization.utils.logging import get_logger, log_dropped

__all__ = [
    "DIMENSION_COLUMN",
    "MAX_TPM_COLUMN",
    "MEDIAN_TPM_COLUMN",
    "MISSING_COLUMN",
    "N_TISSUES_DETECTED_COLUMN",
    "RELEVANT_TISSUE_TPM_COLUMN",
    "TISSUE_SPECIFICITY_COLUMN",
    "TPM_DETECTION_THRESHOLD",
    "build_expression_features",
    "match_relevant_tissue_columns",
    "tissue_specificity",
]

log = get_logger(__name__)

MAX_TPM_COLUMN = "expr__max_tpm"
MEDIAN_TPM_COLUMN = "expr__median_tpm"
N_TISSUES_DETECTED_COLUMN = "expr__n_tissues_detected"
TISSUE_SPECIFICITY_COLUMN = "expr__tissue_specificity"
RELEVANT_TISSUE_TPM_COLUMN = "expr__relevant_tissue_tpm"
MISSING_COLUMN = "missing__expression"

# dim__expression (configs/model.yaml's baseline_weights
# "tissue_expression_score", Context.md §17.1) — a percentile rank of
# expr__relevant_tissue_tpm among the candidates this call was asked to
# score (one disease's candidate set), matching §17.1's naming (tissue
# expression, not overall expression) more closely than max_tpm would.
# Illustrative, like every baseline_weights term.
DIMENSION_COLUMN = "dim__expression"

# A gene counts as "detected" in a tissue above this TPM (Context.md §14.4's
# "number of tissues with detectable expression"). GTEx analyses commonly use
# 0.1-1 TPM as an expressed/not-expressed cutoff; 1.0 is the conservative end
# of that range, a documented choice rather than a tuned one.
TPM_DETECTION_THRESHOLD = 1.0


@cache
def _load_median_tpm() -> pl.DataFrame:
    """Cached GTEx median-TPM table.

    Per-gene, disease-agnostic (module docstring, milestone4_plan.md §4.2),
    but :func:`build_expression_features` is called once per disease by
    ``features.build_features.build_feature_table`` — this keeps a
    ten-disease run from re-parsing the gzipped GCT file ten times.
    """
    return gtex.load_median_tpm()


# "tissue" is a generic filler word a disease-config author might append
# (e.g. "adipose tissue") that carries no matching signal against GTEx's
# controlled vocabulary, which never uses it as a qualifier. Checked
# directly against the real files: dropping this one word from the QUERY
# side (never from GTEx's own names) is what's needed for every configured
# disease's relevant_tissues to resolve as expected — or to correctly fail
# to, for "synovium" (milestone4_plan.md §2.3).
_QUERY_STOPWORDS = frozenset({"tissue"})


def _tokenize(name: str, *, stopwords: frozenset[str] = frozenset()) -> set[str]:
    tokens = {token for token in re.split(r"[^a-z0-9]+", name.lower()) if token}
    return tokens - stopwords


def match_relevant_tissue_columns(
    relevant_tissues: list[str], candidate_columns: list[str]
) -> dict[str, list[str]]:
    """Match free-text disease tissue names to GTEx column names.

    Matching is by TOKEN-SET CONTAINMENT — every (non-stopword) word in the
    query must appear among the candidate's tokens, ignoring word order and
    splitting on any non-alphanumeric character — not substring containment.
    Substring matching fails two real cases: ``"sigmoid colon"`` doesn't
    substring-match ``Colon_Sigmoid`` (word order), and ``"adipose tissue"``
    matches neither adipose column (the word "tissue" appears in the query
    but never in a GTEx name). Token-set containment plus dropping "tissue"
    from the query resolves both. A query commonly matches more than one
    column (``"brain"`` matches all 13 GTEx brain sub-regions); callers
    aggregate across matches.

    Args:
        relevant_tissues: Free-text tissue names, e.g. from
            ``configs/diseases.yaml``.
        candidate_columns: GTEx tissue column names, e.g. from
            :func:`~target_prioritization.data.gtex.tissue_columns`.

    Returns:
        ``{relevant_tissue: [matching GTEx columns]}``, preserving input
        order. A tissue with no match maps to an empty list — logging that
        and deciding what to do about it is the caller's job (some callers
        may want to raise, others to record a documented null), not this
        function's.
    """
    candidate_tokens = {column: _tokenize(column) for column in candidate_columns}
    matches: dict[str, list[str]] = {}
    for tissue in relevant_tissues:
        query_tokens = _tokenize(tissue, stopwords=_QUERY_STOPWORDS)
        matches[tissue] = [
            column
            for column, tokens in candidate_tokens.items()
            if query_tokens and query_tokens <= tokens
        ]
    return matches


def tissue_specificity(tpm_by_tissue: pl.DataFrame) -> pl.DataFrame:
    """Compute a tissue-specificity index per gene.

    Uses the Tau index (Yanai et al. 2005): ``sum(1 - x_i / x_max) / (n - 1)``
    across ``n`` tissues, where ``x_max`` is the gene's own maximum TPM. Tau
    is 1 when expression is concentrated in a single tissue and 0 when
    uniform across all of them.

    Args:
        tpm_by_tissue: ``ensembl_gene_id`` plus one float column per tissue
            (the shape :func:`~target_prioritization.data.gtex.load_median_tpm`
            returns, minus ``gene_symbol``).

    Returns:
        ``ensembl_gene_id`` plus :data:`TISSUE_SPECIFICITY_COLUMN` in
        ``[0, 1]`` — null when the gene's max TPM across tissues is 0 (Tau is
        undefined for a gene with no detected expression anywhere), never a
        fabricated 0.
    """
    tissue_cols = [c for c in tpm_by_tissue.columns if c != "ensembl_gene_id"]
    n = len(tissue_cols)
    if n < 2:
        raise ValueError("tissue_specificity needs at least two tissue columns")

    max_expr = pl.max_horizontal(tissue_cols)
    tau_terms = [
        pl.when(max_expr > 0).then(1 - pl.col(c).fill_null(0.0) / max_expr).otherwise(None)
        for c in tissue_cols
    ]
    tau = pl.when(max_expr > 0).then(pl.sum_horizontal(tau_terms) / (n - 1)).otherwise(None)

    return tpm_by_tissue.select("ensembl_gene_id", tau.alias(TISSUE_SPECIFICITY_COLUMN))


def build_expression_features(
    gene_ids: list[str],
    relevant_tissues: list[str],
) -> pl.DataFrame:
    """Derive expression features for *gene_ids*.

    Args:
        gene_ids: Unversioned Ensembl gene IDs.
        relevant_tissues: GTEx tissue names for the disease. Matched via
            :func:`match_relevant_tissue_columns`; a tissue with zero matches
            (confirmed to happen — rheumatoid arthritis's ``"synovium"`` has
            no GTEx equivalent at all, module docstring) is logged and
            excluded, not an error.

    Returns:
        One row per gene: :data:`MAX_TPM_COLUMN`, :data:`MEDIAN_TPM_COLUMN`
        (across all GTEx tissues), :data:`N_TISSUES_DETECTED_COLUMN` (TPM
        above :data:`TPM_DETECTION_THRESHOLD`), :data:`TISSUE_SPECIFICITY_COLUMN`,
        :data:`RELEVANT_TISSUE_TPM_COLUMN` (mean TPM across every matched
        column), :data:`DIMENSION_COLUMN`, :data:`MISSING_COLUMN`. A gene
        absent from GTEx gets a null across every feature column, never a
        zero (Context.md §32.3).
    """
    result_schema = {
        "target_id": pl.String,
        MAX_TPM_COLUMN: pl.Float64,
        MEDIAN_TPM_COLUMN: pl.Float64,
        N_TISSUES_DETECTED_COLUMN: pl.UInt32,
        TISSUE_SPECIFICITY_COLUMN: pl.Float64,
        RELEVANT_TISSUE_TPM_COLUMN: pl.Float64,
        DIMENSION_COLUMN: pl.Float64,
        MISSING_COLUMN: pl.Int8,
    }
    if not gene_ids:
        return pl.DataFrame(schema=result_schema)

    tpm = _load_median_tpm()
    tissue_cols = gtex.tissue_columns(tpm)

    matches = match_relevant_tissue_columns(relevant_tissues, tissue_cols)
    matched_columns = sorted({column for columns in matches.values() for column in columns})
    unmatched = [tissue for tissue, columns in matches.items() if not columns]
    log_dropped(
        log,
        stage="relevant_tissue_matching",
        reason="disease tissue name has no matching GTEx column",
        count=len(unmatched),
        total=len(relevant_tissues),
        examples=unmatched,
    )

    # dim__expression ranks expr__relevant_tissue_tpm against the FULL GTEx
    # population (~59k genes), not this call's candidate set. Ranking
    # against the per-call candidate set instead would make an otherwise
    # disease-invariant-per-tissue-set gene property depend on population
    # size, and shift systematically between a leave-one-disease-out fold's
    # train and test populations (same reasoning as network.py's
    # dim__network — see its docstring).
    if matched_columns:
        relevant_population = tpm.select(
            "ensembl_gene_id", pl.mean_horizontal(matched_columns).alias(RELEVANT_TISSUE_TPM_COLUMN)
        )
        n_ranked = relevant_population.get_column(RELEVANT_TISSUE_TPM_COLUMN).is_not_null().sum()
        relevant_population = relevant_population.with_columns(
            (pl.col(RELEVANT_TISSUE_TPM_COLUMN).rank(method="average") / n_ranked).alias(DIMENSION_COLUMN)
            if n_ranked
            else pl.lit(None, dtype=pl.Float64).alias(DIMENSION_COLUMN)
        )
    else:
        relevant_population = tpm.select("ensembl_gene_id").with_columns(
            pl.lit(None, dtype=pl.Float64).alias(RELEVANT_TISSUE_TPM_COLUMN),
            pl.lit(None, dtype=pl.Float64).alias(DIMENSION_COLUMN),
        )

    base = tpm.filter(pl.col("ensembl_gene_id").is_in(gene_ids)).select("ensembl_gene_id", *tissue_cols)

    per_gene = (
        base.select(
            "ensembl_gene_id",
            pl.max_horizontal(tissue_cols).alias(MAX_TPM_COLUMN),
            pl.concat_list(tissue_cols).list.median().alias(MEDIAN_TPM_COLUMN),
            pl.sum_horizontal(
                [(pl.col(c) > TPM_DETECTION_THRESHOLD).cast(pl.UInt32) for c in tissue_cols]
            ).alias(N_TISSUES_DETECTED_COLUMN),
        )
        .join(tissue_specificity(base), on="ensembl_gene_id", how="left")
        .join(
            relevant_population.select("ensembl_gene_id", RELEVANT_TISSUE_TPM_COLUMN, DIMENSION_COLUMN),
            on="ensembl_gene_id",
            how="left",
        )
    )

    per_gene = per_gene.rename({"ensembl_gene_id": "target_id"})

    result = pl.DataFrame({"target_id": gene_ids}, schema={"target_id": pl.String}).join(
        per_gene, on="target_id", how="left"
    )

    log_dropped(
        log,
        stage="expression_coverage",
        reason="gene absent from the GTEx median-TPM table",
        count=result.filter(pl.col(MAX_TPM_COLUMN).is_null()).height,
        total=len(gene_ids),
    )

    return result.with_columns(pl.col(MAX_TPM_COLUMN).is_null().cast(pl.Int8).alias(MISSING_COLUMN))
