# Multi-stage build (milestone5_plan.md §2.2, §4.5): a Next.js static
# export served by FastAPI on one port, one origin, no CORS in production.
#
# Requires artifacts already committed to the repo, not a fresh pipeline
# run — `data/processed/*.parquet`, `models/trained/xgboost_baseline.json`
# and `models/trained/folds/*.json` are explicitly un-ignored in
# .gitignore and confirmed via `git ls-files` to be tracked
# (milestone5_plan.md §4.5), so this builds from a clean checkout.

# ---------------------------------------------------------------------
# Stage 1: Next.js static export
# ---------------------------------------------------------------------
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# frontend/src/lib/api-types.ts is committed (generated from the backend's
# OpenAPI schema — `make types`), so this stage never needs a running
# backend. BUILD_STATIC_EXPORT switches next.config.ts's `output` to
# "export" and drops the dev-only rewrites (milestone5_plan.md §4.5).
ENV BUILD_STATIC_EXPORT=1
RUN npm run build

# ---------------------------------------------------------------------
# Stage 2: Python runtime + the static export
# ---------------------------------------------------------------------
FROM python:3.11-slim AS runtime
WORKDIR /app

# uv (pinned image, matches this project's lockfile-driven installs —
# Makefile's `setup`/`freeze` targets both assume uv) reconstructs the
# exact environment `uv.lock` records, deterministically.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/

# Split into two `uv sync` layers, dependencies before source, so an
# application-code change doesn't invalidate the (slow: xgboost, shap,
# numba, lightgbm) dependency-install layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# README.md and LICENSE are read by setuptools as static project metadata
# (pyproject.toml's `readme`/`license` keys) — the second `uv sync` below
# builds and installs the local project itself, so both must be present.
COPY README.md LICENSE ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY data/processed/ ./data/processed/
COPY models/trained/ ./models/trained/
RUN uv sync --frozen --no-dev

COPY --from=frontend-builder /app/frontend/out ./frontend/out

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000

# The lifespan handler (api/main.py) warms both parquets and every fold
# model at startup (milestone5_plan.md §4.2) — measured at Phase 1 against
# real data, so start-period covers it with margin. No curl in the slim
# image; urllib avoids adding one just for this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "target_prioritization.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
