# Resume Bullets — Week 23 deliverable

Every number below is real and traceable to a specific week's live-tested
result in the README or a script in `scripts/` — not the plan's own
generic template bullets (`docs/PROJECT_PLAN.md` §8.2), which state
aspirational targets this project didn't always hit exactly (e.g. its
suggested ">90% budget adherence" bullet — this project's real, measured
`budget_accuracy` is lower, and reported honestly as such rather than
rounded up). Where this project's real number differs from the plan's
target, the real one is used.

## Project title & tagline

Autonomous AI Travel Planning Agent | Python, LangGraph, FastAPI, React,
PostgreSQL, Docker | 2026

## Bullet points

- Architected and shipped a production-grade agentic AI system using
  LangGraph `StateGraph`, orchestrating 12 specialized tools across 8 real
  external APIs (OpenAI, TravelPayouts, Booking.com, Google Maps,
  OpenWeatherMap, Serper, Tavily, Unsplash) with per-tool retry, rate-limit
  handling, and deterministic mock-data fallback so no single API outage
  fails a planning run.

- Implemented geospatial route optimization (Nearest Neighbor + 2-opt),
  measuring a **+45% average travel-time efficiency gain** over naive
  random ordering across a 20-scenario benchmark against a real Google
  Distance Matrix — validated with an adversarial regression test proving
  2-opt's asymmetric-distance handling (a real correctness bug in the
  common "boundary-edges-only" 2-opt shortcut, caught before it shipped).

- Redesigned the agent's tool-execution model to run 5 independent search
  tools concurrently via LangGraph's native parallel-superstep support
  (discovered by reading the framework's own source, not a documented
  feature) instead of serializing them — measured a **2.92x wall-clock
  speedup** on a live A/B benchmark, cutting a 46.8s real end-to-end
  planning run's search phase from ~19.7s of summed work to a ~3.35s
  overlapping window.

- Built and iterated on an automated evaluation framework — 10 scoring
  dimensions (6 computed, 4 LLM-as-judge via GPT-4o) across 30 real trip
  scenarios — that caught and quantified 2 real regressions in production
  logic (attraction category data carrying no signal; mock hotel pricing
  ignoring budget tier), each fixed and re-measured with a real
  before/after delta rather than assumed fixed.

- Maintained 98%+ test coverage across 632 backend (unit/integration/API)
  and 70 frontend tests, including Playwright E2E journeys, load testing,
  and mutation testing; shipped a full CI/CD pipeline (GitHub Actions →
  Docker Hub) and an observability stack (Prometheus, Grafana, Sentry,
  LangSmith, structured logging with correlation IDs traced through
  background threads and third-party library logs).

- Developed a React 18 + TypeScript chat UI with WebSocket-streamed
  step-by-step progress and token-by-token LLM narration, an embedded
  Leaflet map, one-click PDF export, and an incremental multi-turn
  refinement flow that re-runs only the search steps an edit actually
  invalidates — skipping redundant external API calls entirely for
  refinements unrelated to destination, dates, or budget.

## Skills demonstrated

| AI/ML | Backend | Frontend | DevOps/Infra |
|---|---|---|---|
| LangGraph, LangChain, OpenAI API, prompt engineering, LLM-as-judge evaluation, semantic caching, agentic system design | Python, FastAPI, PostgreSQL, Redis, WebSockets, async/await, REST API design, Pydantic | React 18, TypeScript, Tailwind CSS, Leaflet.js, WebSocket client, streaming UI | Docker, GitHub Actions, CI/CD, Prometheus, Grafana, Sentry, LangSmith |
