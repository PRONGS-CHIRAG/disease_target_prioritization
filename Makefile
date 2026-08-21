.PHONY: help setup download verify validate resolve test lint typecheck check api clean freeze \
	dev frontend-install frontend-build frontend-test frontend-test-e2e types docker-build docker-run

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the venv and install the package with dev extras
	uv venv --python 3.11
	uv pip install -e ".[dev]"

download:  ## Fetch the core datasets (~3 GB)
	uv run python scripts/download_data.py --profile core

dry-run:  ## Show what would be downloaded, write nothing
	uv run python scripts/download_data.py --profile core --dry-run

verify:  ## Re-check downloaded files against local and upstream checksums
	uv run python scripts/download_data.py --verify

resolve:  ## Resolve disease names to Open Targets IDs
	uv run python scripts/resolve_diseases.py

evidence-detail:  ## Rebuild the browsable evidence-detail artifacts (Context.md §21)
	uv run python scripts/build_evidence_detail.py

validate:  ## Check every source parses and every identifier join connects
	uv run python scripts/validate_data.py

test:  ## Run the test suite
	uv run pytest -q

lint:  ## Lint and format-check
	uv run ruff check .

typecheck:  ## Type-check the package
	uv run mypy src

check: lint typecheck test  ## Everything CI would run

api:  ## Launch the FastAPI server alone (:8000)
	uv run uvicorn target_prioritization.api.main:app --reload

dev:  ## Run FastAPI (:8000) and the Next.js dev server (:3000) together (milestone5_plan.md §4.5)
	@trap 'kill 0' EXIT; \
	uv run uvicorn target_prioritization.api.main:app --reload --port 8000 & \
	(cd frontend && npm run dev) & \
	wait

frontend-install:  ## Install frontend/ dependencies
	cd frontend && npm install

frontend-build:  ## Build the Next.js static export (frontend/out) — what the Dockerfile copies
	cd frontend && BUILD_STATIC_EXPORT=1 npm run build

frontend-test:  ## Run frontend unit tests (Vitest)
	cd frontend && npm test

frontend-test-e2e:  ## Run the Playwright smoke suite (needs `make api` running separately)
	cd frontend && npm run test:e2e

types:  ## Regenerate frontend/src/lib/api-types.ts from the current OpenAPI schema
	uv run python -c "import json; from target_prioritization.api.main import app; print(json.dumps(app.openapi()))" > frontend/openapi.json
	cd frontend && npx openapi-typescript openapi.json -o src/lib/api-types.ts
	rm frontend/openapi.json

docker-build:  ## Build the single-container image (needs data/processed/ and models/trained/ already built)
	docker build -t disease-target-prioritization .

docker-run:  ## Run the built image, serving the UI and API on :8000
	docker run --rm -p 8000:8000 disease-target-prioritization

freeze:  ## Regenerate requirements.txt from pyproject.toml
	uv pip compile pyproject.toml -o requirements.txt

clean:  ## Remove caches (leaves data/ alone)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache frontend/.next frontend/out
