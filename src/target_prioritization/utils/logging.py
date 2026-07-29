"""Structured logging (Context.md §34).

Pipeline steps emit key/value events rather than formatted prose, so that a run
can be audited afterwards: which dataset, how many rows in, how many rows out,
how many identifiers failed to map. Context.md §34 also demands that failed
mappings are never silently discarded — :func:`log_dropped` is the helper that
makes reporting them the path of least resistance.

Console output is human-readable by default; set ``DTP_LOG_JSON=true`` for
machine-parseable output when running in CI or redirecting to a file.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

__all__ = ["configure_logging", "get_logger", "log_dropped"]

_configured = False


def configure_logging(
    level: str | None = None,
    *,
    json_output: bool | None = None,
    force: bool = False,
) -> None:
    """Configure structlog + stdlib logging. Idempotent unless *force*.

    Args:
        level: Log level name. Defaults to ``DTP_LOG_LEVEL`` or ``INFO``.
        json_output: Emit JSON lines instead of a console renderer. Defaults to
            ``DTP_LOG_JSON``.
        force: Reconfigure even if already configured.
    """
    global _configured
    if _configured and not force:
        return

    level = (level or os.environ.get("DTP_LOG_LEVEL") or "INFO").upper()
    if json_output is None:
        json_output = os.environ.get("DTP_LOG_JSON", "").lower() in {"1", "true", "yes"}

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level, logging.INFO),
        force=True,
    )

    # httpx logs every request at INFO, which buries our own events under ~50
    # lines of transport chatter during a download run.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, configuring logging on first use."""
    configure_logging()
    # structlog.get_logger is typed as returning Any; the configured
    # logger_factory guarantees a stdlib BoundLogger.
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def log_dropped(
    logger: structlog.stdlib.BoundLogger,
    *,
    stage: str,
    reason: str,
    count: int,
    total: int | None = None,
    examples: list[Any] | None = None,
    max_examples: int = 5,
) -> None:
    """Report records dropped by a pipeline stage.

    Context.md §34 forbids silently discarding failed mappings or missing
    values, and §32.6 requires unresolved identifiers to be reported. Call this
    at every point where rows are filtered out, even when the count is zero —
    a logged zero is evidence the check ran.

    Args:
        stage: Pipeline stage name, e.g. ``"gtex_ensembl_join"``.
        reason: Why the records were dropped.
        count: Number of records dropped.
        total: Number of records considered, used to report a rate.
        examples: Sample of dropped values, truncated to *max_examples*.
    """
    payload: dict[str, Any] = {"stage": stage, "reason": reason, "dropped": count}
    if total is not None:
        payload["total"] = total
        payload["dropped_pct"] = round(100.0 * count / total, 3) if total else 0.0
    if examples:
        payload["examples"] = [str(e) for e in examples[:max_examples]]

    # Zero drops are still worth recording, but at a quieter level.
    log = logger.info if count else logger.debug
    log("records_dropped", **payload)
