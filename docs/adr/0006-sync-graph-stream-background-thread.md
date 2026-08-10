# ADR-0006: Sync `graph.stream()` in a background thread instead of LangGraph's async `.astream()`

**Status**: Accepted (Week 15)

## Context

The FastAPI backend needs to run a planning graph (potentially taking tens
of seconds — see Week 20's benchmark, ~47s for a full real trip) without
blocking the event loop, while streaming step-progress and narration
events over a WebSocket as they happen. FastAPI's own idiom for this is
native `async`/`await` throughout, which would suggest LangGraph's async
`.astream()` API paired with an async-compatible checkpointer.

At the time this was built, the current `langgraph-checkpoint-sqlite`
release's `AsyncSqliteSaver` calls `conn.is_alive()` on its underlying
`aiosqlite` connection — a method newer `aiosqlite` releases removed
outright. Fixing this cleanly would require an unrelated major-version
bump across the LangGraph checkpoint stack, a larger and riskier change
than this week's actual scope.

A second approach was tried and rejected before landing on the one
described below: polling `graph.get_state()` from the event loop *while*
`graph.invoke()` ran concurrently in another thread. This reliably hung,
because both threads ended up touching the same raw `sqlite3` checkpointer
connection at the same time — `check_same_thread=False` only disables
Python's own same-thread assertion, it does not make the connection safe
for genuinely concurrent access from two threads.

## Decision

Run the existing, already-tested sync `graph.stream()` (unchanged since
Week 4) inside a single background thread via `asyncio.to_thread`, and
consume its per-node chunks *inside* that same thread, appending each to
the session's event log as they arrive. The event loop only ever reads
`graph.get_state()` afterward, once the background thread has finished —
never while it's still running. This means only one thread ever touches
the checkpointer's connection at a time, sidestepping the concurrency issue
without needing the checkpointer itself to be thread-safe for concurrent
access.

## Consequences

- **Positive**: no LangGraph major-version bump was needed to ship Week
  15's WebSocket streaming, and the graph execution path itself (already
  covered by the Week 4-14 test suite) needed zero changes — only the
  FastAPI-side orchestration around it is new.
- **Positive**: this same synchronous execution model turned out to be
  exactly what Week 20's real parallel-fan-out mechanism needed (see
  [ADR-0005](0005-native-fanout-over-asyncio-gather.md)) — LangGraph's sync
  executor's `ThreadPoolExecutor`-based superstep concurrency wasn't
  something this decision was made in anticipation of, but it composed
  cleanly with it later.
- **Negative**: a real, accepted residual risk — `langgraph-checkpoint-postgres`
  (added Week 18) emits a `DeprecationWarning` on every import
  about a version incompatibility with the pinned LangGraph release, since
  fixing it requires the same kind of major-version bump this decision
  avoided in Week 15. Mitigated by thorough live-testing rather than the
  version bump, and explicitly documented as a known, accepted risk rather
  than silently ignored.
- **Negative**: `asyncio.to_thread` means one worker thread is occupied for
  the full duration of every in-flight planning run — acceptable at this
  project's scale (rate-limited to 10 requests/minute per client, Week 15)
  but a real ceiling on concurrent-session throughput that a fully async
  pipeline wouldn't have.
