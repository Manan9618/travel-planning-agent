import sqlite3
from unittest.mock import patch

import pytest

from travel_agent.api.users import PostgresUserStore, UserStore, build_user_store


def _store() -> UserStore:
    return UserStore(":memory:")


def test_create_and_get_by_id_round_trips():
    store = _store()
    store.create("u1", "traveler@example.com", "hashed-password")
    record = store.get_by_id("u1")
    assert record is not None
    assert record.user_id == "u1"
    assert record.email == "traveler@example.com"
    assert record.password_hash == "hashed-password"


def test_get_by_email_finds_the_same_record():
    store = _store()
    store.create("u1", "traveler@example.com", "hashed-password")
    record = store.get_by_email("traveler@example.com")
    assert record is not None
    assert record.user_id == "u1"


def test_email_lookup_is_case_insensitive():
    store = _store()
    store.create("u1", "Traveler@Example.com", "hashed-password")
    assert store.get_by_email("traveler@example.com") is not None
    assert store.get_by_email("TRAVELER@EXAMPLE.COM") is not None


def test_email_is_stored_lowercased():
    store = _store()
    store.create("u1", "Traveler@Example.COM", "hashed-password")
    assert store.get_by_id("u1").email == "traveler@example.com"


def test_get_by_id_unknown_user_returns_none():
    assert _store().get_by_id("nope") is None


def test_update_password_changes_the_hash():
    store = _store()
    store.create("u1", "traveler@example.com", "old-hash")
    store.update_password("u1", "new-hash")
    assert store.get_by_id("u1").password_hash == "new-hash"


def test_update_password_does_not_affect_other_fields():
    store = _store()
    store.create("u1", "traveler@example.com", "old-hash")
    store.update_password("u1", "new-hash")
    record = store.get_by_id("u1")
    assert record.email == "traveler@example.com"


def test_get_by_email_unknown_user_returns_none():
    assert _store().get_by_email("nobody@example.com") is None


def test_duplicate_email_raises():
    store = _store()
    store.create("u1", "traveler@example.com", "hash1")
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE constraint on email
        store.create("u2", "traveler@example.com", "hash2")


# --- google_id (Google OAuth sign-in) --------------------------------------


def test_create_with_google_id_round_trips():
    store = _store()
    store.create("u1", "traveler@example.com", "unusable-hash", google_id="google-123")
    record = store.get_by_id("u1")
    assert record.google_id == "google-123"


def test_google_id_defaults_to_none_for_a_normal_account():
    store = _store()
    store.create("u1", "traveler@example.com", "hashed-password")
    assert store.get_by_id("u1").google_id is None


def test_get_by_google_id_finds_the_record():
    store = _store()
    store.create("u1", "traveler@example.com", "unusable-hash", google_id="google-123")
    record = store.get_by_google_id("google-123")
    assert record is not None
    assert record.user_id == "u1"


def test_get_by_google_id_unknown_returns_none():
    assert _store().get_by_google_id("nope") is None


def test_link_google_id_sets_it_on_an_existing_account():
    store = _store()
    store.create("u1", "traveler@example.com", "hashed-password")
    store.link_google_id("u1", "google-456")
    record = store.get_by_id("u1")
    assert record.google_id == "google-456"
    assert record.password_hash == "hashed-password"  # untouched


def test_link_google_id_makes_the_account_findable_by_google_id():
    store = _store()
    store.create("u1", "traveler@example.com", "hashed-password")
    store.link_google_id("u1", "google-456")
    assert store.get_by_google_id("google-456").user_id == "u1"


# --- build_user_store (Postgres when DATABASE_URL is set) -----------------


def test_build_user_store_returns_sqlite_store_without_database_url():
    assert isinstance(build_user_store(""), UserStore)


def test_build_user_store_returns_postgres_store_with_database_url():
    with patch("travel_agent.api.users.psycopg.connect") as mock_connect:
        store = build_user_store("postgresql://user@host/db")
    assert isinstance(store, PostgresUserStore)
    mock_connect.assert_called_once()
