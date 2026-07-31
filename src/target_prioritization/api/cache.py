"""In-process caches for the API layer (milestone5_plan.md §4.2).

The services layer has no caching of its own: ``rank_for_disease`` and
``build_evidence_card`` both re-read the processed parquets on every call
unless a frame is injected via their ``features=``/``app_data=`` parameters
— seams that exist for tests, and reused here for the same purpose.
Streamlit's ``@st.cache_data`` (``app/common.py``, removed with the rest of
``app/`` in Phase 7) did this same job with no FastAPI equivalent; this
module is that equivalent, kept at the API layer so nothing in
``services/`` changes.

``lru_cache(maxsize=1)`` on a zero-argument function is the standard
"compute once, keep forever" pattern — equivalent to a module-level global
set lazily, but warmed explicitly at startup (``api/main.py``'s
``lifespan``) rather than on the first request.
"""

from __future__ import annotations

from functools import lru_cache

import polars as pl

from target_prioritization.services.target_ranking import APP_DATA_PATH, FEATURES_PATH

__all__ = ["cached_app_data", "cached_features"]


@lru_cache(maxsize=1)
def cached_features() -> pl.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"{FEATURES_PATH} not found. Run scripts/train_model.py first.")
    return pl.read_parquet(FEATURES_PATH)


@lru_cache(maxsize=1)
def cached_app_data() -> pl.DataFrame:
    if not APP_DATA_PATH.exists():
        raise FileNotFoundError(f"{APP_DATA_PATH} not found. Run scripts/build_app_data.py first.")
    return pl.read_parquet(APP_DATA_PATH)
