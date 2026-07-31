"""Tests for the FastAPI `/rank` endpoint (Context.md §24/§25, Milestone 4 Phase 0).

Exercised with FastAPI's ``TestClient`` against
``services.target_ranking.rank_for_disease`` patched to return canned
``RankedTarget``s — consistent with the rest of this suite (see
tests/test_target_ranking.py's module docstring), which prefers synthetic
data injected explicitly over depending on the real processed parquets
being built. ``rank_for_disease`` itself is already tested end-to-end
against synthetic frames elsewhere; what's new here is the request/response
contract this thin wrapper adds, and its exception -> HTTP status mapping.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from target_prioritization.api import main
from target_prioritization.services.target_ranking import RankedTarget

client = TestClient(main.app)


def _ranked_target(**overrides: object) -> RankedTarget:
    defaults: dict[str, object] = {
        "rank": 1,
        "target_id": "ENSG00000188906",
        "gene_symbol": "LRRK2",
        "gene_name": "leucine rich repeat kinase 2",
        "score": 0.87,
        "weighted_baseline_score": 0.87,
        "xgboost_score_held_out": 0.9,
        "evidence": {
            "genetics": 0.9,
            "evidence_diversity": 0.8,
            "functional": 0.7,
            "literature": 0.6,
            "druggability": 1.0,
        },
        "app_evidence_completeness": 0.5,
        "missing_evidence": ["expression", "network", "pathway"],
        "n_other_diseases_positive": 2,
        "source_links": {"open_targets": "https://platform.opentargets.org/target/ENSG00000188906"},
    }
    defaults.update(overrides)
    return RankedTarget(**defaults)  # type: ignore[arg-type]


class TestHealth:
    def test_health_ok(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestRank:
    def test_successful_rank(self, monkeypatch) -> None:
        monkeypatch.setattr(
            main, "rank_for_disease", lambda disease_id, filters, top_n: [_ranked_target()]
        )
        response = client.post("/rank", json={"disease_id": "MONDO_0005180", "top_n": 10})
        assert response.status_code == 200
        body = response.json()
        assert body["disease_id"] == "MONDO_0005180"
        assert body["disease_name"] == "Parkinson's disease"
        assert body["model_version"] == main.__version__
        assert len(body["limitations"]) == 5

        target = body["targets"][0]
        assert target["gene_symbol"] == "LRRK2"
        assert target["evidence"]["genetics"] == 0.9
        # Pathways/expression/network aren't built yet (Milestone 4 Phase 5+) —
        # the contract reports them as null, not omitted.
        assert target["evidence"]["pathways"] is None
        assert target["evidence"]["network"] is None
        assert target["evidence"]["safety"] is None
        assert target["missing_evidence"] == ["expression", "network", "pathway"]

    def test_unresolved_gene_symbol_falls_back_to_target_id(self, monkeypatch) -> None:
        monkeypatch.setattr(
            main,
            "rank_for_disease",
            lambda disease_id, filters, top_n: [_ranked_target(gene_symbol=None, gene_name=None)],
        )
        response = client.post("/rank", json={"disease_id": "MONDO_0005180"})
        target = response.json()["targets"][0]
        assert target["gene_symbol"] == "ENSG00000188906"
        assert target["gene_name"] == ""

    def test_unknown_disease_returns_404(self, monkeypatch) -> None:
        def _raise(disease_id: str, filters: object, top_n: object) -> list[RankedTarget]:
            raise KeyError(f"No features for disease_id {disease_id!r}")

        monkeypatch.setattr(main, "rank_for_disease", _raise)
        response = client.post("/rank", json={"disease_id": "MONDO_9999999"})
        assert response.status_code == 404

    def test_missing_artifacts_returns_503(self, monkeypatch) -> None:
        def _raise(disease_id: str, filters: object, top_n: object) -> list[RankedTarget]:
            raise FileNotFoundError("disease_target_features.parquet not found")

        monkeypatch.setattr(main, "rank_for_disease", _raise)
        response = client.post("/rank", json={"disease_id": "MONDO_0005180"})
        assert response.status_code == 503

    def test_filters_and_top_n_are_forwarded(self, monkeypatch) -> None:
        captured: dict[str, object] = {}

        def _capture(disease_id: str, filters: object, top_n: object) -> list[RankedTarget]:
            captured["disease_id"] = disease_id
            captured["filters"] = filters
            captured["top_n"] = top_n
            return []

        monkeypatch.setattr(main, "rank_for_disease", _capture)
        client.post(
            "/rank",
            json={
                "disease_id": "MONDO_0005180",
                "top_n": 5,
                "min_genetics_evidence": 0.5,
                "require_druggable": True,
            },
        )
        filters = captured["filters"]
        assert captured["disease_id"] == "MONDO_0005180"
        assert captured["top_n"] == 5
        assert filters.min_genetics_evidence == 0.5  # type: ignore[attr-defined]
        assert filters.require_druggable is True  # type: ignore[attr-defined]

    def test_unresolved_disease_name_falls_back_to_id(self, monkeypatch) -> None:
        monkeypatch.setattr(main, "rank_for_disease", lambda disease_id, filters, top_n: [])
        response = client.post("/rank", json={"disease_id": "MONDO_DOES_NOT_EXIST"})
        assert response.status_code == 200
        assert response.json()["disease_name"] == "MONDO_DOES_NOT_EXIST"

    def test_top_n_out_of_range_is_rejected(self) -> None:
        response = client.post("/rank", json={"disease_id": "MONDO_0005180", "top_n": 0})
        assert response.status_code == 422
