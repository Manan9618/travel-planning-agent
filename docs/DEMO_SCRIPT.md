# Demo video script — Week 24

A ~4 minute, 3-scene narration script for the launch demo video. Each scene
maps to a real, unscripted GIF already captured against the live app (no
mockups, no scripted screenshots) — record screen + voiceover following
this script, using the GIFs as the visual reference for pacing and what's
on screen. Total target: 3:30–4:30.

Style note: say what's real, not what's impressive. Every number below is
this project's own, verified figure (test counts, live-test results,
architecture facts) — no rounding up, no aspirational claims.

---

## Cold open (0:00–0:15) — no visuals yet, just the hook

> Planning a trip is a research project disguised as a vacation. You open
> fifteen tabs, cross-reference flight prices against hotel locations
> against which neighborhoods actually have the restaurants you want, and
> three hours later you have a spreadsheet, not a plan.
>
> This is Waypoint — an AI agent that does that research for you, with
> real flights, real hotels, and a route that actually makes geographic
> sense.

---

## Scene 1 (0:15–1:45) — core planning, end to end

_Visual: `docs/assets/demo.gif` — a single-destination request from typed
text to finished itinerary._

> You describe a trip in plain English — destination, dates, a budget,
> what you're into. Behind the scenes that's a LangGraph agent: five
> independent search steps — flights, hotels, attractions, restaurants,
> weather — run in parallel, not one after another. That's not a minor
> detail; measured end to end, it's a real 2.9x speedup over running them
> sequentially.
>
> [Point to the step-progress checklist ticking off items]
>
> Once the searches land, a route optimizer clusters attractions
> geographically and schedules them day by day — DBSCAN clustering plus a
> budget-constrained backtracking search, not just "here are ten things to
> do." That routing work alone cut walking distance by 45% in this
> project's own benchmarks against a naive nearest-neighbor schedule.
>
> [Show the finished itinerary — day cards, real photos, weather-aware
> packing notes]
>
> The result comes with an interactive map, a real GPT-4o narration of the
> plan you can read as it streams in, and — if you don't like something —
> you just ask for a change in the chat. "Add a museum," "make it
> cheaper." Only the parts of the plan that actually depend on what
> changed get re-planned; a budget tweak doesn't re-run flight search.
>
> [Switch to the PDF tab]
>
> And it exports as an actual polished PDF — cover photo, day-by-day
> breakdown, a real budget table, QR code to the live map. Not a text
> dump.

---

## Scene 2 (1:45–2:55) — multi-destination + real currency conversion

_Visual: `docs/assets/demo-multidestination.gif` — "5 days split between
Paris and Rome... under 3000 EUR"._

> Trips aren't always one city. Ask for something split across two
> destinations and the same day-by-day pipeline runs once per city block
> — Paris gets its own days, Rome gets its own days, with the flight in
> and out and one shared itinerary tying them together. No city bleed
> across days; day 2 is entirely Paris, day 3 is entirely Rome.
>
> [Point at the budget panel]
>
> And the budget doesn't have to be in dollars. State it in euros, and
> every figure you see — allocated, actual, the whole comparison — is
> shown in euros too, converted through a real live exchange-rate lookup,
> not silently treated as if €3,000 meant $3,000.
>
> [Show the PDF cover reading "Paris & Rome"]

---

## Scene 3 (2:55–3:45) — accounts and sharing

_Visual: `docs/assets/demo-sharing.gif` — register, plan, share, and open
the link logged out._

> Real accounts — email and password, or one click with Google. Every
> trip you plan is saved to your dashboard, and you can pick up right
> where you left off.
>
> [Click Share, then log out]
>
> Want someone else to see a trip without giving them an account? One
> click generates a share link. Log all the way out —
>
> [Open the link in what's clearly a fresh, logged-out view]
>
> — and the link still works. Full itinerary, real map, PDF download,
> zero login required. That's the whole point of a share link: it has to
> work for someone who has nothing but the URL.

---

## Close (3:45–4:15)

> Waypoint is fully open source — FastAPI backend, React frontend,
> LangGraph orchestration, deployed with Docker Compose, Prometheus and
> Grafana wired in for real observability. [X hundred] tests, real live
> verification at every step, no mocked demo data pretending to be a real
> run.
>
> Link's in the description. Go plan something.

---

## Recording notes

- Use the 960×600 window size the GIFs were captured at, or re-record
  fresh footage at that pacing if a higher-resolution capture is wanted —
  the GIFs are the pacing/beat reference either way.
- The "[X hundred] tests" line in the close should be filled in with
  whatever the real combined backend+frontend test count is at recording
  time (see the README's own running total in the Status section) —
  deliberately left as a placeholder here rather than hardcoded, since
  it'll be stale by the time this is actually recorded.
- Every claim in this script traces back to something in the README's
  Status log or `docs/EVALUATION_REPORT.md` — if a number here and the
  README ever disagree, the README is correct and this script is stale.
