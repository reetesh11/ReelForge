"""Structured JSON logging: one object per line with ts, level and event."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import TextIO

import structlog


def configure_logging(
    *, stream: TextIO | None = None, log_file: Path | None = None, level: str = "INFO"
) -> None:
    numeric = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    out = stream if stream is not None else sys.stderr
    file_handle: TextIO | None = None
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        file_handle = handler.stream  # type: ignore[assignment]
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=_TeeLoggerFactory(out, file_handle),
        cache_logger_on_first_use=False,
    )


class _TeeLogger:
    def __init__(self, *files: TextIO | None) -> None:
        self._files = [f for f in files if f is not None]

    def msg(self, message: str) -> None:
        for f in self._files:
            try:
                f.write(message + "\n")
                f.flush()
            except (ValueError, OSError):
                continue

    log = debug = info = warn = warning = error = critical = exception = fatal = msg


class _TeeLoggerFactory:
    def __init__(self, *files: TextIO | None) -> None:
        self._files = files

    def __call__(self, *args: object) -> _TeeLogger:
        return _TeeLogger(*self._files)
