"""PostgresSessionStore tests (Week 18) against a real Postgres instance.

Unlike SessionStore's tests (which get true per-test isolation for free via
SQLite's `:memory:`), these share one physical `sessions`/`events` table
against whatever Postgres `TEST_DATABASE_URL` points at, so every test uses
a fresh random session_id and only asserts on rows it created itself, never
on the full row set.

Skipped automatically when no Postgres is reachable, so `make test` stays
green on a machine without one installed (the same offline-by-default
philosophy as the rest of this project) - GitHub Actions CI provides a real
Postgres service container so these genuinely run there. To run locally:
    brew install postgresql@16 && brew services start postgresql@16
    createdb travel_agent_test
    TEST_DATABASE_URL=postgresql://localhost/travel_agent_test \
        pytest tests/unit/test_sessions_postgres.py
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from travel_agent.api.sessions import PostgresSessionStore

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/postgres"
)


@pytest.fixture(scope="module")
def _postgres_available():
    try:
        psycopg.connect(TEST_DATABASE_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip(f"no Postgres reachable at {TEST_DATABASE_URL}")


@pytest.fixture
def store(_postgres_available):
    return PostgresSessionStore(TEST_DATABASE_URL)


def _sid() -> str:
    return f"test-{uuid.uuid4()}"


def test_create_and_get_round_trips(store):
    sid = _sid()
    store.create(sid, "5 days in Paris")
    record = store.get(sid)
    assert record is not None
    assert record.session_id == sid
    assert record.raw_text == "5 days in Paris"
    assert record.status == "running"
    assert record.parent_session_id is None


def test_get_unknown_session_returns_none(store):
    assert store.get(_sid()) is None


def test_create_with_parent_session_id(store):
    child, parent = _sid(), _sid()
    store.create(child, "make it cheaper", parent_session_id=parent)
    assert store.get(child).parent_session_id == parent


def test_update_status_changes_status_and_updated_at(store):
    sid = _sid()
    store.create(sid, "trip")
    before = store.get(sid)
    store.update_status(sid, "completed")
    after = store.get(sid)
    assert after.status == "completed"
    assert after.updated_at >= before.updated_at


def test_append_and_get_events_preserves_order(store):
    sid = _sid()
    store.create(sid, "trip")
    store.append_event(sid, "step_completed", {"step": "parse_preferences"})
    store.append_event(sid, "step_completed", {"step": "search_flights"})
    events = store.get_events(sid)
    assert [e.payload["step"] for e in events] == ["parse_preferences", "search_flights"]


def test_get_events_after_id_only_returns_newer_events(store):
    sid = _sid()
    store.create(sid, "trip")
    store.append_event(sid, "step_completed", {"step": "a"})
    first_id = store.get_events(sid)[0].id
    store.append_event(sid, "step_completed", {"step": "b"})
    newer = store.get_events(sid, after_id=first_id)
    assert [e.payload["step"] for e in newer] == ["b"]


def test_events_are_scoped_per_session(store):
    s1, s2 = _sid(), _sid()
    store.create(s1, "trip 1")
    store.create(s2, "trip 2")
    store.append_event(s1, "step_completed", {"step": "a"})
    store.append_event(s2, "step_completed", {"step": "b"})
    assert [e.payload["step"] for e in store.get_events(s1)] == ["a"]
    assert [e.payload["step"] for e in store.get_events(s2)] == ["b"]


def test_event_payload_round_trips_nested_structures(store):
    sid = _sid()
    store.create(sid, "trip")
    payload = {"node": "build_itinerary", "output": {"itinerary": {"days": [1, 2, 3]}}}
    store.append_event(sid, "node_update", payload)
    assert store.get_events(sid)[0].payload == payload


def test_list_ids_includes_created_session(store):
    sid = _sid()
    store.create(sid, "trip")
    assert sid in store.list_ids()
