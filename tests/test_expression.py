"""Tests for GTEx expression features (Context.md §14.4, Milestone 4).

Synthetic TPM fixtures, never the real 68-tissue GTEx file.
``expression._load_median_tpm`` is monkeypatched directly (it's
``cache``-wrapped, so patching the underlying loader wouldn't reliably take
effect once the cache is warm).

Fixture tissues: ``Colon_Sigmoid``, ``Adipose_Subcutaneous``,
``Adipose_Visceral_Omentum``, ``Brain_Cortex``, ``Brain_Substantia_nigra`` —
chosen specifically because they're the ones milestone4_plan.md §2.3
identified as tricky to match (word order, a filler word, multiple matches).

    GENE_A: [0.1, 0.1, 0.1, 0.1, 100.0]   -> concentrated in substantia nigra
    GENE_B: [10.0, 10.0, 10.0, 10.0, 10.0] -> uniform across all 5
    GENE_C: [0.0, 0.0, 0.0, 0.0, 0.0]       -> no detected expression anywhere
    GENE_D: absent from the table entirely
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.features import expression

TISSUE_COLUMNS = [
    "Colon_Sigmoid",
    "Adipose_Subcutaneous",
    "Adipose_Visceral_Omentum",
    "Brain_Cortex",
    "Brain_Substantia_nigra",
]

TPM = pl.DataFrame(
    {
        "ensembl_gene_id": ["GENE_A", "GENE_B", "GENE_C"],
        "gene_symbol": ["A", "B", "C"],
        "Colon_Sigmoid": [0.1, 10.0, 0.0],
        "Adipose_Subcutaneous": [0.1, 10.0, 0.0],
        "Adipose_Visceral_Omentum": [0.1, 10.0, 0.0],
        "Brain_Cortex": [0.1, 10.0, 0.0],
        "Brain_Substantia_nigra": [100.0, 10.0, 0.0],
    }
)


def _patch(monkeypatch) -> None:
    monkeypatch.setattr(expression, "_load_median_tpm", lambda: TPM)


class TestMatchRelevantTissueColumns:
    def test_word_order_does_not_matter(self):
        """'sigmoid colon' vs GTEx's 'Colon_Sigmoid' — reversed order."""
        matches = expression.match_relevant_tissue_columns(["sigmoid colon"], TISSUE_COLUMNS)
        assert matches["sigmoid colon"] == ["Colon_Sigmoid"]

    def test_filler_word_tissue_is_dropped_from_the_query(self):
        """'adipose tissue' matches both adipose columns once 'tissue' (absent
        from every GTEx name) is dropped from the query side."""
        matches = expression.match_relevant_tissue_columns(["adipose tissue"], TISSUE_COLUMNS)
        assert sorted(matches["adipose tissue"]) == ["Adipose_Subcutaneous", "Adipose_Visceral_Omentum"]

    def test_single_token_query_matches_every_sub_region(self):
        matches = expression.match_relevant_tissue_columns(["brain"], TISSUE_COLUMNS)
        assert sorted(matches["brain"]) == ["Brain_Cortex", "Brain_Substantia_nigra"]

    def test_genuinely_unmatched_tissue_returns_empty_not_a_guess(self):
        """GTEx v10 has no synovial tissue at all — the real gap this
        project discovered, not a matching-algorithm shortcoming."""
        matches = expression.match_relevant_tissue_columns(["synovium"], TISSUE_COLUMNS)
        assert matches["synovium"] == []

    def test_exact_single_column_match(self):
        matches = expression.match_relevant_tissue_columns(["brain cortex"], TISSUE_COLUMNS)
        assert matches["brain cortex"] == ["Brain_Cortex"]


class TestTissueSpecificity:
    def test_concentrated_expression_is_near_one(self):
        result = expression.tissue_specificity(TPM.drop("gene_symbol"))
        row = result.filter(pl.col("ensembl_gene_id") == "GENE_A").row(0, named=True)
        assert row[expression.TISSUE_SPECIFICITY_COLUMN] == pytest.approx(0.999, abs=1e-3)

    def test_uniform_expression_is_zero(self):
        result = expression.tissue_specificity(TPM.drop("gene_symbol"))
        row = result.filter(pl.col("ensembl_gene_id") == "GENE_B").row(0, named=True)
        assert row[expression.TISSUE_SPECIFICITY_COLUMN] == pytest.approx(0.0, abs=1e-9)

    def test_no_expression_anywhere_is_null_not_zero(self):
        """Tau is undefined, not zero, when max TPM is 0 — a flat zero would
        be indistinguishable from perfectly uniform expression."""
        result = expression.tissue_specificity(TPM.drop("gene_symbol"))
        row = result.filter(pl.col("ensembl_gene_id") == "GENE_C").row(0, named=True)
        assert row[expression.TISSUE_SPECIFICITY_COLUMN] is None


