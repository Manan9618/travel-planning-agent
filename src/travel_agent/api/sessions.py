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

The plan calls for "UUID-based sessions persisted in PostgreSQL"; there's no
PostgreSQL instance in this project yet (Docker Compose arrives in Week 18),
so SQLite is used instead — the same kind of documented substitution as
TravelPayouts for Amadeus (Week 2) or GPT-4o for Claude (Week 12). Swapping
the backing store for Postgres later only touches this one file.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

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


@dataclass
class SessionRecord:
    session_id: str
    status: str
    raw_text: str
    parent_session_id: str | None
    created_at: str
    updated_at: str


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

    def create(self, session_id: str, raw_text: str, parent_session_id: str | None = None) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions "
                "(session_id, status, raw_text, parent_session_id, created_at, updated_at) "
                "VALUES (?, 'running', ?, ?, ?, ?)",
                (session_id, raw_text, parent_session_id, now, now),
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
