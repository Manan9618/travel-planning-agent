# ADR-0001: LangGraph supervisor-loop architecture over a plain sequential script

**Status**: Accepted (Week 4)

## Context

The agent needs to run up to 12 distinct steps per trip (parse preferences,
5 independent searches, build the itinerary, enrich it, check conflicts,
optimize budget, generate outputs, optionally pause for human review) with
real dependencies between some steps (search needs parsed preferences;
itinerary-building needs search results) but not others (the 5 searches
don't depend on each other). Failures are expected and routine — every
external API in this project has a documented, common failure mode
(rate limits, quota exhaustion, timeouts) that must not halt the whole run.
The system also needs to pause mid-run for human input (Week 6's conflict
review) and resume later, potentially in a different process.

A plain Python script calling functions in sequence was the simplest
alternative: easy to write, easy to debug with a stack trace. But it can't
express "these 5 steps have no ordering constraint," can't pause and
resume across process boundaries without hand-rolled state serialization,
and turns "retry just the failed step" into ad-hoc control flow that grows
more tangled with every new step added.

## Decision

Model the pipeline as a LangGraph `StateGraph`: a typed `PlanningState`
threaded through every node, a `supervisor` node that decides what runs
next via `determine_valid_steps` (hard dependencies encoded as plain code,
not left for an LLM to infer), worker nodes that each catch their own
exceptions and record them in `state["errors"]` rather than raising, and a
checkpointer (SQLite by default, Postgres in Docker Compose — see
[ADR-0004](0004-sqlite-default-postgres-optional.md)) that persists full
state after every step.

## Consequences

- **Positive**: resuming a paused run (human-in-the-loop, Week 6) is just
  re-invoking the graph with the same `thread_id` — no custom state
  machine to maintain. A step's failure is contained to that step; the
  supervisor moves on and the run still produces a usable (if partial)
  result. Adding a 13th step later meant adding one node and one
  `determine_valid_steps` branch, not restructuring a call chain.
- **Negative**: LangGraph is a real dependency with its own version-
  compatibility surface (a `langgraph-checkpoint-postgres`/`langgraph`
  version mismatch warning has been a known, accepted risk since Week 18)
  and its own execution model to learn (Pregel supersteps, checkpointers,
  `Command(resume=...)`) that a plain script wouldn't require.
- Later found to have a genuine, non-obvious payoff: LangGraph's
  conditional edges support returning a *list* of node names, not just
  one — a first-class "fan out to parallel nodes in one superstep"
  feature this project didn't originally plan to use but adopted in Week
  20 (see [ADR-0005](0005-native-fanout-over-asyncio-gather.md)) once it
  was discovered by reading LangGraph's own source.
