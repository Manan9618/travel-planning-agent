# ADR-0005: LangGraph's native list-return fan-out instead of `asyncio.gather` for parallel tool execution

**Status**: Accepted (Week 20)

## Context

Five of the twelve planning steps — `search_flights`, `search_hotels`,
`find_attractions`, `find_restaurants`, `check_weather` — have no
dependency on each other's results, only on the same upstream preferences.
Before Week 20, `SupervisorAgent` picked exactly one of them per turn (an
LLM call to break the tie when more than one was simultaneously valid),
serializing 5 independent, network-bound calls that could run concurrently.
The plan's own Week 20 line item names `asyncio.gather` as the expected
mechanism for parallel tool execution — the obvious choice for a Python
codebase already using `async`/`await` at the FastAPI layer.

But the graph itself runs synchronously: `app.py`'s `_drive_graph` calls
the compiled graph's sync `.stream()` inside a single background thread via
`asyncio.to_thread`, specifically because LangGraph's async checkpointer
for SQLite (`AsyncSqliteSaver`) has a real upstream bug (calls
`conn.is_alive()`, which newer `aiosqlite` releases removed) — see
[ADR-0006](0006-sync-graph-stream-background-thread.md). Introducing
`asyncio.gather` inside a single synchronous node would require either
spinning up a nested event loop inside a thread already running one turn
of a sync generator, or restructuring the whole execution model this
project deliberately chose to avoid in Week 15.

## Decision

Read LangGraph's own source (`StateGraph.add_conditional_edges`) rather
than assume `asyncio.gather` was the only option, and found that a
conditional edge's routing function is typed to return
`Hashable | list[Hashable]` — returning a list of node names is a
first-class, supported way to fan out to multiple nodes in the same Pregel
superstep, and LangGraph's sync executor runs each ready node of one
superstep through a real `ThreadPoolExecutor`
(`langgraph.pregel.executor`) — genuine OS-thread concurrency for
network-bound I/O, not simulated. `make_supervisor_node` was changed to
return `{"next_step": [step.value for step in valid]}` whenever more than
one step is simultaneously valid, instead of asking `SupervisorAgent` to
pick one.

## Consequences

- **Positive**: no architecture change was needed to get real parallelism
  — the existing sync `graph.stream()` execution model, chosen for the
  `AsyncSqliteSaver` bug workaround, turned out to already have a native
  parallel-execution mechanism once looked for. Live-tested and measured:
  5 search nodes that individually summed to ~19.7s of work completed
  within a 3.35s wall-clock window in a real run, and a direct
  sequential-vs-concurrent A/B benchmark measured a 2.92x speedup.
- **Positive, a side effect the plan didn't anticipate**: fanning out
  instead of picking one made `SupervisorAgent`'s GPT-4o tie-break call
  provably unreachable in every real code path — removed entirely rather
  than left as dead code, directly serving the plan's "reduce LLM token
  usage" goal for this specific call site.
- **Negative**: this is a LangGraph-specific mechanism, not a general
  Python pattern — a reader familiar with `asyncio.gather` but not with
  Pregel's superstep model has to learn a new mental model to understand
  why returning a list from a routing function triggers concurrency,
  whereas `asyncio.gather` inside an async node would have been more
  immediately recognizable, at the cost of the checkpointer conflict noted
  above.
