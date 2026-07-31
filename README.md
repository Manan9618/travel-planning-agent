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

**Phase 2, Week 6 — Conflict Detection & Resolution** — done

- [x] `ConflictDetector`: five constraint types — overlapping items, physically
      impossible travel gaps (real Distance Matrix lookups), budget overruns,
      too many activities per day, and restaurants outside normal meal hours
- [x] `ConflictResolver`: shifts times, drops the lowest-priority activity, or
      trims the most expensive optional items until back under budget. Returns
      unresolved only when fixed costs (flights, hotel) alone exceed the budget
- [x] `detect_and_resolve`: bounded iterative loop — live-testing showed that
      fixing one conflict can surface another (a meal-time fix can create a new
      impossible-travel gap), so a single detect→resolve pass isn't enough
- [x] Human-in-the-loop `human_review` step using LangGraph's real `interrupt()`/
      `Command(resume=...)` API: the graph genuinely pauses (verified via a live
      forced-unresolvable-budget scenario) and resumes correctly on approval or
      rejection
- [x] Every resolution attempt, successful or not, is logged (`ResolutionLogEntry`)
      for later evaluation analysis
- [x] 47 new tests (20 detector scenarios, 13 resolver scenarios including the
      cascading-conflict case, plus node-level and full-graph human-in-the-loop
      integration tests)

**Phase 2, Week 7 — Weather-Aware Scheduling** — done

- [x] `weather_matcher.py`: keyword-based indoor/outdoor classifier for attractions
      (no data source we use tags this explicitly), a bad-weather check (high rain
      probability or low comfort score), and the `weather_adaptation_rate` metric
- [x] `ItineraryBuilder` now prefers outdoor attractions on good-weather days and
      indoor ones (museums, galleries) on bad-weather days, falling back to the
      original rating-sorted order when there's no forecast or no clear match
- [x] Narrative warnings per day (`DayPlan.warnings`) — "Pack rain gear", heat/cold/
      wind alerts — surfaced from the same forecast used for scheduling
- [x] Found and fixed a real Week 5 bug while reworking the attraction-picking
      logic: the day-index arithmetic for the first full day started at 1 instead
      of 0, so the top one or two highest-rated attractions were silently never
      scheduled in any itinerary
- [x] A/B test script (`scripts/weather_ab_test.py`) across 10 real destinations
      with a controlled good/bad weather pattern: weather-aware scheduling hit
      100% adaptation rate on every destination vs. a 39% baseline average — a
      measured +61 point improvement
- [x] 27 new tests (weather_matcher classification/metric, weather-aware
      ItineraryBuilder scenarios including a regression test for the Week 5 bug,
      and node-level weather pass-through)

**Phase 2, Week 8 — Budget Optimization & Constraint Satisfaction** — done

