"""Sentry error tracking (Week 19) — optional, same graceful-degradation
pattern as every other external integration in this project: without
SENTRY_DSN configured, `init_sentry()` is a no-op rather than an error.
"""

from __future__ import annotations

import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

logger = logging.getLogger(__name__)


def init_sentry(dsn: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            FastApiIntegration(),
            # Sentry already gets exceptions via its FastAPI/asyncio hooks;
            # this additionally captures any ERROR-and-above log line (e.g.
            # a caught-and-logged tool failure that doesn't raise) as a
            # Sentry event too, matching "automatic exception capture with
            # context" for errors this project deliberately catches rather
            # than lets propagate (every node in nodes.py, by design).
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    logger.info("sentry initialized")
