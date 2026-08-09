"""Structured logging (Week 19), via structlog wrapping stdlib `logging`.

`configure_logging()` is called once at process startup (`create_app()`;
also safe to call from a script entrypoint). It does NOT require touching
any of the ~15 existing `logger = logging.getLogger(__name__)` call sites
across this project's tools/nodes — structlog's stdlib integration
reconfigures the ROOT logger's formatting, so every existing
`logger.warning(...)` call automatically gets structured (timestamp, level,
logger name, and anything bound via `bind_contextvars` below) without any
of those files knowing structlog exists.

Correlation IDs: `bind_request_context`/`clear_request_context` bind values
(session_id, request_id) into `contextvars`, which `merge_contextvars`
below folds into every log line emitted while they're bound — including
from deep inside a LangGraph node running in a background thread, since
`asyncio.to_thread` (used by `app.py`'s `_drive_graph`) copies the current
`contextvars` context into the worker thread per its own documented
guarantee.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", json_format: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if json_format
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())

    # uvicorn's own loggers otherwise bypass the formatting above (they add
    # their own handler on first use) - route them through the same one.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = [handler]
        uv_logger.propagate = False


def bind_request_context(**kwargs: Any) -> None:
    """Binds correlation-id-style fields (session_id, request_id, ...) onto
    every log line emitted until `clear_request_context()`."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
