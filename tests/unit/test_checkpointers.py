"""Checkpointer factory tests. `build_postgres_checkpointer` (Week 18) is
gated on a real reachable Postgres, same rationale/skip pattern as
test_sessions_postgres.py.
"""

from __future__ import annotations

import gc
import os

import psycopg
import pytest

from travel_agent.agents.graph import build_postgres_checkpointer

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/postgres"
)


@pytest.fixture(scope="module")
def _postgres_available():
    try:
        psycopg.connect(TEST_DATABASE_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip(f"no Postgres reachable at {TEST_DATABASE_URL}")


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


def _checkpoint() -> dict:
    return {
        "v": 1,
        "ts": "2026-01-01T00:00:00+00:00",
        "id": "a",
        "channel_values": {},
        "channel_versions": {},
        "versions_seen": {},
    }


def test_build_postgres_checkpointer_put_and_get_round_trips(_postgres_available):
    checkpointer = build_postgres_checkpointer(TEST_DATABASE_URL)
    config = _config("test-thread-round-trip")
    checkpointer.put(config, _checkpoint(), {"source": "input", "step": 1, "writes": {}}, {})
    assert checkpointer.get(config) is not None


def test_build_postgres_checkpointer_survives_garbage_collection(_postgres_available):
    # Regression test for a real bug found live-testing this: from_conn_string
    # is a @contextmanager generator (`with Connection.connect(...) as conn:
    # yield cls(conn)`). Entering it manually without keeping the context
    # manager object itself referenced lets Python's GC finalize the
    # generator once the temporary goes out of scope, which throws
    # GeneratorExit at the yield point and runs the inner `with` block's
    # __exit__ - silently closing the connection. First symptom was
    # `psycopg.OperationalError: the connection is closed` on first real
    # use, not at construction time, which is exactly why this needs an
    # explicit round-trip-after-gc.collect() test rather than just
    # asserting the checkpointer object was constructed.
    checkpointer = build_postgres_checkpointer(TEST_DATABASE_URL)
    gc.collect()
    config = _config("test-thread-gc-safety")
    checkpointer.put(config, _checkpoint(), {"source": "input", "step": 1, "writes": {}}, {})
    gc.collect()
    assert checkpointer.get(config) is not None
