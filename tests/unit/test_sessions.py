import sqlite3
import tempfile
from pathlib import Path
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


def test_list_by_user_returns_only_that_users_top_level_sessions():
    store = _store()
    store.create("mine", "5 days in Paris", user_id="u1")
    store.create("theirs", "3 days in Rome", user_id="u2")
    records = store.list_by_user("u1")
    assert [r.session_id for r in records] == ["mine"]


def test_list_by_user_excludes_refinement_sessions():
    store = _store()
    store.create("root", "5 days in Paris", user_id="u1")
    store.create("refinement", "add a museum", parent_session_id="root", user_id="u1")
    records = store.list_by_user("u1")
    assert [r.session_id for r in records] == ["root"]


def test_list_by_user_orders_most_recent_first():
    store = _store()
    store.create("first", "trip one", user_id="u1")
    store.create("second", "trip two", user_id="u1")
    records = store.list_by_user("u1")
    assert [r.session_id for r in records] == ["second", "first"]


def test_list_by_user_returns_empty_for_a_user_with_no_sessions():
    assert _store().list_by_user("nobody") == []


def test_delete_removes_the_session():
    store = _store()
    store.create("s1", "5 days in Paris")
    store.delete("s1")
    assert store.get("s1") is None


def test_delete_removes_its_events():
    store = _store()
    store.create("s1", "5 days in Paris")
    store.append_event("s1", "step_completed", {"step": "search_flights"})
    store.delete("s1")
    assert store.get_events("s1") == []


def test_delete_does_not_affect_other_sessions():
    store = _store()
    store.create("keep", "5 days in Paris")
    store.create("gone", "3 days in Rome")
    store.delete("gone")
    assert store.get("keep") is not None


def test_delete_of_an_unknown_session_does_not_raise():
    _store().delete("nope")  # no-op, not an error


def test_new_session_has_no_share_token():
    store = _store()
    store.create("s1", "5 days in Paris")
    assert store.get("s1").share_token is None


def test_set_share_token_makes_the_session_findable_by_token():
    store = _store()
    store.create("s1", "5 days in Paris")
    store.set_share_token("s1", "tok-abc")
    assert store.get("s1").share_token == "tok-abc"
    assert store.get_by_share_token("tok-abc").session_id == "s1"


def test_get_by_share_token_unknown_token_returns_none():
    assert _store().get_by_share_token("nope") is None


def test_clear_share_token_makes_it_no_longer_findable():
    store = _store()
    store.create("s1", "5 days in Paris")
    store.set_share_token("s1", "tok-abc")
    store.clear_share_token("s1")
    assert store.get("s1").share_token is None
    assert store.get_by_share_token("tok-abc") is None


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


# --- user_id (real user accounts) ----------------------------------------


def test_create_with_user_id_round_trips():
    store = _store()
    store.create("s1", "5 days in Paris", user_id="user-abc")
    assert store.get("s1").user_id == "user-abc"


def test_create_without_user_id_defaults_to_none():
    store = _store()
    store.create("s1", "5 days in Paris")
    assert store.get("s1").user_id is None


def test_user_id_column_is_added_additively_to_a_pre_existing_database():
    # Real scenario this guards against: a sessions.sqlite file that existed
    # before real user accounts did, with a `sessions` table and no
    # `user_id` column at all. `CREATE TABLE IF NOT EXISTS` alone can't add
    # a column to an existing table - this asserts the additive migration
    # (`_add_user_id_column_sqlite`) actually runs and the store stays usable.
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "legacy_sessions.sqlite")
        legacy_conn = sqlite3.connect(db_path)
        legacy_conn.execute(
            "CREATE TABLE sessions ("
            "session_id TEXT PRIMARY KEY, status TEXT NOT NULL, raw_text TEXT NOT NULL, "
            "parent_session_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        legacy_conn.execute(
            "INSERT INTO sessions VALUES ('old-session', 'completed', 'trip', NULL, 'x', 'x')"
        )
        legacy_conn.commit()
        legacy_conn.close()

        store = SessionStore(db_path)  # must not raise despite the missing column
        assert store.get("old-session").user_id is None
        store.create("new-session", "another trip", user_id="user-abc")
        assert store.get("new-session").user_id == "user-abc"


def test_user_id_migration_is_idempotent_across_repeated_store_construction():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "sessions.sqlite")
        SessionStore(db_path)
        SessionStore(db_path)  # must not raise "duplicate column name"


def test_share_token_column_is_added_additively_to_a_pre_existing_database():
    # Same scenario as user_id's own migration test, but for a database that
    # predates public share links specifically (even if it already has
    # user_id, from before share_token existed).
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "legacy_sessions.sqlite")
        legacy_conn = sqlite3.connect(db_path)
        legacy_conn.execute(
            "CREATE TABLE sessions ("
            "session_id TEXT PRIMARY KEY, status TEXT NOT NULL, raw_text TEXT NOT NULL, "
            "parent_session_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "user_id TEXT)"
        )
        legacy_conn.execute(
            "INSERT INTO sessions VALUES "
            "('old-session', 'completed', 'trip', NULL, 'x', 'x', 'user-abc')"
        )
        legacy_conn.commit()
        legacy_conn.close()

        store = SessionStore(db_path)  # must not raise despite the missing column
        assert store.get("old-session").share_token is None
        store.set_share_token("old-session", "tok-abc")
        assert store.get("old-session").share_token == "tok-abc"


# --- build_session_store (Week 18: Postgres when DATABASE_URL is set) -----


def test_build_session_store_returns_sqlite_store_without_database_url():
    assert isinstance(build_session_store(""), SessionStore)


def test_build_session_store_returns_postgres_store_with_database_url():
    with patch("travel_agent.api.sessions.psycopg.connect") as mock_connect:
        store = build_session_store("postgresql://user@host/db")
    assert isinstance(store, PostgresSessionStore)
    mock_connect.assert_called_once()
