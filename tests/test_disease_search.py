"""Tests for the disease search service (Context.md §21, Milestone 3).

Exercised entirely against synthetic ``DiseaseSpec``/count/description
arguments — the search space is deliberately just the ten configured
diseases, so no raw Open Targets data or network access is needed to test
the matching logic itself.
"""

from __future__ import annotations

from target_prioritization.config import DiseaseSpec
from target_prioritization.services.disease_search import search_diseases, suggest

_DISEASES = [
    DiseaseSpec(
        key="parkinsons_disease",
        name="Parkinson's disease",
        efo_id="MONDO_0005180",
        resolved_name="Parkinson disease",
        category="neurodegenerative",
    ),
    DiseaseSpec(
        key="alzheimers_disease",
        name="Alzheimer's disease",
        efo_id="MONDO_0004975",
        resolved_name="Alzheimer disease",
        category="neurodegenerative",
    ),
    DiseaseSpec(
        key="type_2_diabetes",
        name="type II diabetes mellitus",
        efo_id="MONDO_0005148",
        resolved_name="type 2 diabetes mellitus",
        category="metabolic",
    ),
]


class TestSearchDiseases:
    def test_exact_name_match(self):
        results = search_diseases("Parkinson's disease", diseases=_DISEASES)
        assert [r.disease_id for r in results] == ["MONDO_0005180"]

    def test_matches_without_apostrophe(self):
        """Users will not reliably type the apostrophe."""
        results = search_diseases("parkinsons disease", diseases=_DISEASES)
        assert [r.disease_id for r in results] == ["MONDO_0005180"]

    def test_substring_match(self):
        results = search_diseases("diabetes", diseases=_DISEASES)
        assert [r.disease_id for r in results] == ["MONDO_0005148"]

    def test_matches_against_resolved_name_too(self):
        """'type 2' only appears in resolved_name, not the config name."""
        results = search_diseases("type 2 diabetes", diseases=_DISEASES)
        assert [r.disease_id for r in results] == ["MONDO_0005148"]

    def test_matches_against_key(self):
        results = search_diseases("alzheimers_disease", diseases=_DISEASES)
        assert [r.disease_id for r in results] == ["MONDO_0004975"]

    def test_no_match_is_a_plain_empty_list(self):
        """The search space is only the ten configured diseases — an
        unmatched query has no second case to represent, so this is the
        complete signal, not a partial one (module docstring)."""
        results = search_diseases("lupus", diseases=_DISEASES)
        assert results == []

    def test_empty_query_returns_everything(self):
        results = search_diseases("", diseases=_DISEASES)
        assert len(results) == 3

    def test_exact_match_sorts_before_substring_matches(self):
        diseases = [
            DiseaseSpec(key="a", name="colitis", efo_id="EFO_0000001", category="autoimmune"),
            DiseaseSpec(key="b", name="ulcerative colitis", efo_id="EFO_0000002", category="autoimmune"),
        ]
        results = search_diseases("colitis", diseases=diseases)
        assert [r.disease_id for r in results] == ["EFO_0000001", "EFO_0000002"]

    def test_results_are_alphabetical_among_non_exact_matches(self):
        results = search_diseases("disease", diseases=_DISEASES)
        names = [r.name for r in results]
        assert names == sorted(names)

    def test_limit_is_respected(self):
        results = search_diseases("", limit=2, diseases=_DISEASES)
        assert len(results) == 2

    def test_target_counts_and_descriptions_are_attached_when_provided(self):
        results = search_diseases(
            "Parkinson's disease",
            diseases=_DISEASES,
            target_counts={"MONDO_0005180": 8690},
            descriptions={"MONDO_0005180": "A neurodegenerative disorder."},
        )
        assert results[0].n_associated_targets == 8690
        assert results[0].description == "A neurodegenerative disorder."

    def test_missing_target_count_or_description_is_none_not_an_error(self):
        results = search_diseases(
            "Parkinson's disease", diseases=_DISEASES, target_counts={}, descriptions={}
        )
        assert results[0].n_associated_targets is None
        assert results[0].description is None

    def test_therapeutic_areas_carries_the_disease_category(self):
        results = search_diseases("Parkinson's disease", diseases=_DISEASES)
        assert results[0].therapeutic_areas == ["neurodegenerative"]


class TestSuggest:
    def test_prefix_match(self):
        assert suggest("park", diseases=_DISEASES) == ["Parkinson's disease"]

    def test_substring_not_matched_by_suggest(self):
        """suggest is prefix-only, unlike search_diseases's substring match —
        a still-being-typed query shouldn't surface unrelated results."""
        assert suggest("disease", diseases=_DISEASES) == []

    def test_empty_prefix_returns_everything_sorted(self):
        result = suggest("", diseases=_DISEASES)
        assert result == sorted(d.name for d in _DISEASES)

    def test_limit_is_respected(self):
        assert len(suggest("", limit=1, diseases=_DISEASES)) == 1
