# ADR-0004: SQLite as the zero-setup default, PostgreSQL opt-in via `DATABASE_URL`

**Status**: Accepted (Week 18)

## Context

The plan specifies PostgreSQL for session storage from the start.
Requiring a real Postgres instance for every local `make serve` — the
command a fresh clone runs first — adds real setup friction (install
Postgres, create a database, manage credentials) for a solo project meant
to be runnable and demoable with minimal ceremony. LangGraph's own
checkpointer abstraction supports both SQLite and Postgres backends behind
the same interface.

## Decision

Ship two implementations behind one factory: `SqliteSessionStore` /
`build_sqlite_checkpointer` (zero setup, a local file) as the default for
plain `make serve`, and `PostgresSessionStore` / `build_postgres_checkpointer`
(Week 18) used automatically the moment `DATABASE_URL` is set — the same
env-var-presence-gates-real-infra pattern this project already used for
Redis caching since Week 2. `docker-compose.yml` sets `DATABASE_URL` itself
to point at its own `postgres` service; nothing else changes.

## Consequences

- **Positive**: `make install && make serve` works with zero database setup
  on a completely fresh machine — verified directly, since this project's
  own development machine needed Postgres installed via Homebrew
  specifically to *test* the Postgres path, confirming the SQLite path
  truly requires nothing extra.
- **Positive, but only after a real bug was found and fixed**: switching to
  Postgres surfaced a genuine subtlety in `PostgresSaver.from_conn_string`
  — it's a `@contextmanager`-decorated generator, and discarding the
  context-manager object after entering it lets Python's GC finalize the
  generator and silently close the connection out from under the returned
  checkpointer. Caught by live-testing against a real local Postgres
  instance, not by unit tests with mocked connections — a large part of
  why this project consistently prioritizes live-testing against real
  infrastructure over trusting mocks alone.
- **Negative**: two code paths to maintain and test (`test_sessions.py` and
  `test_sessions_postgres.py` / `test_checkpointers.py`, the latter
  real-Postgres-gated and skipped in CI environments without one) instead
  of one. Accepted as a reasonable cost for keeping the default developer
  experience friction-free.
