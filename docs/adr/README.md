# Architecture Decision Records

Week 23 deliverable. Each ADR documents one real, consequential design
decision made during this project's 24-week build — not a hypothetical
retrospective, but the actual reasoning behind a choice that shipped, with
the real tradeoffs and (where relevant) the real bug or constraint that
drove it. Format follows the standard lightweight ADR template (Status /
Context / Decision / Consequences).

| # | Title | Week |
|---|---|---|
| [0001](0001-langgraph-supervisor-loop.md) | LangGraph supervisor-loop architecture over a plain sequential script | 4 |
| [0002](0002-mock-data-fallback-everywhere.md) | Every external API call degrades to deterministic mock data instead of failing hard | 2 |
| [0003](0003-travelpayouts-over-amadeus.md) | TravelPayouts instead of Amadeus for flight search | 2 |
| [0004](0004-sqlite-default-postgres-optional.md) | SQLite as the zero-setup default, PostgreSQL opt-in via `DATABASE_URL` | 18 |
| [0005](0005-native-fanout-over-asyncio-gather.md) | LangGraph's native list-return fan-out instead of `asyncio.gather` for parallel tool execution | 20 |
| [0006](0006-sync-graph-stream-background-thread.md) | Sync `graph.stream()` in a background thread instead of LangGraph's async `.astream()` | 15 |

Each ADR links back to the README's own per-week Status entry where the
decision is also documented in the context of everything else that shipped
that week — these are the "why," the README is the "what and when."
