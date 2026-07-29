#!/usr/bin/env python
"""Download the datasets declared in configs/data_sources.yaml.

Thin wrapper around target_prioritization.cli — the logic lives in the package
so it stays importable and testable (Context.md §34).

Examples:
    python scripts/download_data.py --profile core --dry-run
    python scripts/download_data.py --profile core
    python scripts/download_data.py --only string,reactome,gtex
    python scripts/download_data.py --verify
"""

from target_prioritization.cli import download_main

if __name__ == "__main__":
    download_main()
