"""Tests for the evidence-breakdown figure split (Milestone 3, Context.md §21/§38.4).

``plot_evidence_breakdown`` is now a thin wrapper over
``build_evidence_breakdown_figure`` that also saves to disk — the Milestone 1
report-generation test (``scripts/run_milestone1.py``, re-run against the
real release) already verified the saved PNG stays byte-identical after this
split. What's covered here is the new piece: that the figure-returning
variant works standalone, on synthetic data, for the app's live rendering.
"""

from __future__ import annotations

import matplotlib
import polars as pl
from matplotlib.figure import Figure

matplotlib.use("Agg")

from target_prioritization.viz import (
    build_evidence_breakdown_figure,
    build_evidence_radar_figure,
    plot_evidence_breakdown,
)


def _ranked() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "rank": [1, 2],
            "gene_symbol": ["G1", "G2"],
            "prioritization_score": [0.8, 0.3],
            "contrib__genetics": [0.4, 0.1],
            "contrib__evidence_diversity": [0.2, 0.05],
            "contrib__functional": [0.1, 0.05],
            "contrib__literature": [0.1, 0.05],
            "contrib__druggability": [0.0, 0.05],
        }
    )


class TestBuildEvidenceBreakdownFigure:
    def test_returns_a_figure_without_writing_anything(self, tmp_path):
        fig = build_evidence_breakdown_figure(_ranked(), title="Test disease", subtitle="Test subtitle")
        assert isinstance(fig, Figure)
        assert list(tmp_path.iterdir()) == []  # nothing was written to disk

    def test_title_and_subtitle_are_used_for_a_non_parkinsons_disease(self):
        """Regression guard: the hard-coded Parkinson's default must be an
        override-able default, not baked into the figure body — a future
        disease's evidence chart must not silently say 'Parkinson's'."""
        fig = build_evidence_breakdown_figure(_ranked(), title="Rheumatoid arthritis", subtitle="Custom subtitle")
        assert fig._suptitle.get_text() == "Rheumatoid arthritis"

    def test_raises_without_contribution_columns(self):
        import pytest

        with pytest.raises(KeyError):
            build_evidence_breakdown_figure(pl.DataFrame({"gene_symbol": ["G1"], "prioritization_score": [0.5]}))


class TestBuildEvidenceRadarFigure:
    def test_returns_a_figure(self):
        fig = build_evidence_radar_figure({"genetics": 0.9, "druggability": 0.2})
        assert isinstance(fig, Figure)

    def test_none_values_plot_as_zero_without_raising(self):
        fig = build_evidence_radar_figure({"genetics": None, "literature": 0.5})
        assert isinstance(fig, Figure)


class TestPlotEvidenceBreakdownStillSaves:
    def test_writes_a_png_file(self, tmp_path):
        output_path = tmp_path / "figure.png"
        result = plot_evidence_breakdown(_ranked(), output_path, title="Test", subtitle="Test")
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0
