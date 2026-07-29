.PHONY: help setup download verify validate resolve test lint typecheck check app api clean freeze

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

validate:  ## Check every source parses and every identifier join connects
	uv run python scripts/validate_data.py

test:  ## Run the test suite
	uv run pytest -q

lint:  ## Lint and format-check
	uv run ruff check .

typecheck:  ## Type-check the package
	uv run mypy src

check: lint typecheck test  ## Everything CI would run

app:  ## Launch the Streamlit app
	uv run streamlit run app/streamlit_app.py

api:  ## Launch the FastAPI server
	uv run uvicorn target_prioritization.api.main:app --reload

freeze:  ## Regenerate requirements.txt from pyproject.toml
	uv pip compile pyproject.toml -o requirements.txt

clean:  ## Remove caches (leaves data/ alone)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
