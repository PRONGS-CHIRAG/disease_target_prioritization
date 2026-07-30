"""Tests for the multi-disease feature-table assembly (Context.md §37).

``build_feature_table`` itself needs the downloaded release (it calls
``build_disease_features`` once per disease), so — consistent with how the
rest of this suite tests real-data-dependent pipelines — it is exercised via
``scripts/build_dataset.py`` rather than pytest. What's unit-testable here is
the composition logic around that loop: deterministic column ordering after
a diagonal concat, and detecting per-disease all-null columns.
"""

from __future__ import annotations

import polars as pl

from target_prioritization.features.build_features import (
    _ID_COLUMN_ORDER,
    _sparse_columns_by_disease,
)


class TestSparseColumnsByDisease:
    def test_detects_a_column_all_null_within_one_disease(self):
        combined = pl.DataFrame(
            {
                "disease_id": ["D1", "D1", "D2", "D2"],
                "target_id": ["T1", "T2", "T3", "T4"],
                "assoc_ds__crispr_screen_score": [0.5, 0.7, None, None],
                "assoc_ds__gwas_credible_sets_score": [0.1, None, 0.9, 0.2],
            }
        )
        sparse = _sparse_columns_by_disease(
            combined, ["assoc_ds__crispr_screen_score", "assoc_ds__gwas_credible_sets_score"]
        )
        assert sparse == {"D2": ["assoc_ds__crispr_screen_score"]}

    def test_a_column_null_for_only_some_rows_is_not_reported(self):
        """Partial nulls are normal missing evidence, not disease-wide sparsity."""
        combined = pl.DataFrame(
            {
                "disease_id": ["D1", "D1"],
                "target_id": ["T1", "T2"],
                "assoc_ds__eva_score": [0.5, None],
            }
        )
        assert _sparse_columns_by_disease(combined, ["assoc_ds__eva_score"]) == {}

    def test_no_sparse_columns_returns_empty_dict(self):
        combined = pl.DataFrame(
            {
                "disease_id": ["D1", "D2"],
                "target_id": ["T1", "T2"],
                "dim__genetics": [0.5, 0.6],
            }
        )
        assert _sparse_columns_by_disease(combined, ["dim__genetics"]) == {}

    def test_multiple_diseases_and_columns_reported_independently(self):
        combined = pl.DataFrame(
            {
                "disease_id": ["D1", "D1", "D2", "D2", "D3", "D3"],
                "target_id": ["T1", "T2", "T3", "T4", "T5", "T6"],
                "assoc_ds__intogen_score": [None, None, 0.4, 0.6, None, None],
                "assoc_ds__impc_score": [0.3, 0.5, None, None, None, None],
            }
        )
        sparse = _sparse_columns_by_disease(
            combined, ["assoc_ds__intogen_score", "assoc_ds__impc_score"]
        )
        assert sparse == {
            "D1": ["assoc_ds__intogen_score"],
            "D2": ["assoc_ds__impc_score"],
            "D3": ["assoc_ds__impc_score", "assoc_ds__intogen_score"],
        }


class TestDeterministicColumnOrder:
    """Diagonal concat orders columns by frame arrival order, which depends
    on which disease happened to be built first — not reproducible across
    runs on its own (Context.md §33). build_feature_table re-sorts after
    concatenating; this checks the ordering rule it applies."""

    def test_id_columns_precede_feature_columns_in_the_declared_order(self):
        combined = pl.DataFrame(
            {
                "biotype": ["protein_coding"],
                "dim__genetics": [0.5],
                "target_id": ["T1"],
                "disease_id": ["D1"],
                "assoc_ds__eva_score": [0.2],
            }
        )
        id_columns = [c for c in _ID_COLUMN_ORDER if c in combined.columns]
        feature_columns = sorted(c for c in combined.columns if c not in id_columns)
        ordered = combined.select([*id_columns, *feature_columns])

        assert ordered.columns == [
            "disease_id",
            "target_id",
            "biotype",
            "assoc_ds__eva_score",
            "dim__genetics",
        ]

    def test_feature_column_order_is_independent_of_input_order(self):
        """The same columns in a different starting order must sort identically —
        this is what makes a diagonal concat's output reproducible."""
        a = pl.DataFrame({"target_id": ["T1"], "dim__genetics": [0.1], "dim__functional": [0.2]})
        b = pl.DataFrame({"dim__functional": [0.3], "target_id": ["T2"], "dim__genetics": [0.4]})

        def reorder(frame: pl.DataFrame) -> pl.DataFrame:
            id_columns = [c for c in _ID_COLUMN_ORDER if c in frame.columns]
            feature_columns = sorted(c for c in frame.columns if c not in id_columns)
            return frame.select([*id_columns, *feature_columns])

        assert reorder(a).columns == reorder(b).columns
