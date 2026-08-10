# ADR-0002: Every external API call degrades to deterministic mock data instead of failing hard

**Status**: Accepted (Week 2), applied consistently through Week 22

## Context

This project integrates 8 external APIs, every one of which is on a free
or sandbox tier with real limits: Booking.com's RapidAPI hotel search has a
monthly quota that has been exhausted for most of this project's runtime
since Week 2 (confirmed still true as of Week 22's evaluation — every
hotel fetched during that week's 60+ scenario runs came from the fallback,
not a live API response); OpenWeatherMap's free tier only forecasts ~5 days
out; Serper, TravelPayouts, and Google Maps all have their own rate limits.
A demo, a test run, or a real user's request can hit any of these at any
time, and "the whole planning run fails because one hotel API is out of
quota" is a bad failure mode for a system whose whole value proposition is
producing a complete itinerary.

## Decision

Every tool that calls an external API (`FlightSearchTool`,
`HotelSearchTool`, `AttractionFinderTool`, `RestaurantFinderTool`,
`WeatherCheckerTool`) catches its own transient failures (timeouts,
connection errors, 429/5xx after retry) and falls back to deterministic
mock data instead of raising — tagged `is_mock_data=True` so callers and
the itinerary's own PDF/UI output can distinguish real bookable data from
a placeholder. The graph-level nodes (Week 4) add a second, coarser safety
net on top: even an unexpected exception in a tool is caught at the node
level and recorded in `state["errors"]` rather than halting the run.

## Consequences

- **Positive**: this project has never had a demo, a live test, or a real
  session fail outright because of an exhausted third-party quota — every
  documented live-test run across 22 weeks completed, degrading gracefully
  when needed. The Week 22 evaluation's 30-scenario runs (with real
  Booking.com quota exhaustion on every single destination) still produced
  complete, scoreable itineraries.
- **Negative, and a real bug this pattern caused twice**: mock data must be
  *good* mock data, or its own flaws become invisible until specifically
  investigated. Week 13 found the mock-hotel fallback had hardcoded
  coordinates to `(0.0, 0.0)` since Week 2 — silently explaining recurring
  "Distance Matrix ZERO_RESULTS" warnings for a full 4 weeks before being
  traced and fixed. Week 22 found the mock-hotel fallback priced every
  `BudgetTier` identically, tanking the evaluation's `budget_accuracy`
  dimension specifically for luxury-tier scenarios — also unfixed for many
  weeks because the fallback "working" (returning *a* hotel) masked that it
  wasn't returning a *representative* one.
- The pattern also shaped how this project evaluates itself: because mock
  fallbacks fire so often in practice, Week 12's evaluation framework and
  Week 22's re-evaluation both had to explicitly account for mock data in
  their methodology and limitations sections rather than assuming live API
  responses.
