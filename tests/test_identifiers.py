"""Tests for identifier normalization.

Context.md §34 requires unit tests for identifier mapping specifically. Each
test below encodes one real trap from a real source file — the cases that
produce silently wrong joins rather than loud errors.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.data.identifiers import (
    MappingReport,
    build_symbol_lookup,
    ensp_to_ensg_from_string_aliases,
    filter_reactome_to_human,
    is_ensembl_gene_id,
    normalize_ensembl_id,
    strip_ensembl_version,
)


class TestStripEnsemblVersion:
    """GTEx ships versioned IDs; Open Targets and Reactome do not."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ENSG00000186092.7", "ENSG00000186092"),
            ("ENSG00000186092.17", "ENSG00000186092"),
            ("ENSG00000186092", "ENSG00000186092"),
            # PAR_Y genes on the pseudoautosomal region carry a non-numeric
            # suffix. Only a numeric version is a version.
            ("ENSG00000182378.14_PAR_Y", "ENSG00000182378.14_PAR_Y"),
            ("", None),
            ("   ", None),
            (None, None),
        ],
    )
    def test_strips_only_numeric_version_suffix(self, raw, expected):
        assert strip_ensembl_version(raw) == expected

    def test_gtex_and_open_targets_ids_join_after_stripping(self):
        """The actual failure this function exists to prevent."""
        gtex_id = "ENSG00000186092.7"
        open_targets_id = "ENSG00000186092"

        assert gtex_id != open_targets_id  # the silent-zero-rows bug
        assert strip_ensembl_version(gtex_id) == open_targets_id


class TestNormalizeEnsemblId:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  ensg00000186092.7  ", "ENSG00000186092"),
            ("ENSG00000186092", "ENSG00000186092"),
            ("", None),
            (None, None),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert normalize_ensembl_id(raw) == expected


class TestIsEnsemblGeneId:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("ENSG00000186092", True),
            ("ENSG00000186092.7", True),
            ("ensg00000186092", True),
            # A protein ID must not pass as a gene ID — that is the STRING trap.
            ("ENSP00000493376", False),
            ("9606.ENSP00000493376", False),
            ("ENSG123", False),
            ("BRCA1", False),
            ("", False),
            (None, False),
        ],
    )
    def test_recognises_gene_ids_only(self, value, expected):
        assert is_ensembl_gene_id(value) is expected


class TestStringAliases:
    """STRING keys on ENSP; the network is unjoinable without this bridge."""

    @pytest.fixture
    def aliases(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "string_protein_id": [
                    "9606.ENSP00000493376",
                    "9606.ENSP00000493376",
                    "9606.ENSP00000356737",
                    "9606.ENSP00000999999",  # only non-Ensembl aliases
                ],
                "alias": [
                    "ENSG00000186092",
                    "OR4F5",
                    "ENSG00000186092",  # second isoform of the same gene
                    "SOMEALIAS",
                ],
                "source": [
                    "Ensembl_gene",
                    "Ensembl_HGNC",
                    "Ensembl_gene",
                    "BLAST_UniProt_DR_GeneID",
                ],
            }
        )

    def test_extracts_gene_ids(self, aliases):
        lookup, _ = ensp_to_ensg_from_string_aliases(aliases)
        mapping = dict(
            zip(
                lookup.get_column("string_protein_id"),
                lookup.get_column("ensembl_gene_id"),
                strict=True,
            )
        )
        assert mapping["9606.ENSP00000493376"] == "ENSG00000186092"
        assert mapping["9606.ENSP00000356737"] == "ENSG00000186092"

    def test_many_isoforms_map_to_one_gene(self, aliases):
        """Expected, not a bug: network features aggregate per gene afterwards."""
        lookup, _ = ensp_to_ensg_from_string_aliases(aliases)
        genes = lookup.filter(pl.col("ensembl_gene_id") == "ENSG00000186092")
        assert genes.height == 2

    def test_reports_unmapped_proteins(self, aliases):
        """Context.md §34: never silently discard a failed mapping.

        The denominator is *distinct proteins* (3), not alias rows (4) —
        ENSP00000493376 appears twice in the fixture. Proteins are the unit
        being mapped, so a per-row rate would understate coverage.
        """
        _, report = ensp_to_ensg_from_string_aliases(aliases)
        assert report.total == 3
        assert report.mapped == 2
        assert report.unmapped == 1
        assert "9606.ENSP00000999999" in report.unmapped_examples

    def test_ignores_non_gene_aliases(self, aliases):
        lookup, _ = ensp_to_ensg_from_string_aliases(aliases)
        assert not lookup.filter(pl.col("ensembl_gene_id") == "OR4F5").height


