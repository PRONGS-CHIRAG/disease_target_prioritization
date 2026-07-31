"""Schema-level contract tests over the generated OpenAPI document
(milestone5_plan.md §4.3, §6 checks 2-3).

These check the *shape* of the API — properties that must hold no matter
what data flows through it — as opposed to ``tests/test_api.py``, which
checks behaviour against specific inputs. Both are needed: a leakage bug
that only manifests for certain data wouldn't necessarily show up in a
behavioural test, and a schema check can't verify runtime values.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import BaseModel

from target_prioritization.api import main
from target_prioritization.api.schemas import RankedTargetResponse

client = TestClient(main.app)

# The three clinical-development columns app_scores.parquet carries that the
# training label is built from (Context.md §15) — confirmed present in
# app_scores.parquet's schema. `n_other_diseases_positive` is DELIBERATELY
# NOT in this list: it is also label-derived (how many other diseases this
# target is a labelled positive in — target_ranking.py:157-160,
# milestone3_plan.md §2.2), but it is intentionally shipped on the ranking
# table as the per-target form of milestone2.md §1's popularity finding, so
# a denylist of "anything label-derived" would be wrong here — it would flag
# a field this project ships on purpose. This list names exactly the three
# columns that must never reach a ranking response.
_FORBIDDEN_LABEL_FIELDS = {"label__max_clinical_stage", "label__n_drugs", "label__drug_names"}


def _schema_field_names(model: type[BaseModel]) -> set[str]:
    return set(model.model_json_schema().get("properties", {}))


class TestNoLabelLeakageOnRankingResponse:
    def test_ranked_target_response_has_none_of_the_three_label_fields(self) -> None:
        assert _schema_field_names(RankedTargetResponse) & _FORBIDDEN_LABEL_FIELDS == set()

    def test_the_check_actually_fires(self) -> None:
        """A check that can never trip is not a check (the standard
        app_checks.py check 1 already holds itself to, per its own
        docstring) — verify by injecting one of the forbidden fields into a
        throwaway model and confirming the assertion catches it."""

        class _LeakyRankedTargetResponse(RankedTargetResponse):
            label__max_clinical_stage: int | None = None  # type: ignore[assignment]

        leaked = _schema_field_names(_LeakyRankedTargetResponse) & _FORBIDDEN_LABEL_FIELDS
        assert leaked == {"label__max_clinical_stage"}

    def test_openapi_rank_response_schema_has_none_of_the_three_label_fields(self) -> None:
        """Same assertion, but over the actual served OpenAPI document
        rather than the Pydantic model directly — catches a mismatch
        between the model and what FastAPI actually publishes."""
        schema = client.get("/openapi.json").json()
        ranked_target_schema = schema["components"]["schemas"]["RankedTargetResponse"]
        assert set(ranked_target_schema["properties"]) & _FORBIDDEN_LABEL_FIELDS == set()

    def test_n_other_diseases_positive_is_intentionally_present(self) -> None:
        """The one label-derived field that IS meant to ship — asserted
        explicitly so a future reader doesn't "fix" it into the denylist."""
        assert "n_other_diseases_positive" in _schema_field_names(RankedTargetResponse)


class TestNullPreservation:
    """Invariant 1 (milestone5_plan.md §3): a null evidence dimension must
    round-trip through JSON as null, never coerced to 0 — the single
    highest-risk regression this migration names."""

    def test_a_null_dimension_round_trips_as_json_null(self, monkeypatch) -> None:
        import polars as pl

        features = pl.DataFrame(
            {
                "disease_id": ["D1"],
                "target_id": ["T1"],
                "gene_symbol": ["G1"],
                "gene_name": ["Gene One"],
                "dim__genetics": [None],
                "dim__evidence_diversity": [0.5],
                "dim__functional": [0.5],
                "dim__literature": [0.5],
                "dim__druggability": [0.5],
                "missing__genetics": [1],
                "missing__functional": [0],
                "missing__druggability": [0],
                "missing__pathways": [0],
                "missing__network": [0],
                "missing__expression": [0],
                "expr__relevant_tissue_tpm": [1.0],
                "prio__has_small_molecule_binder": [0],
                "prio__has_safety_event": [None],
            }
        )
        app_data = pl.DataFrame(
            {
                "disease_id": ["D1"],
                "target_id": ["T1"],
                "xgboost_score_held_out": [0.5],
                "xgboost_rank_held_out": [1],
                "assoc_overall__score": [0.5],
                "n_other_diseases_positive": [0],
                "label__max_clinical_stage": [None],
                "label__n_drugs": [0],
                "label__drug_names": [None],
            }
        )
        monkeypatch.setattr(main, "cached_features", lambda: features)
        monkeypatch.setattr(main, "cached_app_data", lambda: app_data)

        response = client.post("/api/rank", json={"disease_id": "D1", "top_n": 1})
        raw_json = response.text
        target = response.json()["targets"][0]

        assert target["evidence"]["genetics"] is None
        # Not merely absent from the Python dict — actually the JSON literal
        # `null`, not a stringified "0" or a dropped key, which a naive
        # `value or 0` in a client would silently turn into a zero.
        assert '"genetics":null' in raw_json.replace(" ", "")
