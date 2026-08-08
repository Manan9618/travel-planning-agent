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

**Phase 4, Week 14 — PDF Itinerary Generator** — done

- [x] `PDFGenerator` (WeasyPrint — HTML/CSS rendered straight to PDF, no
      headless browser needed, unlike Week 13's map thumbnails): a cover page,
      an executive summary, one section per day, an embedded map thumbnail
      with an optional QR code, and a budget breakdown table
- [x] Cover page: destination + dates + trip style, with a photo background
      via a new `UnsplashPhotoTool` when `UNSPLASH_ACCESS_KEY` is configured
      (with photographer attribution, per Unsplash's API terms), falling back
      to a clean CSS gradient — and gracefully so, exactly like every other
      external-API tool in this project — when no key is set or the lookup/
      download fails. No Unsplash key was configured yet at the time, so
      both code paths were verified directly (photo present vs. gradient
      fallback) since only the fallback path ran in this environment then —
      a real key was added post-Week-16 (see below), now exercising the
      photo path live too
- [x] Day sections reuse Week 13's `day_color()` so a day's PDF badge and its
      map pins/routes share the same color across both artifacts
- [x] Map section embeds a real Week 13 `render_thumbnail_png()` screenshot
      as a base64 image, plus a QR code (new `qrcode` dependency) linking to
      the interactive map — only rendered when a real URL is supplied, since
      there's no hosted map until Week 15's FastAPI backend exists
- [x] Budget table renders Week 8's `BudgetEvaluation` (category/allocated/
      actual/status, color-coded, plus adherence score and upgrade/cut
      suggestions) when available, falling back to just the estimated total
      when no budget was stated
- [x] Wired into the LangGraph as a new `generate_pdf` step (after
      `generate_map`, before `human_review`); `PlanningState` gained a
      `pdf_path` field. Thumbnail rasterization failure is non-fatal — the
      PDF still generates without the embedded map image, the same
      graceful-degradation pattern used everywhere else in this project
- [x] Live-tested via `scripts/pdf_generation_test.py` across 10 real
      itineraries spanning the full trip-length range the plan calls for
      (2 to 14 days, across 5 cities) — every PDF validated with `pypdf`
      (opens correctly, has the expected page count, extracted text contains
      the destination and every day header). Visually spot-checked the
      2-day and 14-day extremes: page-break rules (`page-break-inside:
      avoid` per section) held up correctly even at 14 days/5 pages, with
      day badges correctly cycling through the full 10-color palette
- [x] 33 new tests (`PDFGenerator` sections/cover/budget/map/QR via both
      HTML-fragment assertions and real `pypdf` content extraction,
      `UnsplashPhotoTool`'s success/failure/caching paths, and the new
      `generate_pdf` node); 453 total passing, 98% coverage

**Phase 4, Week 15 — FastAPI Backend & WebSocket Streaming** — done

- [x] `POST /plan` starts a planning run in the background and returns
      immediately (202); `GET /plan/{session_id}` polls status and results;
      `POST /plan/{session_id}/resume` continues a run paused at Week 6's
      human-in-the-loop conflict review; `GET /export/{session_id}/pdf` and
      `/map` serve Week 14/13's generated artifacts. Full OpenAPI docs at
      `/docs`, auto-generated by FastAPI
- [x] `POST /refine` starts a **new** session seeded from the parent's
      preferences merged with a re-parsed refinement request, rather than
      editing the original session in place — sidesteps a real LangGraph
      gotcha found while building this: `completed_steps` uses an additive
      (`operator.add`) reducer, so feeding a shorter list into an *existing*
      thread_id concatenates rather than resets it, silently leaving the
      supervisor thinking old steps are still done. A fresh thread_id has no
      accumulated state to fight with. This is a full re-plan for now, not
      Week 21's smarter incremental refinement — correct infrastructure for
      that to build on
- [x] `WS /ws/{session_id}` streams step-progress events plus a genuine
      token-by-token LLM narration once the itinerary is built, via a new
      `ItineraryNarrator` (reuses Week 12's `render_itinerary_summary`) —
      verified live against a real running server with a real WebSocket
      client and real GPT-4o output, not just in-process tests
- [x] Session metadata (status + a replayable event log, so a client that
      connects to the WebSocket mid-run or after completion sees everything
      it missed) is tracked in a new SQLite-backed `SessionStore` — the
      plan calls for PostgreSQL, but there's no Postgres instance in this
      project yet (Docker Compose arrives in Week 18), so this is the same
      kind of documented substitution as TravelPayouts for Amadeus (Week 2).
      The actual planning *state* itself continues to live in Week 4's
      LangGraph checkpointer, unchanged
- [x] API key validation (`X-API-Key` header, disabled by default until
      `API_KEY` is set) and rate limiting (`slowapi`, 10/min on `/plan` and
      `/refine`) as real middleware, not just documentation
- [x] Found and fixed a real upstream bug while building this: LangGraph's
      async `.astream()` requires an async-compatible checkpointer, and the
      current `langgraph-checkpoint-sqlite` release's `AsyncSqliteSaver`
      calls `conn.is_alive()`, a method newer `aiosqlite` releases removed.
      Rather than chase that (or force a risky langgraph major-version
      bump), background runs use the existing, already-tested sync
      `graph.stream()` inside a single `asyncio.to_thread` call instead —
      simpler, and it sidesteps a second real bug found in the process:
      polling `graph.get_state()` from the event loop *while* a background
      thread wrote to the same raw sqlite3 checkpointer connection
      reliably hung (SQLite doesn't support true concurrent access even
      with `check_same_thread=False`)
- [x] Live-tested against a real running `uvicorn` server (not just
      `TestClient`): `POST /plan` with a real natural-language request,
      polled to completion, downloaded the real generated PDF and map HTML,
      and streamed a real WebSocket connection showing real step-progress
      events followed by genuine token-by-token GPT-4o narration
- [x] 48 new tests across `SessionStore`, `ItineraryNarrator`, and a new
      `tests/api/` suite (plan/resume/refine/export/websocket/middleware,
      using the same stub-tool pattern as `test_planning_graph.py`); 501
      total passing, 98% coverage
- [x] **Known issue, investigated at length, not fully resolved:** running
      the API test suite (~40 tests, each spinning up its own TestClient
      portal — a background thread + event loop + executor — to drive a
      full graph run) segfaults the whole pytest process roughly 1 run in
      5-8. Confirmed this is *not* either of the two real bugs the
      investigation caught and fixed along the way (an un-stubbed
      `TravelTimeEstimator` making real Redis/Google Maps calls during
      tests, and dangling background tasks still mid-write when a test's
      portal tore down — both fixed and worth keeping regardless). Also
      confirmed it isn't the Python 3.11.0 interpreter release specifically
      (upgraded to 3.11.14, latest patch, still occurs). Crash sites vary
      randomly across unrelated native code (redis-py, sqlite3, WeasyPrint)
      between runs — a classic sign of memory corruption from heavy,
      artificial thread-pool churn rather than a bug in one library. The
      real server, driven by an actual `uvicorn` process handling real
      HTTP/WebSocket traffic, showed no such issue under repeated exercise.
      Documented in `tests/api/conftest.py` for whoever picks this up next

**Phase 4, Week 16 — React Chat UI** — done

- [x] React 18 + TypeScript + Vite + Tailwind CSS 4 frontend (`frontend/`),
      talking to Week 15's FastAPI backend over both REST and the `/ws`
      WebSocket — no server-side changes needed except adding `CORSMiddleware`
      (a new browser origin the backend didn't need to handle before)
- [x] Streaming chat UI: user/assistant message bubbles, a live step-progress
      checklist (all 11 planning steps, ticked off in real time as
      `step_completed` WS events arrive, with the current step pulsing) as
      the "agent thinking" visualization the plan calls for, and a
      three-dot typing indicator while waiting for the first narration token
- [x] Real token-by-token narration rendering: Week 15's `narration_token`
      WS events are folded into one growing string and streamed into an
      assistant bubble as they arrive, not rendered only once complete
- [x] PDF download and "full interactive map" buttons `fetch()` the
      authenticated `/export` endpoints and hand the browser a `blob:` URL,
      rather than linking straight to the API URL — a plain `<a href>` or
      `<iframe src>` can't attach the `X-API-Key` header those endpoints
      require once one is configured
- [x] Refinement chips (`Less walking`, `Upgrade the hotel`, `Add a museum`,
      ...) and free-text refinement both call `POST /refine`, switching the
      whole input into "refine this trip" mode once an itinerary exists;
      "New trip" resets back to planning from scratch
- [x] Human-in-the-loop UI for Week 6's conflict-review pause: shows the
      unresolved conflicts with Approve/Reject buttons, calling
      `POST /plan/{id}/resume` — reconnecting the WebSocket afterward needed
      an explicit `epoch` counter in the reconnect hook, since Week 15's
      backend closes the socket on `awaiting_review` and reusing the same
      `session_id` for `resume()` doesn't change React's dependency array,
      so nothing would otherwise trigger a fresh connection
- [x] Mobile-responsive (verified at a 390px viewport, not just assumed) —
      the chat and the itinerary canvas are two full panes side by side on
      desktop, and a bottom Chat/Itinerary toggle switches between them on
      narrow screens rather than stacking both into one long scroll — dark
      mode (class-based, system-preference default, persisted, toggle in
      the header), and keyboard shortcuts (Enter to send/Shift+Enter for a
      newline, Ctrl/Cmd+K to focus the input from anywhere)

**Visual design pass** (same week, after reviewing reference mockups): rebuilt
the UI around a tabbed-canvas layout — a fixed chat rail plus a right-hand
canvas with **Itinerary / Map / Budget / PDF preview** tabs — replacing the
original single-column chat-with-inline-itinerary-card design.

- [x] Warm paper background + near-black ink + a single green accent
      reserved for actions (day-to-day color-coding lives entirely in the
      day ramp below, not in UI chrome) — `Instrument Sans` for prose,
      `IBM Plex Mono` for anything measured (times, costs, stats), both
      self-hosted via `@fontsource` rather than a runtime Google Fonts
      dependency
- [x] Day color changed from a 10-color categorical palette to a sequential
      **blue → amber ramp** (HSL-interpolated, 10 stops) so a trip's color
      progression reads naturally day-to-day. Changed in both places that
      define it — `travel_map_generator.py`'s `DAY_COLORS` (backend: Folium
      map + PDF day badges) and `dayColors.ts` (frontend: live map preview)
      — kept hand-in-sync exactly as before, so the live map, the exported
      Folium map, and the PDF still all agree on what color means "Day N"
- [x] Found in the process and fixed for real: Folium's `Icon` marker only
      accepts a small fixed set of named colors, not arbitrary hex, so it
      can't represent a smooth ramp. Switched the backend map's markers from
      `Marker` + `Icon` (pins) to `CircleMarker` (dots) — which does accept
      any hex color and is what the React frontend's live map already used,
      so both now render identically, not just approximately
- [x] New `ItineraryPanel`/`DayCard` components: a real weather banner
      (surfaces the first day with an actual Week 7 weather warning, not an
      invented summary), day cards with the day's real cost/stop count, and
      genuine walking-distance/time estimates between consecutive stops
      (haversine great-circle distance, honestly labeled as an estimate —
      the backend's real driving/transit routing isn't re-exposed client
      side). Weather conditions shown as terse METAR-style codes (CLR, OVC,
      RAIN) condensed from OpenWeatherMap's real `condition` field
- [x] New `RunSummary` badges replace an earlier draft's "N tool calls"-style
      framing with only numbers the app actually has: day count, budget
      adherence, conflicts resolved, must-see coverage. Conflicts-resolved
      needed one new backend field — `conflict_log` added to
      `SessionStateResponse`, exposing Week 6's existing `ResolutionLogEntry`
      trail (previously computed but never sent over the API)
- [x] New `PdfPreview` tab: fetches the same authenticated PDF blob the
      download button uses and renders it in an `<iframe>` — browsers render
      PDFs natively, so this needed no new PDF-to-image pipeline
- [x] 64 frontend tests total (up from 33 — new tests for `Header`, `Tabs`,
      `DayCard`, `WeatherBanner`, `BudgetPanel`, `RunSummary`, `PdfPreview`,
      plus `geo.ts`/`weatherCode.ts` utilities; `ItineraryCard`'s old tests
      were retired along with the component itself), plus 2 new backend CORS
      tests and 2 new `conflict_log` assertions on existing endpoint tests;
      503 backend tests + 64 frontend tests passing
- [x] Live-tested end-to-end in a real headless browser against the real
      running `uvicorn` server, twice — once for the original layout, again
      after the visual redesign: typed a real trip request, watched the step
      checklist complete live, real GPT-4o narration stream in, a real
      itinerary render across all four tabs (day cards with real walking
      estimates, a working Leaflet map, a real budget table, and the actual
      generated PDF rendering inline), confirmed dark mode and the mobile
      chat/canvas toggle at a 390px viewport, and confirmed **zero console
      errors and zero failed network requests** throughout both passes

**Post-Week-16 — Per-attraction PDF photos** (MakeMyTrip-style visual
itinerary): Week 14's PDF only ever showed one destination-level cover photo.
Generalized the same `UnsplashPhotoTool` to fetch a real photo per attraction
too — an actual Eiffel Tower photo next to an "Eiffel Tower" row, not just a
generic Paris photo on the cover.

- [x] New `UnsplashPhotoTool.get_photo(query, thumbnail=False)` — a
      general-purpose lookup for any search string, with a separate cache
      entry per (query, size) pair. `get_cover_photo(destination)` is now a
      thin wrapper (`get_photo(f"{destination} travel landmark")`) so Week
      14's cover-photo behavior and caching are unchanged
- [x] `PDFGenerator` fetches a small `thumbnail=True` Unsplash photo for
      every `activity_type == "attraction"` item, keyed on `"{title}
      {destination}"` (e.g. "Eiffel Tower Paris") for precision, and embeds
      it as a base64 thumbnail next to that day's row — restaurants, hotel,
      and transfer rows are intentionally skipped to keep the extra API
      calls bounded. Same graceful no-key/no-result/download-failure
      fallback as the cover photo: a row simply renders without a thumbnail
      rather than breaking the PDF
- [x] Found and fixed a real bug while wiring this up:
      `UnsplashPhotoTool.__init__` did `access_key or settings.unsplash_access_key`,
      so an explicitly-passed empty string silently fell back to the global
      configured key instead of meaning "no key" — harmless while no key was
      configured, but broke the "no key configured" test the moment a real
      `UNSPLASH_ACCESS_KEY` was added to `.env`. Fixed with an explicit
      `is not None` check
- [x] 9 new tests (5 for `get_photo`'s query/size/caching behavior, 4 for
      attraction-row thumbnails: present when available, absent without a
      key, never rendered for non-attraction rows, and the exact query sent)
      bringing backend tests to 512
- [x] Live-tested against the real Unsplash API with a 2-day Paris
      itinerary (Eiffel Tower, Louvre Museum, Notre-Dame Cathedral, Arc de
      Triomphe as attractions, a restaurant thrown in): rendered the PDF,
      extracted the embedded images with `pypdf`, and visually confirmed
      each thumbnail is a real, correctly-matched photo of that exact
      landmark — the restaurant row correctly has no thumbnail

**Post-Week-16 — Full-width canvas fix, web UI photos, and attraction
history** (same enhancement pass, follow-up to the above): the itinerary
canvas wasn't actually filling wide screens, and attraction photos/history
only existed in the PDF, not the live chat UI.

- [x] Fixed a real CSS bug: `Tabs.tsx`'s root div was `flex h-full flex-col`
      with no `w-full`/`flex-1` — as a flex item inside the canvas's
      row-flex container, it shrank to fit its content (the day-card table)
      instead of filling available width, leaving a large blank strip on
      wide screens. One-line fix (`w-full min-w-0` added); verified at
      1920×1080 that the tab bar now spans the full 1500px canvas width
      (window width minus the 420px chat rail), not just its content width
- [x] New `enrich_attractions` LangGraph step (between `build_itinerary` and
      `check_conflicts`): for every `activity_type == "attraction"` item,
      fetches a photo (`UnsplashPhotoTool.get_photo`) and a 2-3 sentence
      history/why-visit blurb, writing `photo_url`/`description` onto the
      `ItineraryItem` itself — so both the web UI and the PDF read the same
      enriched data instead of each fetching independently. `PDFGenerator`
      now reuses `item.photo_url` when already set, only falling back to
      its own lookup for a standalone `PDFGenerator` call (e.g. tests)
- [x] New `AttractionDescriberTool`: one batched GPT-4o structured-output
      call per itinerary (not one call per attraction) returns `{title:
      description}` for every attraction, keeping LLM cost/latency bounded
      regardless of trip length. Cached per (title, destination) pair with
      a 30-day TTL — a landmark's history doesn't change. Same graceful
      degradation as every other optional enrichment in this project: an
      LLM failure just means no descriptions that run, never a blocked plan
- [x] `ItineraryPanel`/`DayCard` now render the photo thumbnail and history
      blurb under each attraction's title, the same MakeMyTrip-style layout
      as the PDF, adapted to the app's existing type/color tokens
- [x] Found and fixed a real, previously-latent bug while testing this:
      LangGraph's default `recursion_limit` (25) counts each worker-step ->
      supervisor round trip as 2 ticks. With 11 worker steps this totaled
      23 - safely under the limit; adding `enrich_attractions` as a 12th
      step pushed a full successful run to exactly 25, tipping over into
      `GraphRecursionError`. This wasn't a test-only issue - the production
      FastAPI backend used the same unset default. Fixed by setting an
      explicit, generous `recursion_limit: 100` everywhere the graph is
      configured (`api/app.py`'s `_config()`, plus the integration/API test
      suites' own graph configs)
- [x] Found and fixed a second real issue while testing: the offline
      integration/API test suites stub every external tool *except* the
      photo/description tools, which previously no-op'd safely only because
      `UNSPLASH_ACCESS_KEY` happened to be blank. Adding a real key would
      have silently made these "offline" suites hit the live Unsplash and
      OpenAI APIs on every run. Added `StubPhotoTool`/`StubDescriptionTool`
      no-ops to both suites' graph-building helpers, restoring true
      offline-ness regardless of what's configured in `.env`
- [x] 21 new backend tests (6 for `make_enrich_attractions_node`, 11 for
      `AttractionDescriberTool`, 4 more `PDFGenerator` cases for
      `photo_url` reuse and description rendering) plus 3 frontend tests
      (`DayCard` photo/description rendering) bringing the total to 533
      backend + 67 frontend tests passing
- [x] Live-tested end-to-end in a real headless browser at 1920×1080
      against the real running `uvicorn` server: submitted "5 days in
      Paris... I love art and museums", confirmed the tab bar now spans the
      full canvas width, and confirmed real photos + accurate history blurbs
      for Musée d'Orsay, Notre-Dame Cathedral, the Eiffel Tower, and the Arc
      de Triomphe in both the Itinerary tab and the generated PDF, with zero
      console errors and zero failed network requests

**Post-Week-16 — Real `/refine` crash found via live use** (same day, found
by actually clicking a refinement chip against a real running server): a
refinement like the **"More outdoor activities"** chip on a London trip
either 500'd with "Load failed" in the UI, or — worse — silently replanned
the *entire* trip around "outdoor activities" as if it were the
destination (real hotels/attractions searches for a place called "outdoor
activities", landing on nonsense results).

- [x] Root cause: `POST /refine` called the same `PreferenceParser.parse()`
      used for a brand-new `/plan` request, which requires a destination.
      A refinement chip's text has no destination in it at all, and the
      parser's own system prompt correctly forbids inventing one — so the
      LLM's structured-output call itself failed pydantic validation
      (`destination` was a required field), an unhandled exception that
      escaped `/refine` as a bare 500. On the runs where the LLM filled
      `destination` in anyway rather than the call failing, the merge logic
      then let that guess silently overwrite the parent session's real
      destination
- [x] Fix: added `PreferenceParser.parse_partial()` — same LLM call, but
      `_ParsedFields.destination` is now optional and `parse_partial()`
      returns a raw field dict (no destination requirement) for `/refine`
      to overlay onto the existing session's preferences, instead of
      building a complete `TravelPreferences` that demands one. `parse()`
      (still used by `/plan`) now explicitly raises `ValueError` when the
      LLM can't determine a destination, rather than leaning on pydantic's
      validation error as the enforcement mechanism
- [x] Also fixed while in there: `interests`/`must_see`/
      `dietary_restrictions`/`accessibility_needs` used to be fully
      *replaced* by whatever the refinement's own (partial) parse
      contained, so "more outdoor activities" would have silently dropped
      an original "art and museums" interest even once the crash was
      fixed. These four list fields now merge by union (order-preserving,
      deduped) instead of replace
- [x] 7 new backend tests (5 in `test_preference_parser.py` for the
      optional-destination/`parse_partial` behavior, 2 new regression
      tests in `test_refine_endpoint.py` reproducing the exact no-crash and
      interests-preserved scenarios, plus stub-parser updates); 540 backend
      tests passing
- [x] Live-reproduced the exact bug end-to-end against the real running
      server first (5 days in London -> click "More outdoor activities"),
      confirmed the crash, then reproduced the same flow again after the
      fix: no "Load failed", the refined trip stayed correctly in London
      (The National Gallery, St. Paul's Cathedral, Tower Bridge), and zero
      console errors or failed network requests throughout

## Setup

```bash
cp .env.example .env                     # fill in your API keys
make install
make test

cp frontend/.env.example frontend/.env   # defaults work for local dev as-is
make frontend-install
```

Run the backend and frontend in two terminals:

```bash
make serve            # FastAPI on :8000
make frontend-dev     # Vite dev server on :5173
```

## Project layout

```
src/travel_agent/
  config.py          # env-based settings
  models/core.py      # shared Pydantic domain models
  tools/               # one module per agent tool (PreferenceParser, FlightSearchTool, ...)
  agents/              # LangGraph agent/graph definitions (added Week 4+)
  api/                 # FastAPI app, schemas, session store (added Week 15)
  utils/
tests/
  unit/
  integration/
  e2e/
  api/                 # FastAPI endpoint/websocket tests (added Week 15)
frontend/               # React 18 + TypeScript + Vite chat UI (added Week 16)
  src/
    components/
    lib/                # API client, WebSocket hook, theme hook
    types/               # hand-written TS mirror of the API's Pydantic schemas
```

## Tech stack

Python 3.11+ (pinned to 3.11.14 via `.python-version`), LangGraph + LangChain, OpenAI GPT-4o,
FastAPI + uvicorn + WebSockets, slowapi, PostgreSQL + Redis, Docker, pytest, Folium, Playwright,
WeasyPrint, qrcode. React 18 + TypeScript + Vite + Tailwind CSS 4 + react-leaflet, Vitest +
Testing Library.