class TestReactomeHumanFilter:
    """Ensembl2Reactome_All_Levels.txt is multi-species."""

    @pytest.fixture
    def mapping(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "ensembl_gene_id": [
                    "ENSG00000186092",
                    "ENSMUSG00000064341",
                    "ENSG00000141510.16",
                    "ENSDARG00000019949",
                ],
                "pathway_id": [
                    "R-HSA-373076",
                    "R-MMU-373076",
                    "R-HSA-5633007",
                    "R-DRE-373076",
                ],
                "species": [
                    "Homo sapiens",
                    "Mus musculus",
                    "Homo sapiens",
                    "Danio rerio",
                ],
            }
        )

    def test_keeps_only_human(self, mapping):
        human, _ = filter_reactome_to_human(mapping)
        assert human.height == 2
        assert set(human.get_column("species").unique()) == {"Homo sapiens"}

    def test_strips_version_suffix(self, mapping):
        human, _ = filter_reactome_to_human(mapping)
        assert "ENSG00000141510" in human.get_column("ensembl_gene_id").to_list()

    def test_mouse_pathways_do_not_inflate_human_counts(self, mapping):
        """The bug this filter prevents: a mouse gene adding to a human target."""
        human, _ = filter_reactome_to_human(mapping)
        ids = human.get_column("ensembl_gene_id").to_list()
        assert not any(i.startswith(("ENSMUSG", "ENSDARG")) for i in ids)

    def test_reports_what_was_dropped(self, mapping):
        _, report = filter_reactome_to_human(mapping)
        assert report.total == 4
        assert report.mapped == 2
        assert "Mus musculus" in report.unmapped_examples


class TestSymbolLookup:
    """Symbols are display labels, not stable keys."""

    @pytest.fixture
    def hgnc(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "symbol": ["PRKN", "PARK7", "SNCA", "NOENSEMBL"],
                "ensembl_gene_id": [
                    "ENSG00000185345",
                    "ENSG00000116288",
                    "ENSG00000145335",
                    "",
                ],
                # HGNC packs multiple values into one pipe-delimited field.
                "prev_symbol": ["PARK2", "", "PARK1|PARK4", ""],
                "alias_symbol": ["AR-JP|PDJ", "DJ1|DJ-1", "NACP", ""],
            }
        )

    def test_current_symbol_resolves(self, hgnc):
        lookup, _ = build_symbol_lookup(hgnc)
        row = lookup.filter(pl.col("symbol") == "PRKN")
        assert row.get_column("ensembl_gene_id").to_list() == ["ENSG00000185345"]

    def test_retired_symbol_still_resolves(self, hgnc):
        """PARK2 was renamed to PRKN, but the Parkinson's literature is full of it."""
        lookup, _ = build_symbol_lookup(hgnc)
        row = lookup.filter(pl.col("symbol") == "PARK2")
        assert row.get_column("ensembl_gene_id").to_list() == ["ENSG00000185345"]
        assert row.get_column("symbol_kind").to_list() == ["previous"]

    def test_pipe_delimited_fields_are_split(self, hgnc):
        lookup, _ = build_symbol_lookup(hgnc)
        symbols = set(lookup.get_column("symbol"))
        assert {"PARK1", "PARK4"} <= symbols  # both halves of "PARK1|PARK4"
        assert "PARK1|PARK4" not in symbols

    def test_aliases_resolve(self, hgnc):
        lookup, _ = build_symbol_lookup(hgnc)
        row = lookup.filter(pl.col("symbol") == "DJ-1")
        assert row.get_column("ensembl_gene_id").to_list() == ["ENSG00000116288"]

    def test_priority_ranks_approved_above_previous_above_alias(self, hgnc):
        lookup, _ = build_symbol_lookup(hgnc)
        priority = dict(
            zip(lookup.get_column("symbol_kind"), lookup.get_column("priority"), strict=True)
        )
        assert priority["approved"] < priority["previous"] < priority["alias"]

    def test_genes_without_an_ensembl_id_are_excluded(self, hgnc):
        lookup, _ = build_symbol_lookup(hgnc)
        assert not lookup.filter(pl.col("symbol") == "NOENSEMBL").height

    def test_lookup_is_uppercased(self, hgnc):
        lookup, _ = build_symbol_lookup(hgnc)
        symbols = lookup.get_column("symbol").to_list()
        assert all(s == s.upper() for s in symbols)


class TestMappingReport:
    def test_computes_unmapped_and_fraction(self):
        report = MappingReport(stage="x", total=10, mapped=8)
        assert report.unmapped == 2
        assert report.mapped_fraction == 0.8

    def test_handles_empty_input_without_dividing_by_zero(self):
        report = MappingReport(stage="x", total=0, mapped=0)
        assert report.mapped_fraction == 0.0

    def test_str_is_readable(self):
        assert "8/10 mapped" in str(MappingReport(stage="x", total=10, mapped=8))
