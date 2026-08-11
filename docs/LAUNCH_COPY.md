# Community launch — drafts

Draft copy for the Week 24 plan's "share on LinkedIn/HackerNews/Reddit,
submit to AI showcases" step. Written for you to review and post yourself —
posting to your own accounts isn't something done autonomously here. Swap
in the real demo video link once it's recorded (see `docs/DEMO_SCRIPT.md`).

---

## LinkedIn

> I spent the last several months building an AI agent that actually plans
> real trips — not a chatbot that describes a plausible-sounding itinerary,
> but a system that searches real flights, real hotels, real attractions
> and restaurants, and builds a route-optimized day-by-day schedule that's
> weather-aware and budget-constrained.
>
> A few things I'm proud of:
> → 5 independent search steps run in parallel through a LangGraph
> supervisor — a real 2.92x speedup over running them one at a time
> → A route optimizer (geographic clustering + budget-constrained
> backtracking) cut walking distance 45% against a naive schedule
> → Every one of 8 external APIs degrades gracefully to a clearly-marked
> fallback instead of crashing the run — which, for at least one provider,
> is the normal operating mode, not an edge case
> → 1,000+ tests, real observability (Prometheus/Grafana/Sentry), and
> every feature live-verified against the actual running app before it
> shipped, not just passing in isolation
>
> It's fully open source. Live demo, architecture writeup, and the full
> build log (24 weeks, documented as I went — including what broke and
> what I got wrong) are linked below.
>
> [live site] · [GitHub repo] · [build write-up]

---

## Hacker News (Show HN)

**Title:**
`Show HN: Waypoint – an AI agent that plans real trips (LangGraph, real APIs)`

**First comment (post immediately after submitting, HN convention):**

> Hi HN — built this over the past few months. It's a LangGraph agent that
> takes a plain-English trip request and turns it into a real, bookable
> itinerary: actual flights (TravelPayouts), actual hotels (Booking.com),
> actual attractions/restaurants/weather, scheduled with a route optimizer
> that clusters geographically and respects your stated budget.
>
> A few technical notes that might be interesting to this crowd:
>
> - The 5 search steps (flights/hotels/attractions/restaurants/weather) run
>   in parallel through the supervisor rather than sequentially — measured
>   2.92x speedup end to end.
> - Every external API call is wrapped to fail closed to a mock rather than
>   crash the graph. Booking.com's free RapidAPI tier gets rate-limited
>   often enough in practice that this isn't a rare-edge-case path — it's
>   how the demo usually actually runs, and I document that honestly rather
>   than hiding it.
> - Refinement ("add a museum," "make it cheaper") is incremental — only
>   the search steps whose actual inputs changed re-run, so a budget tweak
>   doesn't re-hit flight search.
> - Multi-destination trips reuse the same single-destination day-building
>   pipeline once per city block rather than a separate code path — traced
>   through the actual clustering/backtracking algorithm before assuming
>   it would "just work" across cities 1000km apart (it wouldn't have).
>
> Full architecture, ADRs, and the week-by-week build log (24 weeks,
> written as I went, including the bugs) are in the README. Happy to answer
> questions about any of it.
>
> [GitHub repo] · [live site]

---

## Reddit

Best fits: **r/SideProject**, **r/LangChain**, **r/webdev** (pick 1-2, not
all three at once — cross-posting the identical text to several subreddits
in a short window reads as spam and often gets removed).

**Title:** `I built an AI agent that plans real trips — real flights, hotels, route optimization, and a PDF export (LangGraph + FastAPI + React)`

**Body:**

> Wanted to share something I've been building solo — an AI travel-planning
> agent that goes further than "describe a plausible itinerary." It
> actually searches real flights and hotels, finds real attractions and
> restaurants, and builds a day-by-day schedule using actual route
> optimization (geographic clustering + budget-constrained backtracking),
> weather-aware, exported as an interactive map and a real PDF.
>
> Stack: LangGraph for orchestration, FastAPI backend, React/TypeScript
> frontend, Postgres + Redis in Docker Compose, real observability
> (Prometheus/Grafana/Sentry).
>
> It's fully open source and I documented the whole build as I went —
> including the bugs, the wrong turns, and the honest limitations (one of
> the hotel APIs runs in fallback mode more often than not on its free
> tier, and I say so directly rather than hiding it).
>
> [live site] · [GitHub repo]
>
> Happy to answer questions about the architecture or anything that looks
> interesting/questionable in the code.

---

## AI project showcases

A few real, well-known places worth checking (submission processes change,
so verify the current one on each site rather than trusting a specific
submission URL here):

- **[There's An AI For That](https://theresanaiforthat.com)** — large,
  well-trafficked AI tool directory; has a public submission form.
- **[Product Hunt](https://www.producthunt.com)** — launch under an
  "Artificial Intelligence" or "Developer Tools" topic; timing (day of
  week, launch hour) matters more here than almost anywhere else on this
  list, worth reading their own guidance before picking a date.
- **Awesome-LangGraph / Awesome-LangChain GitHub lists** — several
  community-curated "awesome" lists exist for LangGraph/LangChain projects;
  search GitHub for the current ones and open a PR adding this repo, same
  as any other open-source contribution.
- **r/LangChain** (Reddit) — doubles as both a community and a showcase;
  covered above.

Don't submit to all of these in the same day — space it out over a couple
of weeks so each one gets its own attention rather than all landing at
once and diluting each other.
