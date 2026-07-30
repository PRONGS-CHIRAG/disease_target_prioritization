"""Tests for config loading and validation.

Context.md §34 requires configuration to live outside the code. These tests
check that a malformed config fails loudly at load time rather than silently
disabling a pipeline step.
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from target_prioritization.config import (
    DataSourcesConfig,
    DiseasesConfig,
    ModelConfig,
    load_data_sources,
    load_diseases,
    load_features,
    load_model_config,
)
from target_prioritization.utils.paths import CONFIG_DIR


class TestShippedConfigsAreValid:
    def test_data_sources_loads(self):
        assert load_data_sources().sources

    def test_diseases_loads(self):
        assert len(load_diseases().diseases) == 10

    def test_features_loads(self):
        assert load_features().groups

    def test_model_loads(self):
        assert load_model_config().random_seed == 42

    def test_all_configs_are_parseable_yaml(self):
        for name in ("data_sources", "diseases", "features", "model"):
            payload = yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text())
            assert isinstance(payload, dict), name


class TestDataSources:
    def test_core_is_a_subset_of_full(self):
        """`full` means "core plus more", so core must never contain extras."""
        config = load_data_sources()
        core = {(s, d.name) for s, _, d in config.select("core")}
        full = {(s, d.name) for s, _, d in config.select("full")}
        assert core <= full

    def test_core_excludes_the_oversized_tables(self):
        """Excluded deliberately; their signal arrives more cheaply elsewhere."""
        core = {d.name for _, _, d in load_data_sources().select("core")}
        assert "baseline_expression" not in core
        assert "evidence_europepmc" not in core

    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError, match="Unknown profile"):
            load_data_sources().select("nonexistent")

    def test_open_targets_release_is_pinned(self):
        """Context.md §32.7 — an unpinned primary source breaks reproducibility."""
        ot = load_data_sources().sources["open_targets"]
        assert ot.release
        assert ot.release_pinned

    def test_unversioned_sources_are_flagged(self):
        """Reactome/HGNC publish only a `current` URL; the flag records that."""
        sources = load_data_sources().sources
        assert sources["reactome"].release_pinned is False
        assert sources["hgnc"].release_pinned is False

    def test_every_dataset_declares_a_role(self):
        for _, _, dataset in load_data_sources().select("full"):
            assert dataset.role.strip(), f"{dataset.name} has no role"

    def test_dataset_urls_are_absolute(self):
        config = load_data_sources()
        for _, source, dataset in config.select("full"):
            assert source.dataset_url(dataset).startswith("https://")

    def test_release_placeholder_is_substituted(self):
        config = load_data_sources()
        ot = config.sources["open_targets"]
        url = ot.dataset_url(ot.datasets[0])
        assert "{release}" not in url
        assert "26.06" in url

    def test_unknown_profile_reference_is_rejected(self):
        with pytest.raises(ValidationError, match="unknown"):
            DataSourcesConfig.model_validate(
                {
                    "version": 1,
                    "profiles": ["core"],
                    "sources": {
                        "x": {
                            "kind": "files",
                            "homepage": "https://example.org",
                            "license": "CC0",
                            "datasets": [
                                {
                                    "name": "d",
                                    "profiles": ["typo_profile"],
                                    "approx_mb": 1,
                                    "role": "r",
                                    "url": "https://example.org/d",
                                }
                            ],
                        }
                    },
                }
            )

    def test_files_source_without_url_is_rejected(self):
        with pytest.raises(ValidationError, match="require a 'url'"):
            DataSourcesConfig.model_validate(
                {
                    "version": 1,
                    "profiles": ["core"],
                    "sources": {
                        "x": {
                            "kind": "files",
                            "homepage": "https://example.org",
                            "license": "CC0",
                            "datasets": [
                                {"name": "d", "profiles": ["core"], "approx_mb": 1, "role": "r"}
                            ],
                        }
                    },
                }
            )

    def test_typo_in_a_key_is_rejected(self):
        """extra='forbid' — a misspelled key must not be silently ignored."""
        with pytest.raises(ValidationError):
            DataSourcesConfig.model_validate(
                {
                    "version": 1,
                    "profiles": ["core"],
                    "sources": {},
                    "unexpected_key": True,
                }
            )


class TestDiseases:
    def test_exactly_one_milestone_1_disease(self):
        assert load_diseases().milestone_1_disease().key == "parkinsons_disease"

    def test_multiple_milestone_1_diseases_are_rejected(self):
        config = DiseasesConfig.model_validate(
            {
                "version": 1,
                "diseases": [
                    {"key": "a", "name": "A", "category": "x", "milestone_1": True},
                    {"key": "b", "name": "B", "category": "x", "milestone_1": True},
                ],
            }
        )
        with pytest.raises(ValueError, match="Exactly one"):
            config.milestone_1_disease()

    def test_duplicate_keys_are_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate"):
            DiseasesConfig.model_validate(
                {
                    "version": 1,
                    "diseases": [
                        {"key": "a", "name": "A", "category": "x"},
                        {"key": "a", "name": "A2", "category": "x"},
                    ],
                }
            )

    def test_malformed_efo_id_is_rejected(self):
        """Context.md §32.6 — identifier errors invent associations."""
        with pytest.raises(ValidationError, match="Unexpected disease identifier"):
            DiseasesConfig.model_validate(
                {
                    "version": 1,
                    "diseases": [
                        {"key": "a", "name": "A", "category": "x", "efo_id": "parkinsons"}
                    ],
                }
            )

    def test_spans_multiple_therapeutic_areas(self):
        """§23 — a single-area set cannot test generalization."""
        categories = {d.category for d in load_diseases().diseases}
        assert len(categories) >= 3

    def test_includes_cancer_and_non_cancer(self):
        diseases = load_diseases().diseases
        assert any(d.is_cancer for d in diseases)
        assert any(not d.is_cancer for d in diseases)

    def test_resolved_and_unresolved_partition_the_set(self):
        config = load_diseases()
        assert len(config.resolved) + len(config.unresolved) == len(config.diseases)


class TestModelConfig:
    def test_baseline_weights_sum_to_one(self):
        assert abs(sum(load_model_config().baseline_weights.values()) - 1.0) < 1e-9

    def test_unnormalised_weights_are_rejected(self):
        with pytest.raises(ValidationError, match=r"must sum to 1\.0"):
            ModelConfig.model_validate(
                {
                    "version": 1,
                    "random_seed": 1,
                    "split": {"strategy": "leave_one_disease_out"},
                    "baseline_weights": {"a": 0.5, "b": 0.9},
                    "models": {},
                    "evaluation": {
                        "aggregate_by": "disease_id",
                        "ranking_metrics": ["ndcg_at_10"],
                        "classification_metrics": ["pr_auc"],
                        "primary_metric": "ndcg_at_10",
                        "output_dir": "reports/evaluation",
                    },
                }
            )

    def test_split_is_not_random(self):
        """Context.md §19.4 — a random row split leaks diseases across folds."""
        assert load_model_config().split.strategy != "random"

    def test_split_groups_by_disease(self):
        assert load_model_config().split.group_column == "disease_id"

    def test_pr_auc_is_present(self):
        """§19.1 — ROC-AUC flatters under the class imbalance here."""
        assert "pr_auc" in load_model_config().evaluation.classification_metrics

    def test_overall_score_is_a_baseline_not_a_feature(self):
        """§16 — it may be compared against, never trained on."""
        evaluation = load_model_config().evaluation
        assert "open_targets_overall_score" in evaluation.baselines_for_comparison

    def test_target_popularity_baseline_is_configured(self):
        """Milestone 2 (Context.md §37) — measures cross-disease label leakage
        through target-intrinsic popularity rather than disease-specific
        signal; see milestone2.md §1."""
        assert "target_popularity" in load_model_config().evaluation.baselines_for_comparison

    def test_literature_ablation_is_configured(self):
        """§32.2 — measure how much performance is publication bias."""
        names = {a.name for a in load_model_config().evaluation.ablations}
        assert "no_literature" in names
