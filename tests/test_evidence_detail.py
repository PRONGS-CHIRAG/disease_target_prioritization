"""Tests for the browsable evidence detail (Context.md §21).

Hermetic throughout: the three detail artifacts are written as tiny parquets
into ``tmp_path`` and the module-level paths are monkeypatched, so nothing
here touches the ~3 GB raw pull or the committed 7 MB artifacts. The builders
in ``detail_data`` are tested against patched loaders for the same reason —
what needs testing is the reshaping logic (both-direction expansion, root-name
join, universe filtering), not Reactome's file format, which
``tests/test_pathways.py`` already covers.
"""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest
from fastapi.testclient import TestClient

from target_prioritization import detail_data
from target_prioritization.api import main
from target_prioritization.config import DiseaseSpec
from target_prioritization.services import evidence_detail

DISEASE = "MONDO_TEST"
OTHER_DISEASE = "MONDO_OTHER"
TARGET = "ENSG_A"


# ---------------------------------------------------------------------------
# detail_data builders
# ---------------------------------------------------------------------------


def test_build_target_pathways_groups_by_root_and_names_it(monkeypatch):
    """Root NAMES come from the pathway dictionary, not the membership rows.

    A gene is not annotated to its own root category, so the root name is
    unavailable from the membership frame alone.
    """
    monkeypatch.setattr(
        detail_data,
        "pathway_memberships",
        lambda ids: pl.DataFrame(
            {
                "ensembl_gene_id": [TARGET, TARGET],
                "pathway_id": ["R-HSA-2", "R-HSA-3"],
                "pathway_url": ["u2", "u3"],
                "pathway_name": ["Child two", "Child three"],
                "root_pathway_id": ["R-HSA-1", "R-HSA-1"],
            }
        ),
    )
    monkeypatch.setattr(
        detail_data,
        "load_pathway_names",
        lambda: pl.DataFrame(
            {"pathway_id": ["R-HSA-1"], "pathway_name": ["Immune System"], "species": ["Homo sapiens"]}
        ),
    )

    result = detail_data.build_target_pathways([TARGET])

    assert result.height == 2
    assert result.get_column("root_pathway_name").unique().to_list() == ["Immune System"]
    assert result.get_column("root_pathway_id").n_unique() == 1


def test_build_target_pathways_deduplicates_evidence_codes(monkeypatch):
    """Reactome lists a (gene, pathway) pair once per evidence code.

    Without deduplication the same pathway would appear twice in the panel.
    """
    monkeypatch.setattr(
        detail_data,
        "pathway_memberships",
        lambda ids: pl.DataFrame(
            {
                "ensembl_gene_id": [TARGET, TARGET],
                "pathway_id": ["R-HSA-2", "R-HSA-2"],
                "pathway_url": ["u2", "u2"],
                "pathway_name": ["Child two", "Child two"],
                "root_pathway_id": ["R-HSA-1", "R-HSA-1"],
            }
        ),
    )
    monkeypatch.setattr(
        detail_data,
        "load_pathway_names",
        lambda: pl.DataFrame({"pathway_id": ["R-HSA-1"], "pathway_name": ["Root"], "species": ["Homo sapiens"]}),
    )

    assert detail_data.build_target_pathways([TARGET]).height == 1


def test_build_target_pathways_empty_input_keeps_schema():
    result = detail_data.build_target_pathways([])
    assert result.is_empty()
    assert "root_pathway_name" in result.columns


def test_build_target_interactions_expands_both_directions(monkeypatch):
    """STRING edges are stored undirected; a lookup keyed on one endpoint
    would otherwise miss half of every gene's partners."""
    monkeypatch.setattr(
        detail_data.string_db,
        "load_gene_level_edges",
        lambda **kwargs: (
            pl.DataFrame({"gene1": ["A"], "gene2": ["B"], "score": [900]}),
            SimpleNamespace(log=lambda: None),
        ),
    )

    result = detail_data.build_target_interactions(["A", "B"])

    pairs = set(zip(result.get_column("target_id"), result.get_column("partner_target_id"), strict=True))
    assert pairs == {("A", "B"), ("B", "A")}


def test_build_target_interactions_drops_partners_outside_the_universe(monkeypatch):
    """A partner with no feature row has no symbol and no page to link to."""
    monkeypatch.setattr(
        detail_data.string_db,
        "load_gene_level_edges",
        lambda **kwargs: (
            pl.DataFrame({"gene1": ["A", "A"], "gene2": ["B", "ZZ"], "score": [900, 950]}),
            SimpleNamespace(log=lambda: None),
        ),
    )

    result = detail_data.build_target_interactions(["A", "B"])

    # ZZ appears as neither an endpoint nor a partner. The surviving A<->B edge
    # is still expanded both ways, so "A" legitimately appears as B's partner.
    assert "ZZ" not in result.get_column("partner_target_id").to_list()
    assert "ZZ" not in result.get_column("target_id").to_list()
    assert result.filter(pl.col("target_id") == "A").get_column(
        "partner_target_id"
    ).to_list() == ["B"]


