"""Week 19 structured logging tests."""

from __future__ import annotations

import logging

import structlog

from travel_agent.observability import logging as obs_logging
from travel_agent.observability.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
)


def test_configure_logging_is_idempotent(monkeypatch):
    monkeypatch.setattr(obs_logging, "_CONFIGURED", False)
    configure_logging()
    handlers_after_first_call = list(logging.getLogger().handlers)

    configure_logging()  # second call must be a no-op, not double-attach handlers

    assert logging.getLogger().handlers == handlers_after_first_call


def test_configure_logging_sets_root_logger_level(monkeypatch):
    monkeypatch.setattr(obs_logging, "_CONFIGURED", False)
    configure_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_bind_request_context_appears_in_bound_contextvars():
    clear_request_context()
    bind_request_context(session_id="abc-123")
    assert structlog.contextvars.get_contextvars()["session_id"] == "abc-123"
    clear_request_context()


def test_clear_request_context_removes_bound_values():
    bind_request_context(session_id="abc-123", request_id="req-1")
    clear_request_context()
    assert structlog.contextvars.get_contextvars() == {}


def test_bind_request_context_merges_multiple_calls():
    clear_request_context()
    bind_request_context(request_id="req-1")
    bind_request_context(session_id="sess-1")
    bound = structlog.contextvars.get_contextvars()
    assert bound["request_id"] == "req-1"
    assert bound["session_id"] == "sess-1"
    clear_request_context()
