"""Tests for pathway features (Context.md §14.3, Milestone 4).

Synthetic Reactome fixtures, in the style of tests/test_dimensions.py — never
the real ~178k-row human mapping file. ``pathways._load_human_pathway_data``
is monkeypatched directly (it's ``lru_cache``-wrapped, so patching the
underlying loaders it calls wouldn't reliably take effect once the cache is
warm); this replaces the whole cached function for the duration of a test.

Fixture hierarchy — two trees:

    R-HSA-1 (root)          R-HSA-4 (root)
      |__ R-HSA-2             |__ R-HSA-5
            |__ R-HSA-3

GENE_A: R-HSA-1, R-HSA-2, R-HSA-3   -> all one root (R-HSA-1)
GENE_B: R-HSA-4                     -> root R-HSA-4
GENE_C: R-HSA-2, R-HSA-5            -> two roots (R-HSA-1, R-HSA-4)
GENE_D: (no rows at all)            -> no pathway annotation
"""

from __future__ import annotations

import polars as pl

from target_prioritization.features import pathways

MAPPING = pl.DataFrame(
    {
        "ensembl_gene_id": [
            "GENE_A", "GENE_A", "GENE_A",
            "GENE_B",
            "GENE_C", "GENE_C",
        ],
        "pathway_id": [
            "R-HSA-1", "R-HSA-2", "R-HSA-3",
            "R-HSA-4",
            "R-HSA-2", "R-HSA-5",
        ],
    }
)

RELATIONS = pl.DataFrame(
    {
        "parent_pathway_id": ["R-HSA-1", "R-HSA-2", "R-HSA-4"],
        "child_pathway_id": ["R-HSA-2", "R-HSA-3", "R-HSA-5"],
    }
)


def _patch_loader(monkeypatch) -> None:
    monkeypatch.setattr(pathways, "_load_human_pathway_data", lambda: (MAPPING, RELATIONS))


class TestRootFinder:
    def test_root_of_a_root_is_itself(self):
        root_of = pathways._build_root_finder(RELATIONS)
        assert root_of("R-HSA-1") == "R-HSA-1"
        assert root_of("R-HSA-4") == "R-HSA-4"

    def test_root_of_a_leaf_walks_to_the_top(self):
        root_of = pathways._build_root_finder(RELATIONS)
        assert root_of("R-HSA-3") == "R-HSA-1"
        assert root_of("R-HSA-5") == "R-HSA-4"

    def test_unrelated_pathway_id_is_its_own_root(self):
        """A pathway absent from the relations table entirely (no parent,
        no child edge) is trivially its own root."""
        root_of = pathways._build_root_finder(RELATIONS)
        assert root_of("R-HSA-999") == "R-HSA-999"

    def test_a_cycle_does_not_infinite_loop(self):
        """Reactome's hierarchy shouldn't contain cycles, but the walk must
        terminate defensively rather than hang if one existed."""
        cyclic = pl.DataFrame(
            {"parent_pathway_id": ["A", "B"], "child_pathway_id": ["B", "A"]}
        )
        root_of = pathways._build_root_finder(cyclic)
        assert root_of("A") in {"A", "B"}


class TestBuildPathwayFeatures:
    def test_counts_distinct_root_categories_not_raw_rows(self, monkeypatch):
        """GENE_A has 3 raw pathway rows but they all collapse to ONE root —
        the whole point of counting roots instead of leaves (module
        docstring)."""
        _patch_loader(monkeypatch)
        result = pathways.build_pathway_features(["GENE_A"])
        row = result.row(0, named=True)
        assert row[pathways.N_PATHWAYS_COLUMN] == 1
        assert row[pathways.MISSING_COLUMN] == 0

    def test_gene_spanning_two_roots_counts_two(self, monkeypatch):
        _patch_loader(monkeypatch)
        result = pathways.build_pathway_features(["GENE_C"])
        row = result.row(0, named=True)
        assert row[pathways.N_PATHWAYS_COLUMN] == 2

    def test_gene_with_no_annotation_is_null_not_zero(self, monkeypatch):
        _patch_loader(monkeypatch)
        result = pathways.build_pathway_features(["GENE_D"])
        row = result.row(0, named=True)
        assert row[pathways.N_PATHWAYS_COLUMN] is None
        assert row[pathways.MISSING_COLUMN] == 1

    def test_every_requested_gene_gets_exactly_one_row(self, monkeypatch):
        _patch_loader(monkeypatch)
        result = pathways.build_pathway_features(["GENE_A", "GENE_B", "GENE_C", "GENE_D"])
        assert sorted(result.get_column("target_id").to_list()) == [
            "GENE_A", "GENE_B", "GENE_C", "GENE_D",
        ]
        assert result.height == 4

    def test_empty_input_returns_correctly_typed_empty_frame(self, monkeypatch):
        _patch_loader(monkeypatch)
        result = pathways.build_pathway_features([])
        assert result.height == 0
        assert result.schema["target_id"] == pl.String
        assert result.schema[pathways.N_PATHWAYS_COLUMN] == pl.UInt32


class TestPathwayOverlapWithKnownGenes:
    def test_full_overlap_when_all_roots_are_seeds(self, monkeypatch):
        """GENE_B's only root (R-HSA-4) is also GENE_C's second root, but
        seeding with GENE_A (root R-HSA-1 only) gives GENE_B zero overlap."""
        _patch_loader(monkeypatch)
        result = pathways.pathway_overlap_with_known_genes(["GENE_B"], known_disease_genes=["GENE_A"])
        assert result.row(0, named=True)[pathways.OVERLAP_COLUMN] == 0.0

    def test_partial_overlap(self, monkeypatch):
        """GENE_C spans both roots; only one of its two roots (R-HSA-1)
        matches the GENE_A seed, so overlap is 1/2."""
        _patch_loader(monkeypatch)
        result = pathways.pathway_overlap_with_known_genes(["GENE_C"], known_disease_genes=["GENE_A"])
        assert result.row(0, named=True)[pathways.OVERLAP_COLUMN] == 0.5

    def test_gene_with_no_pathway_annotation_is_null(self, monkeypatch):
        _patch_loader(monkeypatch)
        result = pathways.pathway_overlap_with_known_genes(["GENE_D"], known_disease_genes=["GENE_A"])
        assert result.row(0, named=True)[pathways.OVERLAP_COLUMN] is None

    def test_a_seed_gene_scored_against_itself_is_full_overlap(self, monkeypatch):
        """Documents the leave-one-out caveat: this function does not
        exclude a candidate from its own seed set, so a candidate that IS a
        seed gene trivially scores 1.0. Callers doing guilt-by-association
        must exclude the candidate from known_disease_genes themselves."""
        _patch_loader(monkeypatch)
        result = pathways.pathway_overlap_with_known_genes(["GENE_A"], known_disease_genes=["GENE_A"])
        assert result.row(0, named=True)[pathways.OVERLAP_COLUMN] == 1.0

    def test_empty_known_genes_gives_null_not_zero(self, monkeypatch):
        _patch_loader(monkeypatch)
        result = pathways.pathway_overlap_with_known_genes(["GENE_A"], known_disease_genes=[])
        assert result.row(0, named=True)[pathways.OVERLAP_COLUMN] is None

    def test_empty_gene_ids_returns_correctly_typed_empty_frame(self, monkeypatch):
        _patch_loader(monkeypatch)
        result = pathways.pathway_overlap_with_known_genes([], known_disease_genes=["GENE_A"])
        assert result.height == 0
        assert result.schema["target_id"] == pl.String
        assert result.schema[pathways.OVERLAP_COLUMN] == pl.Float64