class TestBuildExpressionFeatures:
    def test_max_median_and_detected_counts(self, monkeypatch):
        _patch(monkeypatch)
        result = expression.build_expression_features(["GENE_A"], relevant_tissues=["brain"])
        row = result.row(0, named=True)
        assert row[expression.MAX_TPM_COLUMN] == 100.0
        assert row[expression.MEDIAN_TPM_COLUMN] == 0.1
        assert row[expression.N_TISSUES_DETECTED_COLUMN] == 1  # only substantia nigra > 1.0 TPM

    def test_relevant_tissue_tpm_averages_multiple_matches(self, monkeypatch):
        """'brain' matches both Brain_Cortex (0.1) and Brain_Substantia_nigra
        (100.0) for GENE_A — averaged, not just one of them picked."""
        _patch(monkeypatch)
        result = expression.build_expression_features(["GENE_A"], relevant_tissues=["brain"])
        row = result.row(0, named=True)
        assert row[expression.RELEVANT_TISSUE_TPM_COLUMN] == pytest.approx((0.1 + 100.0) / 2)

    def test_unmatched_tissue_is_a_documented_null_not_an_error(self, monkeypatch):
        """The corrected contract (module docstring): a disease tissue with
        no GTEx match logs and nulls the relevant-tissue column, it does not
        raise and does not block the rest of the gene's features."""
        _patch(monkeypatch)
        result = expression.build_expression_features(["GENE_A"], relevant_tissues=["synovium"])
        row = result.row(0, named=True)
        assert row[expression.RELEVANT_TISSUE_TPM_COLUMN] is None
        # The rest of the gene's features are still populated.
        assert row[expression.MAX_TPM_COLUMN] == 100.0
        assert row[expression.MISSING_COLUMN] == 0

    def test_gene_absent_from_gtex_is_null_across_every_column(self, monkeypatch):
        _patch(monkeypatch)
        result = expression.build_expression_features(["GENE_D"], relevant_tissues=["brain"])
        row = result.row(0, named=True)
        assert row[expression.MAX_TPM_COLUMN] is None
        assert row[expression.MEDIAN_TPM_COLUMN] is None
        assert row[expression.RELEVANT_TISSUE_TPM_COLUMN] is None
        assert row[expression.MISSING_COLUMN] == 1

    def test_every_requested_gene_gets_exactly_one_row(self, monkeypatch):
        _patch(monkeypatch)
        result = expression.build_expression_features(
            ["GENE_A", "GENE_B", "GENE_C", "GENE_D"], relevant_tissues=["brain"]
        )
        assert result.height == 4

    def test_empty_gene_ids_returns_correctly_typed_empty_frame(self, monkeypatch):
        _patch(monkeypatch)
        result = expression.build_expression_features([], relevant_tissues=["brain"])
        assert result.height == 0
        assert result.schema["target_id"] == pl.String
        assert result.schema[expression.MAX_TPM_COLUMN] == pl.Float64

    def test_dim_expression_does_not_depend_on_the_calling_candidate_set(self, monkeypatch):
        """dim__expression must rank against the FULL GTEx population, not
        whichever subset of genes this particular call happens to request —
        same reasoning as network.py's equivalent test: an otherwise
        disease-invariant-per-tissue-set gene property must not shift with
        population size (leave-one-disease-out train/test mismatch)."""
        _patch(monkeypatch)
        alone = expression.build_expression_features(["GENE_A"], relevant_tissues=["brain"])
        with_everyone = expression.build_expression_features(
            ["GENE_A", "GENE_B", "GENE_C"], relevant_tissues=["brain"]
        )
        a_alone = alone.row(0, named=True)[expression.DIMENSION_COLUMN]
        a_with_everyone = with_everyone.filter(pl.col("target_id") == "GENE_A").row(0, named=True)[
            expression.DIMENSION_COLUMN
        ]
        assert a_alone == a_with_everyone