def test_build_target_interactions_keeps_only_the_strongest_top_n(monkeypatch):
    monkeypatch.setattr(
        detail_data.string_db,
        "load_gene_level_edges",
        lambda **kwargs: (
            pl.DataFrame({"gene1": ["A", "A", "A"], "gene2": ["B", "C", "D"], "score": [700, 900, 800]}),
            SimpleNamespace(log=lambda: None),
        ),
    )

    result = detail_data.build_target_interactions(["A", "B", "C", "D"], top_n=2)
    for_a = result.filter(pl.col("target_id") == "A")

    assert for_a.get_column("partner_target_id").to_list() == ["C", "D"]


# ---------------------------------------------------------------------------
# the service
# ---------------------------------------------------------------------------


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    """Write the three detail artifacts and point the service at them."""
    pathways = pl.DataFrame(
        {
            "target_id": [TARGET] * 3,
            "root_pathway_id": ["R-1", "R-1", "R-2"],
            "root_pathway_name": ["Immune System", "Immune System", "Metabolism"],
            "pathway_id": ["R-11", "R-12", "R-21"],
            "pathway_name": ["Alpha", "Beta", "Gamma"],
            "pathway_url": ["u11", "u12", "u21"],
        }
    )
    # Brain_Cortex is matched by the configured tissue "brain"; Liver is not.
    tissues = pl.DataFrame(
        {
            "target_id": [TARGET] * 3,
            "tissue": ["Brain_Cortex", "Liver", "Whole_Blood"],
            "median_tpm": [50.0, 5.0, 1.0],
        },
        schema={"target_id": pl.String, "tissue": pl.String, "median_tpm": pl.Float32},
    )
    interactions = pl.DataFrame(
        {
            "target_id": [TARGET, TARGET],
            "partner_target_id": ["ENSG_B", "ENSG_C"],
            "score": [999, 800],
        },
        schema={"target_id": pl.String, "partner_target_id": pl.String, "score": pl.UInt16},
    )
    # ENSG_B is a candidate for DISEASE; ENSG_C only for another disease, so it
    # must come back unlinkable rather than as a link that would 404.
    features = pl.DataFrame(
        {
            "disease_id": [DISEASE, DISEASE, OTHER_DISEASE],
            "target_id": [TARGET, "ENSG_B", "ENSG_C"],
            "gene_symbol": ["AAA", "BBB", "CCC"],
            "assoc_ds__europepmc_score": [0.9, 0.1, 0.2],
            "assoc_ds__europepmc_evidence_count": [120.0, 3.0, 4.0],
        }
    )

    paths = {}
    for name, frame in [
        ("PATHWAYS_PATH", pathways),
        ("TISSUES_PATH", tissues),
        ("INTERACTIONS_PATH", interactions),
        ("FEATURES_PATH", features),
    ]:
        path = tmp_path / f"{name.lower()}.parquet"
        frame.write_parquet(path)
        monkeypatch.setattr(evidence_detail, name, path)
        paths[name] = path

    monkeypatch.setattr(
        evidence_detail,
        "load_diseases",
        lambda: SimpleNamespace(
            diseases=[
                DiseaseSpec(
                    key="test_disease",
                    name="Test disease",
                    efo_id=DISEASE,
                    category="test",
                    relevant_tissues=["brain", "synovium"],
                )
            ]
        ),
    )
    return paths


def test_pathway_groups_are_grouped_and_counted_by_root(artifacts):
    detail = evidence_detail.build_evidence_detail(DISEASE, TARGET)

    assert detail.n_root_categories == 2
    assert len(detail.pathway_groups) == detail.n_root_categories
    # Largest group first.
    assert detail.pathway_groups[0].root_pathway_name == "Immune System"
    assert [p.name for p in detail.pathway_groups[0].pathways] == ["Alpha", "Beta"]


def test_relevant_tissue_is_flagged_by_the_same_matcher_as_the_feature(artifacts):
    detail = evidence_detail.build_evidence_detail(DISEASE, TARGET)

    flagged = {t.tissue for t in detail.tissues if t.is_relevant}
    assert flagged == {"Brain_Cortex"}
    assert detail.relevant_tissues_matched == {"brain": ["Brain_Cortex"]}


