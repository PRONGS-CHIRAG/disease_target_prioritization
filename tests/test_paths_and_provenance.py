"""Tests for path resolution and download provenance.

Context.md §33 requires every experiment to record its dataset source, version
and extraction date; §32.7 names data-version drift as a top risk. The manifest
is that record, so it gets tests.
"""

from __future__ import annotations

import json

import pytest

from target_prioritization.utils import paths
from target_prioritization.utils.paths import (
    CONFIG_DIR,
    DATA_RAW,
    PROJECT_ROOT,
    ensure_dir,
    find_project_root,
    raw_dir,
    relative_to_root,
)
from target_prioritization.utils.provenance import (
    Manifest,
    build_manifest,
    manifest_path_for,
    read_manifest,
    sha256_file,
    verify_file,
    write_manifest,
)


class TestPaths:
    def test_project_root_contains_pyproject(self):
        assert (PROJECT_ROOT / "pyproject.toml").exists()

    def test_config_dir_holds_the_four_configs(self):
        for name in ("data_sources", "diseases", "features", "model"):
            assert (CONFIG_DIR / f"{name}.yaml").exists()

    def test_data_layers_are_separate(self):
        """Context.md §34 — raw stays immutable, so the layers must not alias."""
        layers = {paths.DATA_RAW, paths.DATA_INTERIM, paths.DATA_PROCESSED, paths.DATA_EXTERNAL}
        assert len(layers) == 4

    def test_root_is_found_from_a_nested_directory(self):
        assert find_project_root(PROJECT_ROOT / "src" / "target_prioritization") == PROJECT_ROOT

    def test_root_override_is_honoured(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DTP_PROJECT_ROOT", str(tmp_path))
        assert find_project_root() == tmp_path.resolve()

    def test_missing_root_raises_rather_than_guessing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DTP_PROJECT_ROOT", raising=False)
        with pytest.raises(RuntimeError, match="Could not locate the project root"):
            find_project_root(tmp_path)

    def test_raw_dir_builds_nested_paths(self):
        assert raw_dir("open_targets", "target") == DATA_RAW / "open_targets" / "target"

    def test_relative_to_root_shortens_in_repo_paths(self):
        assert relative_to_root(CONFIG_DIR / "model.yaml") == "configs/model.yaml"

    def test_relative_to_root_falls_back_for_outside_paths(self, tmp_path):
        """A relocated DTP_DATA_DIR lies outside the repo; don't crash on it."""
        outside = tmp_path / "elsewhere.txt"
        assert relative_to_root(outside) == str(outside)

    def test_ensure_dir_is_idempotent(self, tmp_path):
        target = tmp_path / "a" / "b"
        assert ensure_dir(target) == target
        assert ensure_dir(target).is_dir()


class TestProvenance:
    @pytest.fixture
    def data_file(self, tmp_path):
        path = tmp_path / "example.parquet"
        path.write_bytes(b"some bytes representing a dataset")
        return path

    def test_sha256_is_stable(self, data_file):
        assert sha256_file(data_file) == sha256_file(data_file)

    def test_sha256_changes_with_content(self, data_file, tmp_path):
        other = tmp_path / "other.parquet"
        other.write_bytes(b"different bytes")
        assert sha256_file(data_file) != sha256_file(other)

    def test_manifest_path_is_a_sibling(self, data_file):
        assert manifest_path_for(data_file).name == "example.parquet.manifest.json"

    def test_manifest_records_what_reproducibility_needs(self, data_file, tmp_path):
        """Context.md §33 — source, version and extraction date, at minimum."""
        manifest = build_manifest(
            data_file,
            source="open_targets",
            dataset="target",
            url="https://example.org/target",
            release="26.06",
            license="CC0 1.0",
        )
        assert manifest.source == "open_targets"
        assert manifest.release == "26.06"
        assert manifest.license == "CC0 1.0"
        assert manifest.bytes == data_file.stat().st_size
        assert manifest.sha256
        assert manifest.fetched_at.endswith("+00:00")

    def test_write_and_read_round_trip(self, data_file, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "target_prioritization.utils.provenance.RAW_MANIFEST_LOG",
            tmp_path / "_manifest.jsonl",
        )
        original = build_manifest(
            data_file, source="gtex", dataset="gene_median_tpm", url="https://example.org/g"
        )
        write_manifest(data_file, original)

        loaded = read_manifest(data_file)
        assert loaded is not None
        assert loaded.sha256 == original.sha256
        assert loaded.dataset == "gene_median_tpm"

    def test_append_log_accumulates(self, data_file, tmp_path, monkeypatch):
        log_path = tmp_path / "_manifest.jsonl"
        monkeypatch.setattr("target_prioritization.utils.provenance.RAW_MANIFEST_LOG", log_path)
        for dataset in ("a", "b"):
            write_manifest(
                data_file,
                build_manifest(data_file, source="s", dataset=dataset, url="https://example.org/x"),
            )
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert {json.loads(line)["dataset"] for line in lines} == {"a", "b"}

    def test_unpinned_source_is_flagged(self, data_file):
        """Reactome publishes only `current/`; the flag records that."""
        manifest = build_manifest(
            data_file,
            source="reactome",
            dataset="pathways",
            url="https://reactome.org/download/current/ReactomePathways.txt",
            version_pinned=False,
        )
        assert manifest.version_pinned is False

    def test_verify_passes_for_an_untouched_file(self, data_file, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "target_prioritization.utils.provenance.RAW_MANIFEST_LOG",
            tmp_path / "_manifest.jsonl",
        )
        write_manifest(
            data_file,
            build_manifest(data_file, source="s", dataset="d", url="https://example.org/x"),
        )
        ok, detail = verify_file(data_file)
        assert ok, detail

    def test_verify_detects_corruption(self, data_file, tmp_path, monkeypatch):
        """The whole point: silent bit-rot must not pass as valid data."""
        monkeypatch.setattr(
            "target_prioritization.utils.provenance.RAW_MANIFEST_LOG",
            tmp_path / "_manifest.jsonl",
        )
        write_manifest(
            data_file,
            build_manifest(data_file, source="s", dataset="d", url="https://example.org/x"),
        )
        data_file.write_bytes(b"corrupted contents of a different length")

        ok, detail = verify_file(data_file)
        assert not ok
        assert "mismatch" in detail

    def test_verify_reports_a_missing_file(self, tmp_path):
        ok, detail = verify_file(tmp_path / "gone.parquet")
        assert not ok
        assert "missing" in detail

    def test_verify_without_a_manifest_fails_closed(self, data_file):
        """No provenance means unverifiable, which must not read as verified."""
        ok, detail = verify_file(data_file)
        assert not ok
        assert "no manifest" in detail

    def test_verify_accepts_an_explicit_checksum(self, data_file):
        ok, _ = verify_file(data_file, sha256_file(data_file))
        assert ok

    def test_manifest_survives_unknown_future_fields(self, data_file, tmp_path, monkeypatch):
        """A newer writer adding a field must not break an older reader."""
        monkeypatch.setattr(
            "target_prioritization.utils.provenance.RAW_MANIFEST_LOG",
            tmp_path / "_manifest.jsonl",
        )
        manifest = build_manifest(data_file, source="s", dataset="d", url="https://example.org/x")
        write_manifest(data_file, manifest)

        path = manifest_path_for(data_file)
        payload = json.loads(path.read_text())
        payload["some_future_field"] = "value"
        path.write_text(json.dumps(payload))

        loaded = read_manifest(data_file)
        assert loaded is not None
        assert loaded.sha256 == manifest.sha256

    def test_manifest_serialises_to_json(self, data_file):
        manifest = Manifest(
            source="s",
            dataset="d",
            url="https://example.org/x",
            path="data/raw/x",
            bytes=10,
            sha256="abc",
            fetched_at="2026-01-01T00:00:00+00:00",
        )
        assert json.loads(json.dumps(manifest.to_dict()))["source"] == "s"
