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
