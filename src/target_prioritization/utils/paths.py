"""Filesystem layout for the project.

Context.md §34 requires that file paths never be hard-coded. Every module that
touches disk should ask this module where things live rather than building
paths from string literals or relative `../..` walks, which break as soon as
the working directory changes (notebooks are run from `notebooks/`, scripts
from the repo root, tests from anywhere).

The data root can be relocated with ``DTP_DATA_DIR`` — the core Open Targets
pull is ~2.5 GB and may belong on an external drive.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "CONFIG_DIR",
    "DATA_EXTERNAL",
    "DATA_INTERIM",
    "DATA_PROCESSED",
    "DATA_RAW",
    "DATA_ROOT",
    "MODELS_DIR",
    "PROJECT_ROOT",
    "RAW_MANIFEST_LOG",
    "REPORTS_DIR",
    "ensure_dir",
    "find_project_root",
    "raw_dir",
    "relative_to_root",
]

# Files that mark the repository root. `pyproject.toml` is the primary marker;
# `.git` is the fallback for worktrees or partial checkouts.
_ROOT_MARKERS = ("pyproject.toml", ".git")


def find_project_root(start: Path | None = None) -> Path:
    """Walk upward from *start* until a directory containing a root marker.

    Args:
        start: Directory to begin from. Defaults to this file's location, which
            makes resolution independent of the current working directory.

    Returns:
        The repository root.

    Raises:
        RuntimeError: If no marker is found on the way up to the filesystem
            root. Silence here would mean data silently written to the wrong
            place, so this fails loudly.
    """
    if env_root := os.environ.get("DTP_PROJECT_ROOT"):
        return Path(env_root).expanduser().resolve()

    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in _ROOT_MARKERS):
            return candidate

    raise RuntimeError(
        f"Could not locate the project root above {current}. "
        f"Expected to find one of {_ROOT_MARKERS}. "
        "Set DTP_PROJECT_ROOT to override."
    )


def _resolve_data_root(project_root: Path) -> Path:
    """Data root, honouring the ``DTP_DATA_DIR`` override."""
    if env_data := os.environ.get("DTP_DATA_DIR"):
        return Path(env_data).expanduser().resolve()
    return project_root / "data"


PROJECT_ROOT: Path = find_project_root()

CONFIG_DIR: Path = PROJECT_ROOT / "configs"
DOCS_DIR: Path = PROJECT_ROOT / "docs"
MODELS_DIR: Path = PROJECT_ROOT / "models"
NOTEBOOKS_DIR: Path = PROJECT_ROOT / "notebooks"
REPORTS_DIR: Path = PROJECT_ROOT / "reports"

DATA_ROOT: Path = _resolve_data_root(PROJECT_ROOT)

# Context.md §34: keep raw data immutable and separate raw/interim/processed.
#   raw       — exactly as downloaded, never edited in place
#   interim   — decoded, filtered, joined; cheap to regenerate from raw
#   processed — model-ready tables (the feature store)
#   external  — anything hand-curated or not fetched by download_data.py
DATA_RAW: Path = DATA_ROOT / "raw"
DATA_INTERIM: Path = DATA_ROOT / "interim"
DATA_PROCESSED: Path = DATA_ROOT / "processed"
DATA_EXTERNAL: Path = DATA_ROOT / "external"

TRAINED_MODELS: Path = MODELS_DIR / "trained"
MODEL_METADATA: Path = MODELS_DIR / "metadata"

FIGURES_DIR: Path = REPORTS_DIR / "figures"
EVALUATION_DIR: Path = REPORTS_DIR / "evaluation"
MODEL_CARDS_DIR: Path = REPORTS_DIR / "model_cards"

# Append-only provenance log; one JSON object per downloaded file.
RAW_MANIFEST_LOG: Path = DATA_RAW / "_manifest.jsonl"


def ensure_dir(path: Path) -> Path:
    """Create *path* (and parents) if absent and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_dir(source: str, *parts: str) -> Path:
    """Path within ``data/raw`` for a named source.

    Example:
        >>> raw_dir("open_targets", "target").name
        'target'
    """
    return DATA_RAW.joinpath(source, *parts)


def relative_to_root(path: Path) -> str:
    """Render *path* relative to the project root for stable log output.

    Absolute paths differ between machines, which makes logs and manifests
    noisy to diff. Falls back to the absolute path when *path* lies outside
    the repository (e.g. a relocated ``DTP_DATA_DIR``).
    """
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