- [x] `BudgetOptimizer`: flights are a market-price pass-through (not allocated a
      percentage); whatever budget remains after flights is split across hotel/
      food/activities using backpacker/mid-range/luxury tier defaults, shiftable
      by `TravelPreferences.priority_weights` (e.g. "I prioritize accommodation
      over dining")
- [x] Per-category evaluation against the actual built itinerary — upgrade
      suggestions when a category is well under its allocation, cut suggestions
      when it's over, using `itinerary_cost_breakdown` (new in `budget_tracker.py`)
- [x] `budget_adherence_score`: 1.0 for an exact match to the stated budget,
      decreasing symmetrically for both overspend and underspend
- [x] Wired into the LangGraph as an `optimize_budget` step, running after
      conflicts are resolved so the evaluation reflects the final itinerary
- [x] Live-verified tier splits, priority-weight shifting, and upgrade/cut
      suggestions against real search results across all three tiers
- [x] 20-scenario constraint satisfaction script (`scripts/budget_scenarios_test.py`)
      spanning tiers, priority weights, and budget levels from tight to generous
- [x] 39 new tests (budget_tracker breakdown/adherence, BudgetOptimizer allocation/
      evaluation, node-level, and updated graph-routing tests)

**Phase 3, Week 9 — Geospatial Data Pipeline** — done

- [x] Attractions/hotels already carry precise lat/lng directly from Serper/
      Booking.com (Weeks 2-3) — no separate geocoding/enrichment step was needed,
      since we'd chosen data sources that supply coordinates natively
- [x] `DistanceMatrixTool`: real NxN travel-time matrix via Google's batched
      Distance Matrix API — one request per origin (covering up to 100
      destinations each) instead of N² individual pairwise calls, chunked to
      respect Google's per-request element cap
- [x] Shares its Redis cache-key format with Week 5's single-pair
      `TravelTimeEstimator`, so pairs either tool has already computed are never
      re-fetched by the other
- [x] `geo_clustering.py`: DBSCAN clustering with a **haversine** metric (not
      Euclidean on raw degrees, which would distort east-west vs. north-south
      distances inconsistently across cities at different latitudes) — `eps` is
      expressed in real-world km
- [x] Folium map rendering, color-coded by cluster
- [x] Live-verified clustering quality on all 3 required cities (Paris, Tokyo,
      New York) via `scripts/geo_clustering_test.py`: geographically sensible
      results throughout (e.g. Paris's historic center clusters together while
      the Arc de Triomphe — genuinely ~2km further out — is correctly flagged as
      noise; NYC splits cleanly into a Financial District cluster and a Midtown
      cluster)
- [x] 20 new tests, including a haversine-scaling correctness check (verifies
      the km<->degree conversion isn't silently wrong)

**Phase 3, Week 10 — Route Optimization** — done

- [x] `RouteOptimizerTool`: Nearest Neighbor construction (greedy TSP
      approximation) followed by 2-opt local search, with the hotel as a fixed
      start/end point ("start near hotel, end near hotel")
- [x] Correctly handles **asymmetric** travel times (real driving/transit data
      reflects one-way streets and transit-line directionality, so A→B and B→A
      legitimately differ) — 2-opt recomputes the full tour length per candidate
      swap rather than taking the classic boundary-edges-only shortcut, which is
      only valid for symmetric distances. Verified with an adversarial regression
      test where the boundary-only shortcut would accept a swap that's actually
      far worse once a flipped internal edge is accounted for
- [x] `route_efficiency_score`: naive/optimized travel-time ratio, with the naive
      baseline averaged over multiple random shuffles rather than a single one
- [x] 20-scenario benchmark (`scripts/route_optimization_benchmark.py`, 5 real
      cities × 4 activity-set sizes) against a real Distance Matrix: **+45%
      average efficiency gain** over random ordering (range +10% to +92%,
      generally scaling up with more activities per day, as expected)
- [x] 19 new tests, including the asymmetric-matrix correctness regression and
      an invariant check that 2-opt never produces a worse tour than plain
      Nearest Neighbor across 20 randomized matrices

**Phase 3, Week 11 — Multi-Day Itinerary Optimizer** — done

- [x] `MultiDayOptimizer` sits above `ItineraryBuilder`: it decides WHICH
      attractions go on WHICH day (clustering + must-see priority + a bounded
      backtracking search against a per-day activity budget), route-optimizes
      each day's visiting order, and rebalances walking distance across days —
      then delegates the actual time-slot/weather-swap mechanics to a new
      `ItineraryBuilder.build_day()` public method, reusing the tested Week 5/7
      logic rather than duplicating it
- [x] Priority-based scheduling: `TravelPreferences.must_see` attractions are
      sorted first (by rating) ahead of "nice-to-have" ones, which are grouped
      by geographic cluster (largest cluster first) so nearby attractions tend
      to land on the same day
- [x] Real backtracking (not just greedy): candidate day-assignments are tried
      highest-priority-first; a combination that would push a day's estimated
      cost over its soft per-day activity budget (derived from Week 8's
      `BudgetOptimizer`) is rejected and the search backtracks to the next
      combination — undoing and retrying rather than committing to the first
      guess. Falls back to the cheapest available combination if none fit, so
      a day is never left empty
- [x] Cross-day balancing: after initial assignment, the day with the most
      total travel time and the day with the least repeatedly try swapping one
      attraction between them, keeping the swap only if it narrows the spread
- [x] A single batched Distance Matrix call (Week 9's `DistanceMatrixTool`,
      covering the hotel + every attraction that could be scheduled) backs
      every travel-time lookup used during assignment/balancing/ordering —
      found and fixed a real performance issue during live testing: an
      earlier version called the single-pair `TravelTimeEstimator` repeatedly
      during balancing/ordering, which on a cold cache meant dozens of
      redundant network round-trips
- [x] Performance: the optimizer's own computation (clustering, backtracking,
      route ordering, balancing) completes in single-digit milliseconds for a
      7-day/20-attraction trip, verified with fixed test doubles (no network
      involved) — comfortably inside the plan's <5s target. End-to-end wall
      time against real APIs is dominated by `ItineraryBuilder`'s per-item
      restaurant-transition Distance Matrix lookups (an existing Week 5
      characteristic, not part of Week 11's algorithm) and drops to
      milliseconds on a warm cache
- [x] Wired in as the LangGraph's default `build_itinerary` tool (same
      `.build()` signature as `ItineraryBuilder`, so it's a drop-in default;
      pass an explicit `ItineraryBuilder()` to opt out)
- [x] Live-tested via `scripts/multi_day_optimizer_benchmark.py` — 10 real
      trip scenarios across 5 cities, varying trip length/budget tier/must-see
      attractions: 100% must-see coverage across scenarios that specified one,
      46% average budget adherence (mock hotel pricing from Booking.com's
      exhausted RapidAPI quota skews this — see Week 2's known issue), 11
      minutes average day-to-day travel spread
- [x] 23 new tests: 19 for `MultiDayOptimizer` (must-see priority sorting,
      backtracking budget constraint satisfaction and graceful degradation,
      cross-day balancing, route ordering, batched-matrix call-count
      invariant, edge cases, and a performance regression test) plus 4 direct
      tests of the new `ItineraryBuilder.build_day()` entry point

**Phase 3, Week 12 — Agent Evaluation Framework** — done

- [x] 10-dimension rubric, split deliberately between what code can measure
      exactly and what genuinely needs judgment:
      - **6 computed** (`ItineraryEvaluator`, no LLM cost): `feasibility`
        (penalizes each `ConflictDetector` conflict), `budget_accuracy`
        (Week 8's `budget_adherence_score` × 10), `geo_efficiency` (the
        itinerary's as-scheduled route length vs. a naive-random baseline,
        same methodology as Week 10's `route_efficiency_score`),
        `weather_match` (Week 7's `weather_adaptation_rate` × 10),
        `completeness` (full-day slot-fill rate + must-see coverage), and
        `variety` (distinct attraction categories ÷ total scheduled)
      - **4 LLM-judged** (`ItineraryJudge`, GPT-4o — substituted for the
        plan's "Claude grades it" to stay on this project's one established
        LLM choice, the same kind of documented swap as TravelPayouts for
        Amadeus): `personalization_fit`, `narrative_quality`,
        `practicality`, `overall_satisfaction`
      - A dimension that doesn't apply (no budget stated, no weather data in
        range, fewer than 2 attractions scheduled) scores `None` and is
        excluded from that itinerary's overall average rather than dragging
        it down
- [x] `scripts/agent_evaluation.py`: 25 real trip scenarios across 13 cities,
      covering all 6 of the plan's named trip styles (city/beach/adventure/
      family/solo/honeymoon) with varying budgets, tiers, pace, and
      must-see lists; two scenarios deliberately use a near-term start date
      so `weather_match` is exercised at least once rather than reading
      "n/a" for every scenario (every other scenario uses a realistic
      45-day-out start, like every prior live-test script)
- [x] Live-run baseline results (`output/evaluation/evaluation_results.csv` +
      `evaluation_report.html`, gitignored like other generated `output/`):
      **5.52/10 average overall score** across all 25 scenarios;
      `feasibility` was a perfect 10.0 on every single scenario (Weeks 5-11's
      avoid-conflicts-by-construction approach is working)
- [x] Investigated and root-caused the 5 lowest-scoring dimensions rather than
      just reporting the numbers:
      1. **`variety` (2.5/10)** — traced to Serper's `/places` API returning
         the generic category `"Tourist attraction"` for nearly everything
         (verified directly against live Paris results), not an actual lack
         of diversity in what's scheduled. Improvement task: derive a finer
         category from the attraction's name/description text, the same
         keyword-classification approach `weather_matcher.py` already uses
         for indoor/outdoor.
      2. **`budget_accuracy` (3.8/10)** — the 3 worst-scoring scenarios were
         all luxury-tier honeymoons; traced to Booking.com's exhausted
         RapidAPI quota (documented since Week 2) forcing every scenario
         onto the same flat mock hotel price regardless of requested tier,
         so luxury budgets go massively underspent. Improvement task: scale
         the mock-hotel fallback price by requested `BudgetTier`.
      3-5. **`overall_satisfaction`, `narrative_quality`, `personalization_fit`
         (4.4-4.5/10)** — the LLM judge's own explanations repeatedly cited
         low attraction/restaurant variety, consistent with failure mode 1;
         likely to improve directly once that's fixed rather than needing
         separate work.
- [x] 30 new tests (8 for `ItineraryJudge`'s summary rendering and structured
      output, 22 for `ItineraryEvaluator`'s 6 computed dimensions and overall
      report assembly); 399 total passing, 98% coverage

**Phase 4, Week 13 — Interactive Map Generation** — done

- [x] `TravelMapGenerator`: Folium/Leaflet map with a hotel pin, one pin per
      scheduled attraction/restaurant/hotel check-in/out — color-coded by day
      (Day 1 = blue, Day 2 = green, ... cycling through a 10-color palette)
      with a popup info card (title, time, activity type, cost) — and a
      polyline per day connecting that day's stops in chronological order
- [x] `MarkerCluster` (a real Folium/Leaflet plugin, not a bespoke one) groups
      nearby pins together at low zoom so the map stays readable
- [x] Day-by-day reveal animation via Folium's `TimestampedGeoJson` plugin: a
      genuine Leaflet timeline slider control: each day's route is one
      GeoJSON feature sharing a single timestamp (that day's date), so
      advancing the slider reveals a whole day's route at once and earlier
      days stay visible rather than animating point-by-point
- [x] `.save()` exports a self-contained HTML file (same Folium-file
      convention as Week 9's cluster maps); `render_thumbnail_png()`
      rasterizes it to PNG via a headless Chromium (Playwright, newly added
      dependency — `make install` now also runs `playwright install
      chromium`) for embedding in Week 14's PDF, which can't render live
      Leaflet JS
- [x] Wired into the LangGraph as a new `generate_map` step, running after
      `optimize_budget` and before `human_review`; `PlanningState` gained a
      `map_html` field
- [x] Found and fixed a real bug while visually inspecting a live-rendered
      thumbnail: `HotelSearchTool`'s Week 2 mock-data fallback (used whenever
      Booking.com's RapidAPI quota is exhausted — a running known issue)
      hardcoded the mock hotel's coordinates to `(0.0, 0.0)` ("Null Island").
      This silently explains recurring "Distance Matrix ZERO_RESULTS"
      fallback warnings seen in live tests since Week 9 (Google can't route
      to/from Null Island) and, more visibly, put Week 13's map thumbnail
      hundreds of kilometers from the actual destination. Fixed by geocoding
      the destination via the Google Maps API (reusing the same key already
      authenticated for Distance Matrix) as a one-shot, non-retrying
      best-effort lookup, falling back to `(0.0, 0.0)` only if that also fails
- [x] Live-tested via `scripts/map_generation_test.py` against two real
      built itineraries (Paris, Tokyo — real attractions/restaurants via
      Serper, `MultiDayOptimizer`); visually verified via the rendered PNG
      thumbnails that the map now centers correctly, clusters pins sensibly,
      and shows distinct day-colored routes, output under `output/maps/`
- [x] 21 new tests (`TravelMapGenerator` structure/markers/routes/timeline/
      export, the new `generate_map` node, and the hotel geocoding fallback,
      including its own fallback-of-a-fallback case); 420 total passing, 98%
      coverage

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
PostgreSQL + Redis, Docker, pytest, Folium, Playwright.
