# Autonomous AI Travel Planning Agent

End-to-end agentic system for personalized trip planning, itinerary building, and logistics.
Built over a 24-week plan (see `docs/`); this repo tracks progress phase by phase.

## Status

**Phase 1, Week 1 — Project Scaffold, Environment & API Setup** — done

- [x] Repo scaffold, Poetry project, pre-commit (black, ruff)
- [x] Core Pydantic data models (`TravelPreferences`, `FlightOption`, `HotelOption`,
      `Attraction`, `Restaurant`, `Itinerary`, ...)
- [x] `PreferenceParser` v1 (GPT-4o via LangChain structured output)
- [x] Unit tests for `PreferenceParser` and core models
- [x] All 7 external APIs registered and smoke-tested (`make smoke`)

**Phase 1, Week 2 — Flight Search & Hotel Search Tools** — done

- [x] `FlightSearchTool` (TravelPayouts: merges `/v1/prices/cheap` + `/v2/prices/latest`)
- [x] `HotelSearchTool` (Booking.com via RapidAPI: destination lookup + hotel search)
- [x] Redis-backed response caching (`utils/cache.py`), graceful no-op if Redis is down
- [x] Retry/backoff on transient errors; deterministic mock-data fallback (`is_mock_data` flag)
- [x] 26 unit tests across both tools (mocked HTTP via `responses`), plus 6 for the cache layer

**Phase 1, Week 3 — Attraction, Restaurant & Weather Tools** — done

- [x] `AttractionFinderTool` and `RestaurantFinderTool` (both via Serper's `/places`
      endpoint, which returns structured name/lat/lng/rating/category/price directly —
      no separate OpenStreetMap or Google Places calls needed)
- [x] `WeatherCheckerTool` (OpenWeatherMap geocode + free-tier 5-day/3-hour forecast,
      aggregated into one `WeatherForecast` per day with a derived comfort score)
- [x] `BudgetTrackerTool` (pure computation: per-category running tally, remaining budget)
- [x] Shared `utils/http.py` retry/timeout helper, used by all three new HTTP-backed tools
- [x] 46 new unit tests + 1 integration test simulating a full 5-day London trip across
      all four tools together

**Phase 1, Week 4 — LangGraph State Machine & Tool Orchestration** — done

- [x] Typed `PlanningState` + `determine_valid_steps`: encodes hard dependencies
      (preferences must exist before any search; flights need an origin; weather
      needs a start date) as code, not something the LLM has to infer
- [x] `SupervisorAgent`: skips the LLM entirely when only one step is valid; calls
      it (with structured output, validated against the allowed set) only when
      multiple independent tools are all ready and an order must be chosen
- [x] All 6 tools wired into StateGraph nodes, each catching its own exceptions
      into `errors` so one tool failing doesn't halt the run
- [x] SQLite-backed checkpointer (`langgraph-checkpoint-sqlite`) — verified state
      persists and is retrievable across a fresh connection using just a `thread_id`
- [x] End-to-end smoke test: real natural-language input → all 6 tools called → full
      itinerary-ready state assembled, live against all real APIs
- [x] 34 new unit/integration tests (state routing, supervisor, each node, and the
      full compiled graph with stubbed tools)

**Phase 2, Week 5 — Itinerary Builder v1: Time Slot Assignment** — done

- [x] `ItineraryBuilder`: arrival day (flight → transfer → check-in → dinner if time
      allows), full middle days (morning/lunch/afternoon/dinner), departure day
      (checkout → airport transfer)
- [x] `TravelTimeEstimator`: real Google Distance Matrix lookups between consecutive
      activities, cached, with a flat-minute fallback on any failure
- [x] Fixed, category-appropriate time windows stand in for real opening-hours data
      (neither Serper nor Booking.com actually supply it); travel time can push a
      booking later within its window or skip it entirely if it can't fit
- [x] Caught and fixed a real bug during live testing: TravelPayouts returns the
      cheapest fare found *near* the requested month, not on the exact date, so the
      builder was anchoring Day 1 to the flight's own (wrong) date. Fixed by using
      only the flight's time-of-day, anchored to the itinerary's actual start date
- [x] Wired into the LangGraph as a final `build_itinerary` step, run once every
      search tool has completed
- [x] Live-tested end-to-end against all 3 required trip types (city tour, beach
      holiday, adventure trip) plus 25 new unit tests

## Setup

```bash
cp .env.example .env   # fill in your API keys
make install
make test
```

## Project layout

```
src/travel_agent/
  config.py          # env-based settings
  models/core.py      # shared Pydantic domain models
  tools/               # one module per agent tool (PreferenceParser, FlightSearchTool, ...)
  agents/              # LangGraph agent/graph definitions (added Week 4+)
  utils/
tests/
  unit/
  integration/
  e2e/
```

## Tech stack

Python 3.11+, LangGraph + LangChain, OpenAI GPT-4o, FastAPI, React (added later phases),
PostgreSQL + Redis, Docker, pytest.
