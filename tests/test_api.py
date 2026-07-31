"""Tests for the FastAPI application (Context.md §24/§25, milestone5_plan.md).

Two testing styles, matched to what each endpoint needs:

- ``/api/rank`` and ``/api/evidence`` patch ``main.cached_features`` /
  ``main.cached_app_data`` to return synthetic frames shaped exactly like
  ``disease_target_features.parquet`` / ``app_scores.parquet`` (the same
  frames ``tests/test_target_ranking.py`` uses), then run the REAL
  ``rank_for_disease`` / ``build_evidence_card`` / ``normalize_weights``
  against them — this exercises the actual filter, weight-normalization
  and leakage-boundary logic end-to-end, hermetically.
- ``/api/diseases*`` patch ``main.search_diseases`` directly with canned
  results — consistent with the pre-Milestone-5 style of this file, and
  simpler than constructing a synthetic ``configs/diseases.yaml``.
"""

from __future__ import annotations

import polars as pl
from fastapi.testclient import TestClient

from target_prioritization.api import main
from target_prioritization.services.disease_search import DiseaseSearchResult

client = TestClient(main.app)

DISEASE = "D1"

WEIGHTS = {
    "genetics": 0.4,
    "evidence_diversity": 0.2,
    "functional": 0.15,
    "literature": 0.15,
    "druggability": 0.1,
}


def _features() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "disease_id": [DISEASE] * 4,
            "target_id": ["T1", "T2", "T3", "T4"],
            "gene_symbol": ["G1", "G2", "G3", "G4"],
            "gene_name": ["Gene One", "Gene Two", "Gene Three", "Gene Four"],
            "dim__genetics": [0.9, 0.1, None, 0.5],
            "dim__evidence_diversity": [0.8, 0.2, 0.5, 0.5],
            "dim__functional": [0.7, None, 0.3, 0.4],
            "dim__literature": [0.6, 0.6, 0.6, 0.6],
            "dim__druggability": [1.0, 0.0, 0.5, None],
            "missing__genetics": [0, 0, 1, 0],
            "missing__functional": [0, 1, 0, 0],
            "missing__druggability": [0, 0, 0, 1],
            "missing__pathways": [0, 1, 0, 0],
            "missing__network": [0, 0, 1, 0],
            "missing__expression": [0, 0, 0, 1],
            "expr__relevant_tissue_tpm": [5.0, 0.5, 2.0, None],
            "prio__has_small_molecule_binder": [1, 0, 1, 0],
            "prio__has_safety_event": [None, -1, None, None],
        }
    )


def _app_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "disease_id": [DISEASE] * 4,
            "target_id": ["T1", "T2", "T3", "T4"],
            "xgboost_score_held_out": [0.2, 0.9, 0.5, 0.4],
            "xgboost_rank_held_out": [4, 1, 2, 3],
            "assoc_overall__score": [0.5, 0.5, 0.5, 0.5],
            "n_other_diseases_positive": [3, 0, 1, 0],
            "label__max_clinical_stage": [4, None, 2, None],
            "label__n_drugs": [2, 0, 1, 0],
            "label__drug_names": ["DRUGA, DRUGB", None, "DRUGC", None],
        }
    )


def _patch_caches(monkeypatch, *, features: pl.DataFrame | None = None, app_data: pl.DataFrame | None = None) -> None:
    monkeypatch.setattr(main, "cached_features", lambda: features if features is not None else _features())
    monkeypatch.setattr(main, "cached_app_data", lambda: app_data if app_data is not None else _app_data())


def _raise_features_not_found() -> pl.DataFrame:
    raise FileNotFoundError("disease_target_features.parquet not found")


class TestLifespan:
    def test_startup_warms_caches_without_raising(self) -> None:
        """Starlette only runs `lifespan` under the context-manager form of
        TestClient — the module-level `client` used everywhere else in this
        file never exercises it. Runs against the REAL processed artifacts
        and REAL fold models (no monkeypatching), because that is exactly
        what happens in the container at boot: a missing or malformed fold
        model must not crash startup (main.lifespan's broad `except
        Exception` around load_fitted_xgboost)."""
        with TestClient(main.app) as warm_client:
            response = warm_client.get("/health")
            assert response.status_code == 200


