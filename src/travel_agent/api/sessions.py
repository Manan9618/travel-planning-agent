"""SessionStore — Week 15 deliverable: lightweight session metadata and a
replayable event log, backed by SQLite.

This is deliberately separate from the full planning STATE, which
LangGraph's own checkpointer (Week 4's `build_sqlite_checkpointer`) already
persists per `thread_id` (== `session_id` throughout the API layer). This
store only tracks what the checkpointer doesn't: session status
(running/awaiting_review/completed/failed), when it was created, the
original request text, and a rolling log of streamed events — so a
WebSocket client that connects mid-run or after completion can replay
everything it missed instead of only seeing events from the moment it
connected, and an HTTP polling client never needs a WebSocket at all.

The plan calls for "UUID-based sessions persisted in PostgreSQL". SQLite was
used as a documented substitution through Week 17 (no Postgres instance
existed yet). Week 18 (Docker Compose) resolves that: `PostgresSessionStore`
below is the real thing, used automatically whenever `DATABASE_URL` is set
(see `build_session_store`) — `SessionStore` (SQLite) remains the default
for plain `make serve`, the same "degrades gracefully to local-only when the
real infra isn't there" pattern already used for Redis caching everywhere
else in this project.

`sessions.user_id` (added alongside real user accounts, see `api/users.py`
and `api/auth.py`) links a session to the account that created it, so
`GET /plan/{id}` and friends can enforce that a user only ever sees their
own trips. Nullable, and migrated onto pre-existing tables additively (see
`_add_user_id_column_sqlite`) rather than requiring a fresh database —
sessions created before accounts existed simply have no owner and become
unreachable through the now-authenticated endpoints, which is the correct,
expected consequence of adding real per-user ownership after the fact.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    parent_session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _add_user_id_column_sqlite(conn: sqlite3.Connection) -> None:
    # `CREATE TABLE IF NOT EXISTS` above only helps a brand-new database —
    # every `sessions.sqlite` from before real user accounts existed already
    # has a `sessions` table with no `user_id` column, and SQLite has no
    # `ADD COLUMN IF NOT EXISTS`. Idempotent by catching the one error
    # "already has this column" produces, not by checking first (avoids a
    # TOCTOU race, though this store is already single-connection/locked).
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
        conn.commit()
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


@dataclass
class SessionRecord:
    session_id: str
    status: str
    raw_text: str
    parent_session_id: str | None
    created_at: str
    updated_at: str
    user_id: str | None = None


@dataclass
class SessionEvent:
    id: int
    event_type: str
    payload: dict[str, Any]
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SessionStore:
    def __init__(self, db_path: str = "sessions.sqlite") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            _add_user_id_column_sqlite(self._conn)

    def create(
        self,
        session_id: str,
        raw_text: str,
        parent_session_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions "
                "(session_id, status, raw_text, parent_session_id, created_at, updated_at, "
                "user_id) "
                "VALUES (?, 'running', ?, ?, ?, ?, ?)",
                (session_id, raw_text, parent_session_id, now, now, user_id),
            )
            self._conn.commit()

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return SessionRecord(**dict(row)) if row else None

    def update_status(self, session_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status, _now(), session_id),
            )
            self._conn.commit()

    def append_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (session_id, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(payload, default=str), _now()),
            )
            self._conn.commit()

    def list_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT session_id FROM sessions").fetchall()
        return [row["session_id"] for row in rows]

    def list_by_user(self, user_id: str) -> list[SessionRecord]:
        # Only top-level sessions (no parent) — one row per trip a user
        # started via /plan, not one per /refine follow-up too, matching the
        # dashboard's "one card per trip" mental model.
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? AND parent_session_id IS NULL "
                "ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [SessionRecord(**dict(row)) for row in rows]

    def get_events(self, session_id: str, after_id: int = 0) -> list[SessionEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE session_id = ? AND id > ? ORDER BY id ASC",
                (session_id, after_id),
            ).fetchall()
        return [
            SessionEvent(
                id=row["id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]


_POSTGRES_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    parent_session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_POSTGRES_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class PostgresSessionStore:
    """Real thing the plan asked for ("UUID-based sessions persisted in
    PostgreSQL") — same public interface as `SessionStore` (SQLite), used
    automatically instead of it whenever `DATABASE_URL` is set. See
    `build_session_store`.
    """

    def __init__(self, database_url: str) -> None:
        # autocommit rather than an explicit .commit() per method: this
        # store's writes are already one-statement-per-call, so there's no
        # multi-statement transaction to batch, and it keeps every method
        # below a direct mirror of SessionStore's.
        self._conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(_POSTGRES_SESSIONS_TABLE)
            self._conn.execute(_POSTGRES_EVENTS_TABLE)
            # Postgres, unlike SQLite, supports ADD COLUMN IF NOT EXISTS
            # directly - no try/except migration dance needed here.
            self._conn.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_id TEXT")

    def create(
        self,
        session_id: str,
        raw_text: str,
        parent_session_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions "
                "(session_id, status, raw_text, parent_session_id, created_at, updated_at, "
                "user_id) "
                "VALUES (%s, 'running', %s, %s, %s, %s, %s)",
                (session_id, raw_text, parent_session_id, now, now, user_id),
            )

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
            ).fetchone()
        return SessionRecord(**row) if row else None

    def update_status(self, session_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET status = %s, updated_at = %s WHERE session_id = %s",
                (status, _now(), session_id),
            )

    def append_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (session_id, event_type, payload, created_at) "
                "VALUES (%s, %s, %s, %s)",
                (session_id, event_type, json.dumps(payload, default=str), _now()),
            )

    def list_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT session_id FROM sessions").fetchall()
        return [row["session_id"] for row in rows]

    def list_by_user(self, user_id: str) -> list[SessionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE user_id = %s AND parent_session_id IS NULL "
                "ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [SessionRecord(**row) for row in rows]

    def get_events(self, session_id: str, after_id: int = 0) -> list[SessionEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE session_id = %s AND id > %s ORDER BY id ASC",
                (session_id, after_id),
            ).fetchall()
        return [
            SessionEvent(
                id=row["id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]


def build_session_store(database_url: str | None) -> SessionStore | PostgresSessionStore:
    """Postgres when `DATABASE_URL` is set (Docker Compose), SQLite
    otherwise (plain `make serve`) — the default `create_app()` uses."""
    return PostgresSessionStore(database_url) if database_url else SessionStore()
