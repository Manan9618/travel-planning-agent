from unittest.mock import patch

from travel_agent.api.sessions import PostgresSessionStore, SessionStore, build_session_store


def _store() -> SessionStore:
    return SessionStore(":memory:")


def test_create_and_get_round_trips():
    store = _store()
    store.create("s1", "5 days in Paris")
    record = store.get("s1")
    assert record is not None
    assert record.session_id == "s1"
    assert record.raw_text == "5 days in Paris"
    assert record.status == "running"
    assert record.parent_session_id is None


def test_get_unknown_session_returns_none():
    assert _store().get("nope") is None


def test_create_with_parent_session_id():
    store = _store()
    store.create("child", "make it cheaper", parent_session_id="parent")
    assert store.get("child").parent_session_id == "parent"


def test_update_status_changes_status_and_updated_at():
    store = _store()
    store.create("s1", "trip")
    before = store.get("s1")
    store.update_status("s1", "completed")
    after = store.get("s1")
    assert after.status == "completed"
    assert after.updated_at >= before.updated_at


def test_append_and_get_events_preserves_order():
    store = _store()
    store.create("s1", "trip")
    store.append_event("s1", "step_completed", {"step": "parse_preferences"})
    store.append_event("s1", "step_completed", {"step": "search_flights"})
    events = store.get_events("s1")
    assert [e.payload["step"] for e in events] == ["parse_preferences", "search_flights"]


def test_get_events_after_id_only_returns_newer_events():
    store = _store()
    store.create("s1", "trip")
    store.append_event("s1", "step_completed", {"step": "a"})
    first_id = store.get_events("s1")[0].id
    store.append_event("s1", "step_completed", {"step": "b"})
    newer = store.get_events("s1", after_id=first_id)
    assert [e.payload["step"] for e in newer] == ["b"]


def test_events_are_scoped_per_session():
    store = _store()
    store.create("s1", "trip 1")
    store.create("s2", "trip 2")
    store.append_event("s1", "step_completed", {"step": "a"})
    store.append_event("s2", "step_completed", {"step": "b"})
    assert [e.payload["step"] for e in store.get_events("s1")] == ["a"]
    assert [e.payload["step"] for e in store.get_events("s2")] == ["b"]


def test_event_payload_round_trips_nested_structures():
    store = _store()
    store.create("s1", "trip")
    payload = {"node": "build_itinerary", "output": {"itinerary": {"days": [1, 2, 3]}}}
    store.append_event("s1", "node_update", payload)
    assert store.get_events("s1")[0].payload == payload


# --- build_session_store (Week 18: Postgres when DATABASE_URL is set) -----


def test_build_session_store_returns_sqlite_store_without_database_url():
    assert isinstance(build_session_store(""), SessionStore)


def test_build_session_store_returns_postgres_store_with_database_url():
    with patch("travel_agent.api.sessions.psycopg.connect") as mock_connect:
        store = build_session_store("postgresql://user@host/db")
    assert isinstance(store, PostgresSessionStore)
    mock_connect.assert_called_once()