class TestHealth:
    def test_root_health_ok(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_api_health_matches_root(self) -> None:
        assert client.get("/api/health").json() == client.get("/health").json()


class TestMeta:
    def test_scenario_presets_are_well_formed(self) -> None:
        body = client.get("/api/meta").json()
        assert body["scenario_presets"], "at least one scenario preset"
        for preset in body["scenario_presets"]:
            assert set(preset["weights"]) <= set(body["dimension_keys"])
            assert abs(sum(preset["weights"].values()) - 1.0) < 1e-6

    def test_dimension_keys_and_labels_agree(self) -> None:
        body = client.get("/api/meta").json()
        assert set(body["dimension_keys"]) == set(body["dimension_labels"])

    def test_default_weights_sum_to_one(self) -> None:
        body = client.get("/api/meta").json()
        assert abs(sum(body["default_weights"].values()) - 1.0) < 1e-6

    def test_safety_first_uses_default_weights(self) -> None:
        body = client.get("/api/meta").json()
        assert body["safety_first"]["weights"] == body["default_weights"]

    def test_six_evidence_categories(self) -> None:
        body = client.get("/api/meta").json()
        assert len(body["evidence_categories"]) == 6

    def test_limitations_present(self) -> None:
        body = client.get("/api/meta").json()
        assert len(body["not_buildable"]) >= 1
        assert body["custom_slug"] and body["custom_label"]


class TestDiseases:
    def _canned_result(self) -> DiseaseSearchResult:
        return DiseaseSearchResult(
            disease_id="MONDO_TEST",
            name="Test disease",
            description="A synthetic disease for tests.",
            therapeutic_areas=["testing"],
            n_associated_targets=42,
        )

    def test_list_diseases(self, monkeypatch) -> None:
        monkeypatch.setattr(main, "search_diseases", lambda q: [self._canned_result()])
        response = client.get("/api/diseases")
        assert response.status_code == 200
        assert response.json() == [
            {
                "disease_id": "MONDO_TEST",
                "name": "Test disease",
                "description": "A synthetic disease for tests.",
                "therapeutic_areas": ["testing"],
                "n_associated_targets": 42,
            }
        ]

    def test_search_diseases_forwards_query(self, monkeypatch) -> None:
        captured: dict[str, object] = {}

        def _search(q: str) -> list[DiseaseSearchResult]:
            captured["q"] = q
            return [self._canned_result()]

        monkeypatch.setattr(main, "search_diseases", _search)
        response = client.get("/api/diseases/search", params={"q": "test"})
        assert response.status_code == 200
        assert captured["q"] == "test"

    def test_disease_detail_found(self, monkeypatch) -> None:
        monkeypatch.setattr(main, "search_diseases", lambda q: [self._canned_result()])
        app_data_with_release = _app_data().with_columns(
            pl.lit("26.06").alias("dataset_version"), pl.lit("2026-01-01").alias("extraction_date")
        )
        _patch_caches(monkeypatch, app_data=app_data_with_release)
        response = client.get("/api/diseases/MONDO_TEST")
        assert response.status_code == 200
        body = response.json()
        assert body["evidence_categories_total"] == 6
        assert body["evidence_categories_built"] == 6
        assert len(body["evidence_coverage"]) == 6
        assert body["dataset_version"] == "26.06"
        assert body["extraction_date"] == "2026-01-01"

    def test_disease_detail_not_found(self, monkeypatch) -> None:
        monkeypatch.setattr(main, "search_diseases", lambda q: [])
        response = client.get("/api/diseases/MONDO_DOES_NOT_EXIST")
        assert response.status_code == 404

    def test_disease_detail_degrades_gracefully_when_artifacts_missing(self, monkeypatch) -> None:
        monkeypatch.setattr(main, "search_diseases", lambda q: [self._canned_result()])
        monkeypatch.setattr(main, "cached_features", _raise_features_not_found)
        monkeypatch.setattr(main, "cached_app_data", _raise_features_not_found)
        response = client.get("/api/diseases/MONDO_TEST")
        assert response.status_code == 200
        body = response.json()
        assert body["evidence_categories_built"] == 0
        assert body["dataset_version"] is None


class TestRank:
    def test_successful_rank_default_weights(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/rank", json={"disease_id": DISEASE, "top_n": 10})
        assert response.status_code == 200
        body = response.json()
        assert body["total_candidates"] == 4
        assert len(body["targets"]) == 4
        assert body["sort_by"] == "weighted_baseline"
        assert len(body["limitations"]) == 5

    def test_scenario_weights_change_the_score(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        default = client.post("/api/rank", json={"disease_id": DISEASE, "top_n": 10}).json()
        literature_heavy = client.post(
            "/api/rank",
            json={
                "disease_id": DISEASE,
                "top_n": 10,
                "weights": {
                    "genetics": 0.0,
                    "evidence_diversity": 0.0,
                    "functional": 0.0,
                    "literature": 1.0,
                    "druggability": 0.0,
                },
            },
        ).json()
        assert default["targets"][0]["score"] != literature_heavy["targets"][0]["score"]
        assert literature_heavy["weights_used"]["literature"] == 1.0

    def test_weights_used_is_normalized_not_raw(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank",
            json={
                "disease_id": DISEASE,
                "weights": {
                    "genetics": 2.0,
                    "evidence_diversity": 2.0,
                    "functional": 2.0,
                    "literature": 2.0,
                    "druggability": 2.0,
                },
            },
        )
        weights_used = response.json()["weights_used"]
        assert abs(sum(weights_used.values()) - 1.0) < 1e-6
        assert weights_used["genetics"] == weights_used["druggability"]

    def test_negative_weight_returns_400(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank", json={"disease_id": DISEASE, "weights": {"genetics": -1.0, "literature": 2.0}}
        )
        assert response.status_code == 400

    def test_evidence_breakdown_preserves_null_not_zero(self, monkeypatch) -> None:
        """Invariant 1 (milestone5_plan.md §3): a target with no genetics
        evidence must serialize genetics as JSON null, never 0."""
        _patch_caches(monkeypatch)
        response = client.post("/api/rank", json={"disease_id": DISEASE, "top_n": 10})
        by_id = {t["target_id"]: t for t in response.json()["targets"]}
        assert by_id["T3"]["evidence"]["genetics"] is None
        assert by_id["T1"]["evidence"]["genetics"] == 0.9

    def test_pathways_expression_network_safety_are_null_on_ranking_table(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/rank", json={"disease_id": DISEASE, "top_n": 10})
        target = response.json()["targets"][0]
        assert target["evidence"]["pathways"] is None
        assert target["evidence"]["expression"] is None
        assert target["evidence"]["network"] is None
        assert target["evidence"]["safety"] is None

    def test_evidence_completeness_count_and_total(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/rank", json={"disease_id": DISEASE, "top_n": 10})
        by_id = {t["target_id"]: t for t in response.json()["targets"]}
        t1 = by_id["T1"]
        assert t1["evidence_completeness_total"] == 6
        assert t1["evidence_completeness_count"] == 6
        assert t1["evidence_completeness"] == 1.0

    def test_min_genetics_evidence_filter(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank",
            json={"disease_id": DISEASE, "top_n": 10, "filters": {"min_genetics_evidence": 0.5}},
        )
        ids = {t["target_id"] for t in response.json()["targets"]}
        assert ids == {"T1", "T4"}  # T1: 0.9, T4: 0.5 (>= threshold); T2: 0.1, T3: null->0

    def test_require_druggable_filter(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank", json={"disease_id": DISEASE, "top_n": 10, "filters": {"require_druggable": True}}
        )
        ids = {t["target_id"] for t in response.json()["targets"]}
        assert ids == {"T1", "T3"}

    def test_exclude_safety_concerns_filter(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank",
            json={"disease_id": DISEASE, "top_n": 10, "filters": {"exclude_safety_concerns": True}},
        )
        ids = {t["target_id"] for t in response.json()["targets"]}
        assert "T2" not in ids  # T2 carries the -1 safety liability flag

    def test_relevant_tissue_filter(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank", json={"disease_id": DISEASE, "top_n": 10, "filters": {"relevant_tissue": True}}
        )
        ids = {t["target_id"] for t in response.json()["targets"]}
        assert ids == {"T1", "T3"}  # T2 below threshold, T4 null (treated as failing)

    def test_target_family_filter_returns_400(self, monkeypatch) -> None:
        """Invariant 6: target_family stays unbuildable and must not be
        silently ignored — the filter raises rather than accepting."""
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank", json={"disease_id": DISEASE, "filters": {"target_family": "kinase"}}
        )
        assert response.status_code == 400

    def test_rank_reflects_full_population_not_filtered_subset(self, monkeypatch) -> None:
        """Invariant 9: a target's rank is its place among every candidate,
        not among filter survivors — ranks may have gaps."""
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/rank", json={"disease_id": DISEASE, "top_n": 10, "filters": {"require_druggable": True}}
        )
        ranks = {t["target_id"]: t["rank"] for t in response.json()["targets"]}
        # T1 (score 0.815) ranks 1st overall; T3 ranks lower once T2's/T4's
        # scores are counted even though they don't survive the filter.
        assert ranks["T1"] == 1
        assert ranks["T3"] > 2

    def test_unknown_disease_returns_404(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/rank", json={"disease_id": "MONDO_9999999"})
        assert response.status_code == 404

    def test_missing_artifacts_returns_503(self, monkeypatch) -> None:
        monkeypatch.setattr(main, "cached_features", _raise_features_not_found)
        response = client.post("/api/rank", json={"disease_id": DISEASE})
        assert response.status_code == 503

    def test_top_n_out_of_range_is_rejected(self) -> None:
        response = client.post("/api/rank", json={"disease_id": DISEASE, "top_n": 0})
        assert response.status_code == 422

    def test_unknown_sort_by_is_rejected(self) -> None:
        response = client.post("/api/rank", json={"disease_id": DISEASE, "sort_by": "nonsense"})
        assert response.status_code == 422

    def test_source_links_present(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/rank", json={"disease_id": DISEASE, "top_n": 1})
        assert response.json()["targets"][0]["source_links"]


class TestEvidence:
    def test_successful_evidence(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/evidence", json={"disease_id": DISEASE, "target_id": "T1", "weights": WEIGHTS})
        assert response.status_code == 200
        body = response.json()
        assert body["gene_symbol"] == "G1"
        assert body["rank"] == 1
        assert body["total_candidates"] == 4

    def test_contributions_sum_exactly_to_score(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/evidence", json={"disease_id": DISEASE, "target_id": "T2"})
        body = response.json()
        assert abs(sum(body["contributions"].values()) - body["score"]) < 1e-9

    def test_dimension_values_preserve_null(self, monkeypatch) -> None:
        """Invariant 1: T3 has no dim__genetics evidence — must be null."""
        _patch_caches(monkeypatch)
        response = client.post("/api/evidence", json={"disease_id": DISEASE, "target_id": "T3"})
        assert response.json()["dimension_values"]["genetics"] is None

    def test_drug_label_fields_present_but_not_on_ranking_table(self, monkeypatch) -> None:
        """Invariant 3: label__* fields are context on the evidence card
        only — never reachable from RankedTargetResponse."""
        _patch_caches(monkeypatch)
        response = client.post("/api/evidence", json={"disease_id": DISEASE, "target_id": "T1"})
        body = response.json()
        assert body["label_n_drugs"] == 2
        assert body["label_drug_names"] == "DRUGA, DRUGB"
        assert body["label_max_clinical_stage"] == 4

    def test_not_buildable_items_present(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/evidence", json={"disease_id": DISEASE, "target_id": "T1"})
        assert "Direction of effect" in response.json()["not_buildable"]

    def test_unknown_target_returns_404(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post("/api/evidence", json={"disease_id": DISEASE, "target_id": "DOES_NOT_EXIST"})
        assert response.status_code == 404

    def test_missing_artifacts_returns_503(self, monkeypatch) -> None:
        monkeypatch.setattr(main, "cached_features", _raise_features_not_found)
        response = client.post("/api/evidence", json={"disease_id": DISEASE, "target_id": "T1"})
        assert response.status_code == 503

    def test_negative_weight_returns_400(self, monkeypatch) -> None:
        _patch_caches(monkeypatch)
        response = client.post(
            "/api/evidence", json={"disease_id": DISEASE, "target_id": "T1", "weights": {"genetics": -1.0}}
        )
        assert response.status_code == 400
