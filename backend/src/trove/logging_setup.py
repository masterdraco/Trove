from __future__ import annotations

import logging
import sys

import structlog

from trove.config import get_settings
from trove.log_buffer import LogBufferHandler, structlog_capture_processor


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog_capture_processor,
    ]
    if settings.log_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout, force=True)

    # Attach the ring-buffer handler to the root logger exactly once so
    # uvicorn access/error lines are captured too.
    root = logging.getLogger()
    if not any(isinstance(h, LogBufferHandler) for h in root.handlers):
        root.addHandler(LogBufferHandler(level=level))
