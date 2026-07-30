"""Figures for the Milestone 1 report (Context.md §36 task 8).

The evidence-breakdown chart is a **stacked horizontal bar**, which is the
honest form here rather than a stylistic choice: the baseline's per-dimension
contributions sum exactly to the prioritization score, so the stack total *is*
the bar length. Nothing is normalized away and nothing is hidden.

Palette and mark specs follow the project's data-visualization guidance. The
five categorical hues were validated before use (adjacent-pair CVD ΔE 9.1,
normal-vision ΔE 19.6, both above their floors). Three of them fall below 3:1
contrast against the light surface, which obliges "relief": this chart ships a
legend, direct score labels on every bar, and the report carries the full table
view — identity is never left to color alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: figures are written to disk, never displayed

import matplotlib.pyplot as plt
import polars as pl

from target_prioritization.models.baseline import CONTRIBUTION_PREFIX, SCORE_COLUMN
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import ensure_dir

__all__ = ["DIMENSION_COLORS", "plot_evidence_breakdown"]

log = get_logger(__name__)

# Validated categorical palette, assigned in fixed order — never cycled.
# Order is the scoring order so the legend reads like the formula.
DIMENSION_COLORS: dict[str, str] = {
    "genetics": "#2a78d6",  # blue
    "evidence_diversity": "#eb6834",  # orange
    "functional": "#1baf7a",  # aqua
    "literature": "#eda100",  # yellow
    "druggability": "#e87ba4",  # magenta
}

DIMENSION_LABELS: dict[str, str] = {
    "genetics": "Genetics",
    "evidence_diversity": "Evidence diversity",
    "functional": "Functional",
    "literature": "Literature",
    "druggability": "Druggability",
}

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8880"
GRID = "#e4e3df"

# A 2px surface-coloured gap separates touching stack segments.
_SEGMENT_GAP_PT = 1.5


def plot_evidence_breakdown(
    ranked: pl.DataFrame,
    output_path: Path,
    *,
    top_n: int = 20,
    highlight: dict[str, str] | None = None,
    weights: dict[str, float] | None = None,
    title: str = "Top Parkinson's disease target candidates",
    subtitle: str = "Prioritization score decomposed into its weighted evidence dimensions",
) -> Path:
    """Draw the stacked evidence breakdown for the top *top_n* targets.

    Args:
        ranked: Ranked frame from ``WeightedBaseline.rank`` — needs
            ``gene_symbol``, ``prioritization_score`` and ``contrib__*``.
        output_path: PNG destination.
        top_n: Number of targets to draw.
        highlight: ``{gene_symbol: annotation}`` for established disease genes.
            Marked with a text marker rather than a colour change, so the
            categorical encoding keeps meaning one thing.
        weights: Dimension weights, shown in the legend so the reader can see
            what produced each segment length without leaving the figure.

    Returns:
        *output_path*.
    """
    highlight = highlight or {}
    weights = weights or {}
    contribution_columns = [
        f"{CONTRIBUTION_PREFIX}{d}"
        for d in DIMENSION_COLORS
        if f"{CONTRIBUTION_PREFIX}{d}" in ranked.columns
    ]
    if not contribution_columns:
        raise KeyError(
            f"No contribution columns in the ranked frame. "
            f"Expected {[f'{CONTRIBUTION_PREFIX}{d}' for d in DIMENSION_COLORS]}"
        )

    top = ranked.head(top_n)
    symbols = [s or "(unnamed)" for s in top.get_column("gene_symbol").to_list()]
    scores = top.get_column(SCORE_COLUMN).to_list()
    ranks = top.get_column("rank").to_list()

    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    y = list(range(len(symbols)))[::-1]  # rank 1 at the top
    left = [0.0] * len(symbols)

    for column in contribution_columns:
        dimension = column.removeprefix(CONTRIBUTION_PREFIX)
        values = top.get_column(column).fill_null(0.0).to_list()
        label = DIMENSION_LABELS[dimension]
        if dimension in weights:
            label = f"{label} ({weights[dimension]:.2f})"
        ax.barh(
            y,
            values,
            left=left,
            height=0.62,  # capped: the band's leftover is deliberate air
            color=DIMENSION_COLORS[dimension],
            label=label,
            # The 2px surface gap between touching segments.
            edgecolor=SURFACE,
            linewidth=_SEGMENT_GAP_PT,
            zorder=3,
        )
        left = [current + value for current, value in zip(left, values, strict=True)]

    # Direct score labels — required relief for the sub-3:1 hues, and they save
    # the reader from measuring against the axis.
    for position, total, symbol in zip(y, scores, symbols, strict=True):
        marker = " ●" if symbol in highlight else ""
        ax.text(
            total + 0.008,
            position,
            f"{total:.3f}{marker}",
            va="center",
            ha="left",
            fontsize=9,
            color=INK_SECONDARY,
            zorder=4,
        )

    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{rank:>2}. {symbol}" for rank, symbol in zip(ranks, symbols, strict=True)],
        fontsize=10,
    )
    # get_yticklabels() is annotated as list[str] but returns Text artists.
    tick_labels: list[Any] = list(ax.get_yticklabels())
    for label, symbol in zip(tick_labels, symbols, strict=True):
        # Established genes in primary ink, everything else secondary. Weight,
        # not colour, so it does not collide with the categorical encoding.
        if symbol in highlight:
            label.set_color(INK_PRIMARY)
            label.set_fontweight("bold")
        else:
            label.set_color(INK_SECONDARY)

    ax.set_xlabel("Prioritization score", fontsize=10, color=INK_SECONDARY, labelpad=8)
    ax.set_xlim(0, max(scores) * 1.16)
    ax.tick_params(axis="x", colors=INK_MUTED, labelsize=9)
    ax.tick_params(axis="y", length=0)

    # Recessive grid: hairline, solid, one step off surface, behind the marks.
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    fig.suptitle(title, x=0.012, y=0.985, ha="left", fontsize=15, color=INK_PRIMARY, weight="bold")
    ax.set_title(subtitle, loc="left", fontsize=10, color=INK_SECONDARY, pad=26)

    # Below the axes rather than inside them. In-plot placement only works while
    # the shortest bars stay short: adding the weights to the labels widened the
    # box enough to nearly reach the rank-17-to-20 score labels, and a longer
    # gene name or a flatter score distribution would collide outright.
    legend = ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.09),
        frameon=False,
        fontsize=9,
        ncol=len(contribution_columns),
        columnspacing=1.6,
        handlelength=1.2,
        title="Evidence dimension (weight)",
        title_fontsize=9,
    )
    legend.get_title().set_color(INK_SECONDARY)
    for text in legend.get_texts():
        text.set_color(INK_SECONDARY)

    if highlight:
        fig.text(
            0.012,
            0.005,
            "● established Parkinson's disease gene — a pipeline sanity check, not a label used in scoring",
            fontsize=8.5,
            color=INK_MUTED,
            ha="left",
        )

    fig.tight_layout(rect=(0, 0.05, 1, 0.955))
    ensure_dir(output_path.parent)
    fig.savefig(output_path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

    log.info("wrote_figure", path=str(output_path), targets=len(symbols))
    return output_path
