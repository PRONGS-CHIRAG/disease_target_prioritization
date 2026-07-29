"""Typed configuration loading (Context.md §34: "store configuration outside the code").

The four YAML files in ``configs/`` are validated against pydantic models on
load. A typo in a config key therefore fails at startup with a precise message
rather than silently disabling a pipeline step — which matters most for
``features.yaml``, where a silently-dropped denylist rule would let the training
label leak into the feature matrix (Context.md §16).
"""

from __future__ import annotations

import fnmatch
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from target_prioritization.utils.paths import CONFIG_DIR

__all__ = [
    "DataSourcesConfig",
    "DatasetSpec",
    "DenylistRule",
    "DiseaseSpec",
    "DiseasesConfig",
    "FeaturesConfig",
    "ModelConfig",
    "Settings",
    "SourceSpec",
    "load_data_sources",
    "load_diseases",
    "load_features",
    "load_model_config",
    "load_yaml",
    "settings",
]


class _Base(BaseModel):
    """Reject unknown keys everywhere: a typo should fail, not be ignored."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Runtime settings (environment)
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    """Environment-driven runtime settings. See ``.env.example``."""

    model_config = ConfigDict(frozen=True)

    log_level: str = "INFO"
    log_json: bool = False
    download_concurrency: int = Field(default=4, ge=1, le=16)
    open_targets_api: str = "https://api.platform.opentargets.org/api/v4/graphql"
    open_targets_release: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        def _flag(name: str, default: bool) -> bool:
            raw = os.environ.get(name)
            return default if raw is None else raw.strip().lower() in {"1", "true", "yes"}

        return cls(
            log_level=os.environ.get("DTP_LOG_LEVEL", "INFO"),
            log_json=_flag("DTP_LOG_JSON", False),
            download_concurrency=int(os.environ.get("DTP_DOWNLOAD_CONCURRENCY", "4")),
            open_targets_api=os.environ.get(
                "DTP_OPEN_TARGETS_API",
                "https://api.platform.opentargets.org/api/v4/graphql",
            ),
            open_targets_release=os.environ.get("DTP_OPEN_TARGETS_RELEASE"),
        )


settings = Settings.from_env()


# ---------------------------------------------------------------------------
# data_sources.yaml
# ---------------------------------------------------------------------------


class DatasetSpec(_Base):
    """One downloadable dataset.

    For ``parquet_dir`` sources the dataset is a directory of partitioned
    parquet parts whose file list is discovered at fetch time; for ``files``
    sources *url* points at a single file.
    """

    name: str
    profiles: list[str] = Field(min_length=1)
    approx_mb: float = Field(ge=0)
    role: str
    url: str | None = None
    filename: str | None = None
    # Free-text warning surfaced by the downloader and carried into the
    # manifest. Used to flag tables that must never become features.
    leakage_note: str | None = None

    def in_profile(self, profile: str) -> bool:
        return profile in self.profiles


class SourceSpec(_Base):
    """A data provider and its datasets."""

    kind: Literal["parquet_dir", "files"]
    homepage: str
    license: str
    citation: str | None = None
    release: str | None = None
    # False when the URL contains no version (e.g. Reactome's `current/`), so
    # the fetch timestamp is the only version anchor (Context.md §32.7).
    release_pinned: bool = True
    base_url: str | None = None
    checksum_manifest_url: str | None = None
    datasets: list[DatasetSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_urls(self) -> SourceSpec:
        if self.kind == "parquet_dir":
            if not self.base_url:
                raise ValueError("parquet_dir sources require 'base_url'")
        else:
            missing = [d.name for d in self.datasets if not d.url]
            if missing:
                raise ValueError(f"'files' source datasets require a 'url': {missing}")
        return self

    def resolved_base_url(self) -> str:
        """Base URL with ``{release}`` substituted."""
        if not self.base_url:
            return ""
        return self.base_url.format(release=self.release or "")

    def dataset_url(self, dataset: DatasetSpec) -> str:
        if self.kind == "files":
            return (dataset.url or "").format(release=self.release or "")
        return f"{self.resolved_base_url().rstrip('/')}/{dataset.name}/"


class DataSourcesConfig(_Base):
    version: int
    profiles: list[str] = Field(min_length=1)
    sources: dict[str, SourceSpec]

    @model_validator(mode="after")
    def _check_profiles_exist(self) -> DataSourcesConfig:
        known = set(self.profiles)
        for source_name, source in self.sources.items():
            for dataset in source.datasets:
                if unknown := set(dataset.profiles) - known:
                    raise ValueError(
                        f"{source_name}/{dataset.name} references unknown "
                        f"profile(s) {sorted(unknown)}; known: {sorted(known)}"
                    )
        return self

    def select(self, profile: str) -> list[tuple[str, SourceSpec, DatasetSpec]]:
        """Datasets belonging to *profile*, in declaration order."""
        if profile not in self.profiles:
            raise KeyError(f"Unknown profile {profile!r}; known: {self.profiles}")
        return [
            (source_name, source, dataset)
            for source_name, source in self.sources.items()
            for dataset in source.datasets
            if dataset.in_profile(profile)
        ]


# ---------------------------------------------------------------------------
# diseases.yaml
# ---------------------------------------------------------------------------


class DiseaseSpec(_Base):
    """One MVP disease (Context.md §23).

    *efo_id* starts as null and is populated by ``scripts/resolve_diseases.py``
    from the Open Targets ``disease`` table. Context.md §32.6 names identifier
    errors as a top risk, so IDs are resolved from the release rather than
    typed by hand.
    """

    key: str
    name: str
    efo_id: str | None = None
    resolved_name: str | None = None
    category: str
    relevant_tissues: list[str] = Field(default_factory=list)
    is_cancer: bool = False
    milestone_1: bool = False
    notes: str | None = None

    @field_validator("efo_id")
    @classmethod
    def _check_efo(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not any(v.startswith(p) for p in ("EFO_", "MONDO_", "HP_", "Orphanet_", "OTAR_")):
            raise ValueError(f"Unexpected disease identifier format: {v!r}")
        return v


class DiseasesConfig(_Base):
    version: int
    resolved_against_release: str | None = None
    resolved_at: str | None = None
    diseases: list[DiseaseSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_unique(self) -> DiseasesConfig:
        keys = [d.key for d in self.diseases]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate disease keys in diseases.yaml")
        return self

    @property
    def resolved(self) -> list[DiseaseSpec]:
        return [d for d in self.diseases if d.efo_id]

    @property
    def unresolved(self) -> list[DiseaseSpec]:
        return [d for d in self.diseases if not d.efo_id]

    def by_key(self, key: str) -> DiseaseSpec:
        for disease in self.diseases:
            if disease.key == key:
                return disease
        raise KeyError(f"Unknown disease key {key!r}")

    def milestone_1_disease(self) -> DiseaseSpec:
        """The single disease for the first milestone (Context.md §36)."""
        flagged = [d for d in self.diseases if d.milestone_1]
        if len(flagged) != 1:
            raise ValueError(
                f"Exactly one disease must set milestone_1: true; found {len(flagged)}"
            )
        return flagged[0]


# ---------------------------------------------------------------------------
# features.yaml
# ---------------------------------------------------------------------------


class DenylistRule(_Base):
    """A column pattern that must never reach the model matrix.

    Context.md §16 lists using label-defining evidence as a feature as the
    canonical leakage mode for this project. Each rule carries its *reason* so
    a future reader can tell whether it still applies.

    *required* is the important flag: when true, the rule must match at least
    one real column, otherwise the build fails. Upstream renames a datasource
    (``chembl`` → ``clinical_precedence``) and an unrequired rule would quietly
    stop protecting anything.
    """

    id: str
    match: str
    reason: str
    required: bool = True

    def matches(self, column: str) -> bool:
        return fnmatch.fnmatch(column, self.match)


class LeakageGuardConfig(_Base):
    enabled: bool = True
    denylist: list[DenylistRule] = Field(default_factory=list)

    def find_violations(self, columns: list[str]) -> dict[str, list[str]]:
        """Map rule id → matching columns, for rules that matched anything."""
        hits = {rule.id: [c for c in columns if rule.matches(c)] for rule in self.denylist}
        return {rule_id: cols for rule_id, cols in hits.items() if cols}

    def unmatched_required_rules(self, columns: list[str]) -> list[DenylistRule]:
        """Required rules that matched nothing — a sign the guard has gone stale."""
        return [
            rule
            for rule in self.denylist
            if rule.required and not any(rule.matches(c) for c in columns)
        ]


class LabelConfig(_Base):
    """MVP label definition (Context.md §15)."""

    name: str
    source: str
    # Open Targets ships maxClinicalStage as a string enum (APPROVAL, PHASE_3,
    # ...). This maps those values onto the integer scale compared against
    # positive_min_clinical_stage. A null value means "exclude from both
    # classes" — UNKNOWN must not be silently treated as a negative.
    clinical_stage_map: dict[str, int | None] = Field(default_factory=dict)
    positive_min_clinical_stage: int = Field(ge=1, le=4)
    negative_definition: str
    output_path: str
    notes: str | None = None

    @model_validator(mode="after")
    def _check_stage_map_reaches_threshold(self) -> LabelConfig:
        """A threshold no stage can satisfy would yield zero positives."""
        if self.clinical_stage_map and not any(
            v is not None and v >= self.positive_min_clinical_stage
            for v in self.clinical_stage_map.values()
        ):
            raise ValueError(
                f"No clinical stage reaches positive_min_clinical_stage="
                f"{self.positive_min_clinical_stage}; the label would have no positives."
            )
        return self


class FeatureGroup(_Base):
    description: str
    source: str
    features: list[str] = Field(default_factory=list)
    # Context.md §32.3: absence of evidence is not evidence of absence.
    missing_indicator: bool = True
    log_transform: bool = False


class FeaturesConfig(_Base):
    version: int
    label: LabelConfig
    leakage_guard: LeakageGuardConfig
    groups: dict[str, FeatureGroup]


# ---------------------------------------------------------------------------
# model.yaml
# ---------------------------------------------------------------------------


class SplitConfig(_Base):
    strategy: Literal["leave_one_disease_out", "disease_group", "temporal", "random"]
    group_column: str = "disease_id"
    n_folds: int | None = None
    notes: str | None = None


class ModelConfig(_Base):
    version: int
    random_seed: int
    split: SplitConfig
    baseline_weights: dict[str, float]
    models: dict[str, dict[str, Any]]
    evaluation: dict[str, Any]

    @model_validator(mode="after")
    def _check_weights(self) -> ModelConfig:
        total = sum(self.baseline_weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"baseline_weights must sum to 1.0, got {total:.6f}")
        return self


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML mapping, with a clear error if the file is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping at the top level of {path}")
    return payload


@lru_cache(maxsize=1)
def load_data_sources(path: Path | None = None) -> DataSourcesConfig:
    return DataSourcesConfig.model_validate(load_yaml(path or CONFIG_DIR / "data_sources.yaml"))


@lru_cache(maxsize=1)
def load_diseases(path: Path | None = None) -> DiseasesConfig:
    return DiseasesConfig.model_validate(load_yaml(path or CONFIG_DIR / "diseases.yaml"))


@lru_cache(maxsize=1)
def load_features(path: Path | None = None) -> FeaturesConfig:
    return FeaturesConfig.model_validate(load_yaml(path or CONFIG_DIR / "features.yaml"))


@lru_cache(maxsize=1)
def load_model_config(path: Path | None = None) -> ModelConfig:
    return ModelConfig.model_validate(load_yaml(path or CONFIG_DIR / "model.yaml"))


def clear_config_cache() -> None:
    """Drop cached configs. Used by tests and by ``resolve_diseases.py``."""
    for loader in (load_data_sources, load_diseases, load_features, load_model_config):
        loader.cache_clear()
