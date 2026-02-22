"""Centralized logging configuration for Day1."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Structured JSON log lines — useful for Docker / log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


TEXT_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
TEXT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Configure the root logger from BM_LOG_LEVEL / BM_LOG_FORMAT env vars.

    Safe to call multiple times — reconfigures on each call.
    """
    from day1.config import settings

    level = getattr(logging, settings.log_level.upper(), logging.DEBUG)

    # Pick formatter
    if settings.log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(TEXT_FORMAT, datefmt=TEXT_DATEFMT)

    # Replace existing handlers on the root logger
    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet noisy third-party loggers unless we're at DEBUG
    if level > logging.DEBUG:
        for name in ("aiomysql", "sqlalchemy.engine", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
