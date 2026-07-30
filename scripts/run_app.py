#!/usr/bin/env python
"""Launch the Streamlit app (Context.md §21, §28 Step 11).

Verifies the artifacts the app reads from disk exist before launching —
missing them produces a confusing in-app error ("file not found" deep in a
service call) instead of a clear, actionable message naming the script to
run first.

Also sets ``ARROW_DEFAULT_MEMORY_POOL=system`` before launching. Without
it, this environment's pyarrow (25.0.0) segfaults (SIGSEGV, inside its
mimalloc allocator's per-thread heap init) the first time a Streamlit
session reruns the script in a new thread — reproduced via Playwright:
switching the selected disease reliably crashed the server until this was
set. Streamlit runs each session in its own thread, and pyarrow's mimalloc
allocator is what's implicated in the crash traces (macOS crash reporter,
``~/Library/Logs/DiagnosticReports/python3.11-*.ips``); the ``system``
memory pool avoids mimalloc entirely. Must be set in the environment
BEFORE the ``streamlit`` subprocess starts — setting it after pyarrow has
already initialized its allocator would not help, which is why this script
sets it and then launches ``streamlit`` as a fresh subprocess rather than
importing and calling Streamlit's runtime in-process.

Usage:
    python scripts/run_app.py
    make app
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from target_prioritization.milestone2 import FOLD_MODELS_DIRNAME, fold_model_filename
from target_prioritization.utils.paths import DATA_PROCESSED, PROJECT_ROOT, TRAINED_MODELS

REQUIRED_FILES: list[tuple[Path, str]] = [
    (DATA_PROCESSED / "disease_target_features.parquet", "scripts/train_model.py"),
    (DATA_PROCESSED / "labels.parquet", "scripts/train_model.py"),
    (DATA_PROCESSED / "app_scores.parquet", "scripts/build_app_data.py (after scripts/train_model.py)"),
]


def _missing_fold_models() -> list[str]:
    from target_prioritization.config import load_diseases

    missing = []
    for disease in load_diseases().resolved:
        path = TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(disease.key)
        if not path.exists():
            missing.append(disease.key)
    return missing


def main() -> int:
    problems: list[str] = []
    for path, fix in REQUIRED_FILES:
        if not path.exists():
            problems.append(f"  - {path} not found. Run: {fix}")

    if missing_folds := _missing_fold_models():
        problems.append(
            f"  - {len(missing_folds)} held-out fold model(s) missing under "
            f"models/trained/{FOLD_MODELS_DIRNAME}/ ({', '.join(missing_folds[:3])}"
            f"{', ...' if len(missing_folds) > 3 else ''}). Run: scripts/train_model.py"
        )

    if problems:
        print("Cannot launch the app — required artifacts are missing:\n")
        print("\n".join(problems))
        return 1

    env = os.environ.copy()
    env["ARROW_DEFAULT_MEMORY_POOL"] = "system"

    # `python -m streamlit`, not a bare `streamlit` on PATH — this must run
    # with the SAME interpreter/environment scripts/run_app.py itself is
    # running under, whatever invoked it (uv run, an activated venv, or a
    # bare venv python), rather than depending on PATH resolution.
    return subprocess.call(
        [sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "app" / "streamlit_app.py"), *sys.argv[1:]],
        env=env,
    )


if __name__ == "__main__":
    sys.exit(main())
