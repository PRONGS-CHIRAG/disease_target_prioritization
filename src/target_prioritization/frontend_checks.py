"""Milestone 5 acceptance checks (milestone5_plan.md §6).

Runs against the real processed artifacts, the real fold models and the
real ten configured diseases — no synthetic data, the same standard
``app_checks.py`` (Milestone 3's analogous gate) holds itself to. Exercised
through FastAPI's ``TestClient`` in-process (no live server needed), using
the real ``lifespan`` handler so the fold-model/parquet warm-up runs too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from fastapi.testclient import TestClient

from target_prioritization.api.cache import cached_features
from target_prioritization.api.main import app
from target_prioritization.config import DiseaseSpec, load_diseases
from target_prioritization.utils.paths import PROJECT_ROOT

__all__ = ["CheckResult", "run_all_checks"]

# The three clinical-development columns app_scores.parquet carries that
# the training label is built from (Context.md §15) — invariant 3
# (milestone5_plan.md §3, §4.3). Deliberately NOT "any label__* field":
# `n_other_diseases_positive` is also label-derived and intentionally
# shipped (see api/schemas.py's RankedTargetResponse docstring).
_FORBIDDEN_LABEL_FIELDS = {"label__max_clinical_stage", "label__n_drugs", "label__drug_names"}

_FRONTEND_DIST = PROJECT_ROOT / "frontend" / "out"


@dataclass(slots=True)
class CheckResult:
    name: str
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def _check_all_endpoints_ok(client: TestClient, diseases: list[DiseaseSpec]) -> CheckResult:
    problems: list[str] = []
    for disease in diseases:
        disease_id = disease.efo_id
        assert disease_id is not None
        for method, path, kwargs in [
            ("get", f"/api/diseases/{disease_id}", {}),
            ("post", "/api/rank", {"json": {"disease_id": disease_id, "top_n": 5}}),
        ]:
            response = getattr(client, method)(path, **kwargs)
            if response.status_code != 200:
                problems.append(f"{method.upper()} {path} -> {response.status_code}: {response.text[:200]}")

        rank_response = client.post("/api/rank", json={"disease_id": disease_id, "top_n": 1})
        targets = rank_response.json().get("targets", [])
        if not targets:
            problems.append(f"{disease_id}: /api/rank returned no targets")
            continue
        target_id = targets[0]["target_id"]
        evidence_response = client.post(
            "/api/evidence", json={"disease_id": disease_id, "target_id": target_id}
        )
        if evidence_response.status_code != 200:
            problems.append(f"{disease_id}/{target_id}: /api/evidence -> {evidence_response.status_code}")

    for path in ["/health", "/api/health", "/api/meta", "/api/diseases"]:
        response = client.get(path)
        if response.status_code != 200:
            problems.append(f"GET {path} -> {response.status_code}")

    return CheckResult("all_endpoints_ok_for_every_disease", problems)


def _check_no_label_leakage(client: TestClient) -> CheckResult:
    schema = client.get("/openapi.json").json()
    fields = set(schema["components"]["schemas"]["RankedTargetResponse"]["properties"])
    leaked = fields & _FORBIDDEN_LABEL_FIELDS
    problems = [f"RankedTargetResponse exposes forbidden field {f!r}" for f in leaked]
    return CheckResult("no_label_leakage_on_ranking_response", problems)


def _check_null_dimensions_round_trip_as_null(client: TestClient, diseases: list[DiseaseSpec]) -> CheckResult:
    """Invariant 1: find a real target with a genuinely missing dimension
    and confirm the API reports it as JSON ``null``, not ``0`` — checked
    against real data, not a synthetic frame, so it also catches a
    serialization layer silently coercing the value."""
    features = cached_features()
    for disease in diseases:
        disease_id = disease.efo_id
        assert disease_id is not None
        row = (
            features.filter(
                (pl.col("disease_id") == disease_id) & pl.col("dim__genetics").is_null()
            )
            .head(1)
        )
        if row.is_empty():
            continue
        target_id = row.get_column("target_id")[0]
        evidence_response = client.post(
            "/api/evidence", json={"disease_id": disease_id, "target_id": target_id}
        )
        evidence = evidence_response.json()
        genetics = evidence.get("dimension_values", {}).get("genetics")
        if genetics is not None:
            return CheckResult(
                "null_dimension_round_trips_as_json_null",
                [f"{disease_id}/{target_id}: expected null genetics, got {genetics!r}"],
            )
        raw_text = evidence_response.text.replace(" ", "")
        if '"genetics":null' not in raw_text:
            return CheckResult(
                "null_dimension_round_trips_as_json_null",
                [f"{disease_id}/{target_id}: JSON body does not contain a literal null for genetics"],
            )
        return CheckResult("null_dimension_round_trips_as_json_null", [])
    return CheckResult(
        "null_dimension_round_trips_as_json_null",
        ["No disease had a target with a null dim__genetics value to check against"],
    )


def _check_target_family_rejected(client: TestClient, diseases: list[DiseaseSpec]) -> CheckResult:
    disease_id = diseases[0].efo_id
    response = client.post(
        "/api/rank",
        json={"disease_id": disease_id, "filters": {"target_family": "kinase"}},
    )
    problems = []
    if response.status_code != 400:
        problems.append(f"target_family filter -> {response.status_code}, expected 400")
    return CheckResult("target_family_filter_rejected", problems)


def _check_limitations_present(client: TestClient, diseases: list[DiseaseSpec]) -> CheckResult:
    disease_id = diseases[0].efo_id
    problems = []
    meta = client.get("/api/meta").json()
    if not meta.get("limitations"):
        problems.append("/api/meta carries no limitations")
    rank = client.post("/api/rank", json={"disease_id": disease_id, "top_n": 1}).json()
    if not rank.get("limitations"):
        problems.append("/api/rank carries no limitations")
    target_id = rank["targets"][0]["target_id"]
    evidence = client.post("/api/evidence", json={"disease_id": disease_id, "target_id": target_id}).json()
    if not evidence.get("limitations"):
        problems.append("/api/evidence carries no limitations")
    return CheckResult("limitations_present_on_every_scored_response", problems)


def _check_static_export_built(_: TestClient) -> CheckResult:
    problems = []
    index_html = _FRONTEND_DIST / "index.html"
    if not index_html.exists():
        problems.append(
            f"{index_html} not found — run `make frontend-build` before this check."
        )
        return CheckResult("static_export_built_with_no_external_origin", problems)
    text = index_html.read_text()
    for marker in ("http://", "https://"):
        if marker in text:
            problems.append(f"{index_html} references an external origin ({marker!r} found)")
    return CheckResult("static_export_built_with_no_external_origin", problems)


def run_all_checks(diseases: list[DiseaseSpec] | None = None) -> list[CheckResult]:
    diseases = diseases if diseases is not None else load_diseases().resolved
    if not diseases:
        raise ValueError("No resolved diseases in configs/diseases.yaml")

    with TestClient(app) as client:
        return [
            _check_all_endpoints_ok(client, diseases),
            _check_no_label_leakage(client),
            _check_null_dimensions_round_trip_as_null(client, diseases),
            _check_target_family_rejected(client, diseases),
            _check_limitations_present(client, diseases),
            _check_static_export_built(client),
        ]
