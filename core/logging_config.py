"""Logging configuration for SignConnect.

In production (``ENVIRONMENT=production``) every log record is emitted as a
single-line JSON object — easy to ingest with ELK, Datadog, or any structured
log aggregator.

In development the classic human-readable format is used instead.

If ``LOG_FILE`` is set in the environment, records are *also* written to that
path using a ``RotatingFileHandler`` (10 MB per file, 5 backups) so the
container's disk cannot fill up.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a compact JSON line."""

    # Fields promoted to top-level keys for fast querying in log aggregators.
    _STANDARD_FIELDS = frozenset(logging.LogRecord(
        "", 0, "", 0, "", (), None
    ).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        # Attach any extra fields the caller passed via ``extra={}``
        for key, value in record.__dict__.items():
            if key not in self._STANDARD_FIELDS and not key.startswith("_"):
                try:
                    json.dumps(value)  # only include JSON-serialisable extras
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: str = "INFO") -> None:
    """Set up root-logger handlers based on the current environment.

    Call this once, early in ``create_app()``, before any other module emits
    log records.

    Parameters
    ----------
    log_level:
        String level name (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
        ``CRITICAL``).  Defaults to ``INFO``.
    """
    environment = os.getenv("ENVIRONMENT", "development").lower()
    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if configure_logging is called more than once
    # (e.g. during testing when the app factory is invoked repeatedly).
    root.handlers.clear()

    if environment == "production":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

    # ── stdout handler ─────────────────────────────────────────────────────
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # ── optional rotating file handler ─────────────────────────────────────
    log_file = os.getenv("LOG_FILE", "").strip()
    if log_file:
        _add_rotating_file_handler(root, log_file, formatter, level)


def _add_rotating_file_handler(
    logger: logging.Logger,
    path: str,
    formatter: logging.Formatter,
    level: int,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """Attach a ``RotatingFileHandler`` to *logger*, creating parent dirs as needed."""
    import pathlib

    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


# Module-level start time used by /api/health to report uptime.
_START_TIME: float = time.monotonic()


def get_uptime_seconds() -> float:
    """Return the number of seconds since the logging module was first imported."""
    return time.monotonic() - _START_TIME
