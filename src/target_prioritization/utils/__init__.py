"""Shared utilities: paths, structured logging, provenance, validation."""

from target_prioritization.utils.logging import configure_logging, get_logger
from target_prioritization.utils.paths import PROJECT_ROOT, ensure_dir

__all__ = ["PROJECT_ROOT", "configure_logging", "ensure_dir", "get_logger"]
