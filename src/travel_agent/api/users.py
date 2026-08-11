"""UserStore — real user accounts.

Same dual-backend pattern as `sessions.py` (SQLite by default, PostgreSQL
whenever `DATABASE_URL` is set — see `build_user_store`) and the same
"one store, one file/table, one purpose" convention already used throughout
this project (Cache/Redis, SessionStore/sessions.sqlite, checkpointer/
checkpoints.sqlite) — kept separate from `SessionStore` itself rather than
folded into it, even though sessions now reference a `user_id`.

Passwords are never stored or logged in plaintext: `password_hash` is a
bcrypt hash, produced by `api.auth.hash_password` before it ever reaches
this module.

`google_id` (added alongside Google OAuth sign-in, see `api/app.py`'s
`/auth/google/login` + `/callback`) is nullable and migrated onto
pre-existing tables additively (same `_add_column_sqlite` pattern
`sessions.py`'s `share_token` uses) — accounts created before this feature
existed simply have no linked Google identity, which is correct. A user who
signs in with Google gets a real, unusable-by-anyone random `password_hash`
(see `create`'s docstring) rather than a nullable column, so the existing
`password_hash TEXT NOT NULL` constraint never needs to change at all.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def _add_column_sqlite(conn: sqlite3.Connection, column: str, coltype: str) -> None:
    # Same idea as sessions.py's helper of the same name: `CREATE TABLE IF
    # NOT EXISTS` only helps a brand-new database, and SQLite has no `ADD
    # COLUMN IF NOT EXISTS` — idempotent by catching the "already has this
    # column" error rather than checking first (this store is already
    # single-connection/locked, so there's no real TOCTOU race either way).
    try:
        conn.execute(f"ALTER TABLE users ADD COLUMN {column} {coltype}")
        conn.commit()
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


@dataclass
class UserRecord:
    user_id: str
    email: str
    password_hash: str
    created_at: str
    google_id: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


class UserStore:
    def __init__(self, db_path: str = "users.sqlite") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            _add_column_sqlite(self._conn, "google_id", "TEXT")

    def create(
        self, user_id: str, email: str, password_hash: str, google_id: str | None = None
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (user_id, email, password_hash, created_at, google_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, email.lower(), password_hash, _now(), google_id),
            )
            self._conn.commit()

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.lower(),)
            ).fetchone()
        return UserRecord(**dict(row)) if row else None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return UserRecord(**dict(row)) if row else None

    def get_by_google_id(self, google_id: str) -> UserRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE google_id = ?", (google_id,)
            ).fetchone()
        return UserRecord(**dict(row)) if row else None

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?", (password_hash, user_id)
            )
            self._conn.commit()

    def link_google_id(self, user_id: str, google_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET google_id = ? WHERE user_id = ?", (google_id, user_id)
            )
            self._conn.commit()


class PostgresUserStore:
    """Same public interface as `UserStore`, used instead of it whenever
    `DATABASE_URL` is set — see `build_user_store`."""

    def __init__(self, database_url: str) -> None:
        self._conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(_POSTGRES_SCHEMA)
            # Postgres, unlike SQLite, supports ADD COLUMN IF NOT EXISTS
            # directly — no try/except migration dance needed here.
            self._conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id TEXT")

    def create(
        self, user_id: str, email: str, password_hash: str, google_id: str | None = None
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (user_id, email, password_hash, created_at, google_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, email.lower(), password_hash, _now(), google_id),
            )

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE email = %s", (email.lower(),)
            ).fetchone()
        return UserRecord(**row) if row else None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE user_id = %s", (user_id,)
            ).fetchone()
        return UserRecord(**row) if row else None

    def get_by_google_id(self, google_id: str) -> UserRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE google_id = %s", (google_id,)
            ).fetchone()
        return UserRecord(**row) if row else None

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET password_hash = %s WHERE user_id = %s", (password_hash, user_id)
            )

    def link_google_id(self, user_id: str, google_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET google_id = %s WHERE user_id = %s", (google_id, user_id)
            )


def build_user_store(database_url: str | None) -> UserStore | PostgresUserStore:
    """Postgres when `DATABASE_URL` is set (Docker Compose), SQLite
    otherwise (plain `make serve`) — same rule `build_session_store` uses."""
    return PostgresUserStore(database_url) if database_url else UserStore()
