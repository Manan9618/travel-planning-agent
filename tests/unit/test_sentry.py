"""Week 19 Sentry wiring tests. Real sentry_sdk.init() is mocked throughout
- there's no real Sentry project/DSN for these tests to report to, and the
point being tested is "did we call init with the right args", not Sentry's
own behavior."""

from __future__ import annotations

from unittest.mock import patch

from travel_agent.observability.sentry import init_sentry


def test_init_sentry_is_a_noop_without_a_dsn():
    with patch("travel_agent.observability.sentry.sentry_sdk.init") as mock_init:
        init_sentry("")
    mock_init.assert_not_called()


def test_init_sentry_calls_sentry_sdk_init_with_a_dsn():
    with patch("travel_agent.observability.sentry.sentry_sdk.init") as mock_init:
        init_sentry("https://example@o0.ingest.sentry.io/0")
    mock_init.assert_called_once()
    assert mock_init.call_args.kwargs["dsn"] == "https://example@o0.ingest.sentry.io/0"


def test_init_sentry_disables_default_pii():
    with patch("travel_agent.observability.sentry.sentry_sdk.init") as mock_init:
        init_sentry("https://example@o0.ingest.sentry.io/0")
    assert mock_init.call_args.kwargs["send_default_pii"] is False