def test_configured_tissue_with_no_gtex_column_is_reported_not_dropped(artifacts):
    """GTEx has no synovial data at all (milestone4.md §1) — rheumatoid
    arthritis must render an explicit absence, not a blank panel."""
    detail = evidence_detail.build_evidence_detail(DISEASE, TARGET)

    assert detail.relevant_tissues_unmatched == ["synovium"]


def test_tissues_are_returned_descending_by_expression(artifacts):
    detail = evidence_detail.build_evidence_detail(DISEASE, TARGET)

    tpms = [t.median_tpm for t in detail.tissues]
    assert tpms == sorted(tpms, reverse=True)


def test_partner_outside_this_disease_is_marked_unlinkable(artifacts):
    detail = evidence_detail.build_evidence_detail(DISEASE, TARGET)

    by_symbol = {p.gene_symbol: p for p in detail.partners}
    assert by_symbol["BBB"].is_candidate is True
    assert by_symbol["CCC"].is_candidate is False


def test_partners_are_ordered_by_confidence(artifacts):
    detail = evidence_detail.build_evidence_detail(DISEASE, TARGET)

    assert [p.score for p in detail.partners] == [999, 800]


def test_literature_search_url_is_escaped(artifacts):
    detail = evidence_detail.build_evidence_detail(DISEASE, TARGET)

    assert detail.literature.europepmc_evidence_count == 120.0
    assert "AAA" in detail.literature.search_url
    assert " " not in detail.literature.search_url


def test_unknown_disease_raises_key_error(artifacts):
    with pytest.raises(KeyError):
        evidence_detail.build_evidence_detail("MONDO_NOPE", TARGET)


def test_pair_with_no_feature_row_raises_key_error(artifacts):
    with pytest.raises(KeyError):
        evidence_detail.build_evidence_detail(DISEASE, "ENSG_MISSING")


def test_missing_artifact_raises_file_not_found(artifacts, monkeypatch, tmp_path):
    monkeypatch.setattr(evidence_detail, "PATHWAYS_PATH", tmp_path / "absent.parquet")
    with pytest.raises(FileNotFoundError):
        evidence_detail.build_evidence_detail(DISEASE, TARGET)


def test_target_with_no_annotation_returns_empty_sections_not_an_error(artifacts):
    """49% of ranked targets have no Reactome annotation — an empty panel is a
    real answer, not a failure."""
    features = pl.read_parquet(artifacts["FEATURES_PATH"])
    extra = pl.DataFrame(
        {
            "disease_id": [DISEASE],
            "target_id": ["ENSG_BARE"],
            "gene_symbol": ["BARE"],
            "assoc_ds__europepmc_score": [None],
            "assoc_ds__europepmc_evidence_count": [None],
        },
        schema=features.schema,
    )
    pl.concat([features, extra]).write_parquet(artifacts["FEATURES_PATH"])

    detail = evidence_detail.build_evidence_detail(DISEASE, "ENSG_BARE")

    assert detail.pathway_groups == []
    assert detail.n_root_categories == 0
    assert detail.tissues == []
    assert detail.partners == []
    assert detail.literature.europepmc_score is None


# ---------------------------------------------------------------------------
# the endpoint
# ---------------------------------------------------------------------------

client = TestClient(main.app)


def test_endpoint_returns_detail(artifacts, monkeypatch):
    monkeypatch.setattr(main, "cached_features", lambda: pl.read_parquet(artifacts["FEATURES_PATH"]))

    response = client.get("/api/evidence/detail", params={"disease_id": DISEASE, "target_id": TARGET})

    assert response.status_code == 200
    body = response.json()
    assert body["gene_symbol"] == "AAA"
    assert body["n_root_categories"] == 2
    assert len(body["pathway_groups"]) == 2
    assert body["relevant_tissues_unmatched"] == ["synovium"]
    assert body["partner_min_score"] == detail_data.PARTNER_MIN_SCORE
    # §21's fourth detail item is declared absent, not rendered as empty.
    assert "Supporting literature" in body["not_buildable"]


def test_endpoint_404s_for_an_unknown_pair(artifacts, monkeypatch):
    monkeypatch.setattr(main, "cached_features", lambda: pl.read_parquet(artifacts["FEATURES_PATH"]))

    response = client.get(
        "/api/evidence/detail", params={"disease_id": DISEASE, "target_id": "ENSG_MISSING"}
    )

    assert response.status_code == 404


def test_endpoint_requires_both_parameters():
    assert client.get("/api/evidence/detail", params={"disease_id": DISEASE}).status_code == 422
