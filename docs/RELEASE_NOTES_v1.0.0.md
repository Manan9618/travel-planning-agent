# Waypoint v1.0.0

The first tagged release — the full 24-week build plan plus everything added
after it on request. Live site: https://manan9618.github.io/travel-planning-agent/

## What it does

Turns a natural-language travel request into a complete, optimized
day-by-day itinerary: real flights, hotels, attractions, restaurants, and
weather searched in parallel, a route-optimized schedule that's
weather-aware and budget-constrained, an interactive map, a polished PDF,
and a chat interface you can refine in plain English without starting over.

## Highlights

- **LangGraph agent, not a script** — a supervisor node fans out to 5
  independent search steps in parallel (a real **2.92x speedup** over
  sequential execution) and every worker node catches its own failures
  rather than crashing the run.
- **Real optimization, not a list** — DBSCAN geographic clustering plus a
  budget-constrained backtracking search cut walking distance **45%**
  against a naive nearest-neighbor baseline.
- **Graceful degradation everywhere** — all 8 external APIs (flights,
  hotels, maps, weather, search, photos) fail closed to a clearly-marked
  mock rather than crashing; this is the normal operating mode for at
  least one provider (Booking.com's free tier), not a rare edge case.
- **Real accounts** — email/password or one-click Google sign-in, JWT
  bearer auth, a dashboard of saved trips, forgot-password, and public
  share links that work with zero login on the receiving end.
- **Multi-destination trips** with correct per-city day blocking, and
  **real currency conversion** — state a budget in any currency and every
  figure you see is converted and displayed in it, not silently treated
  as USD.
- **A PDF worth printing** — real cover photo, per-attraction and
  per-restaurant photos, a hotel section, a real budget table, and a QR
  code to the live interactive map.
- **Real observability** — structured JSON logs, Prometheus metrics,
  Grafana dashboards, Sentry error tracking, cost-per-run tracking for the
  LLM calls.
- **1,003 tests** (859 backend, 144 frontend), 98%+ backend coverage on
  the algorithm-dense modules, a Playwright E2E suite, load testing, and
  mutation testing on the modules where a surviving mutant would actually
  indicate a real test-quality gap.
- Every feature in this release was **live-verified against the real
  running app with real APIs** at the point it shipped — not just unit
  tests passing in isolation.

## Timeline

**Weeks 1–14 — core agent** (foundation, tool layer, LangGraph
orchestration, conflict resolution, weather-aware scheduling, budget
optimization, geospatial clustering, route optimization, the multi-day
optimizer, an evaluation framework, interactive maps, and the first PDF
generator).

**Weeks 15–17 — productionization** (FastAPI + WebSocket backend, a React
chat UI, a full Playwright E2E suite, load testing, mutation testing).

**Weeks 18–20 — infra & performance** (Docker Compose + Postgres + CI/CD,
structured logging + Prometheus + Grafana + Sentry, parallel search
execution + semantic caching).

**Weeks 21–23 — polish** (incremental multi-turn refinement, a full
evaluation pass with before/after data and a simulated user study,
architecture diagrams + ADRs + enriched OpenAPI docs + a technical blog
post + a real demo GIF).

**Post-plan** (added on request, same engineering bar as every numbered
week): real user accounts + a redesigned PDF; a landing page + trip-history
dashboard; delete-trip, currency conversion, calendar export,
forgot-password, share links, and multi-destination trips, all in one
batch; a second PDF visual pass (colored backgrounds, more photos, a hotel
section); "Continue with Google" OAuth sign-in.

**Week 24 — this release** (demo video script + 2 new real demo GIFs, this
GitHub Pages landing page, final code review, this tag).

## Links

- [README](https://github.com/Manan9618/travel-planning-agent#readme) —
  full architecture and the complete week-by-week build log
- [Build write-up](https://github.com/Manan9618/travel-planning-agent/blob/main/docs/BLOG_POST.md)
- [Evaluation report](https://github.com/Manan9618/travel-planning-agent/blob/main/docs/EVALUATION_REPORT.md)
- [Architecture Decision Records](https://github.com/Manan9618/travel-planning-agent/tree/main/docs/adr)
- [The original 24-week plan](https://github.com/Manan9618/travel-planning-agent/blob/main/docs/PROJECT_PLAN.md)

## Known limitations

Documented honestly rather than glossed over — see the README's Status
section for full detail on each:

- Booking.com's free-tier RapidAPI quota is exhausted more often than not
  in practice, so hotel search runs in mock-fallback mode most of the
  time — by design, not a bug, but worth knowing before a live demo.
- Currency conversion covers the primary budget-display path and flight
  search's `max_price` filter; a couple of deeper internal comparisons
  (Week 6's conflict-detection trigger, the multi-day optimizer's per-day
  activity budget) still compare against the raw stated figure.
- A multi-destination trip's hotel stays singular (the primary
  destination's hotel only) — a deliberate scope decision, not an
  oversight.
