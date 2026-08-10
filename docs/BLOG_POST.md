# How I Built a Production AI Travel Agent in 24 Weeks

_Draft — Week 23 deliverable. Covers the full build through Week 22; not yet
published externally. For the narrower, evaluation-specific post written a
week earlier, see [`BLOG_POST_DRAFT.md`](BLOG_POST_DRAFT.md)._

Travel planning is a research project disguised as a vacation. You open
fifteen tabs, cross-reference flight prices against hotel locations against
which neighborhoods actually have the restaurants you want, discover your
museum closes on the one day you're free, and three hours later you have a
spreadsheet, not a plan. I spent 23 weeks building an agent that does that
work autonomously — real flights, real hotels, real attractions and
restaurants, a route-optimized day-by-day schedule that's weather-aware and
budget-constrained, delivered as an interactive map and a polished PDF, with
a chat interface you can actually refine ("make it more relaxing," "add a
museum") without starting over.

This is the story of building it, not just a features list — what the
architecture actually looks like, which decisions turned out to matter, and
which bugs took longest to find and taught the most.

## The shape of the problem

An LLM alone can *describe* a plausible-sounding Paris itinerary. It cannot
tell you a real flight exists at that price, that the museum is open on
Tuesday, or that the hotel you'd like is 40 minutes from three of your five
scheduled attractions. The interesting engineering here isn't the language
model — it's everything around it: eight external APIs with their own
rate limits and quirks, a scheduling problem that's NP-hard in the general
case, and a genuine need for the system to keep working when any one of
those eight APIs is unavailable, which — as it turned out — is most of the
time.

## Architecture: a supervisor, not a script

The system is a LangGraph `StateGraph`: a typed state object threaded
through a loop where a supervisor node decides what runs next and worker
nodes do the work, each catching its own failures rather than crashing the
run. I could have written this as a plain Python function calling other
functions in sequence — simpler to read, easier to debug with a stack
trace. I didn't, for a reason that only paid off nine weeks later than I
expected: five of the twelve planning steps (search flights, hotels,
attractions, restaurants, weather) don't depend on each other at all. A
script makes that fact invisible. A graph can express it directly — and in
Week 20, reading LangGraph's own source revealed that its routing functions
can return a *list* of next steps, which its executor runs through a real
thread pool, genuinely concurrently. Five independent, network-bound calls
that used to run one after another, at 10-20 seconds apiece, started
overlapping in a single ~3-second window. That's a 2.92x measured speedup
I got almost for free, nine weeks after making an architecture choice for
an entirely different reason (resumability across a human-in-the-loop
pause, not performance). The full reasoning is written up as
[ADR-0001](adr/0001-langgraph-supervisor-loop.md) and
[ADR-0005](adr/0005-native-fanout-over-asyncio-gather.md).

## Everything fails, so everything falls back

Every external API in this project has failed in some real, observed way:
Booking.com's hotel search has had its free-tier quota exhausted for most
of this project's life; OpenWeatherMap's forecast horizon is five days;
Serper and Google Maps have their own limits. The design response, from
Week 2 onward, was that every tool catches its own transient failures and
falls back to deterministic mock data — tagged so downstream code and the
final PDF can tell real bookable results from a placeholder — rather than
letting one exhausted quota fail an entire planning run.

This pattern is also where two of the project's more instructive bugs came
from, both discovered not because anything crashed, but because "the
fallback returns *a* result" quietly hid that it wasn't returning a
*representative* one. Week 13 found the mock hotel fallback had hardcoded
its coordinates to `(0.0, 0.0)` since Week 2 — silently explaining
recurring "can't compute a route" warnings in live tests for a month before
anyone traced them. Week 22's evaluation found the same fallback priced
every budget tier identically, so a "luxury" trip's mock hotel cost exactly
what a backpacker's did — invisible until an actual evaluation rubric
scored the output and asked "does the spend match the stated budget?" and
the answer, for every luxury scenario, was no.

## Measuring instead of assuming

Week 12 built an evaluation framework — 10 scoring dimensions across 25
real trip scenarios, six computed directly from the itinerary and four
judged by GPT-4o — and got a baseline: 5.52/10, with two clearly
root-caused weak spots. It would have been easy to leave it there as a
one-time snapshot. Week 22 re-ran the exact same rubric across 30 scenarios
(5.51/10 — confirming nine weeks of unrelated work hadn't quietly broken
anything) and then actually fixed what Week 12 had diagnosed and never got
around to.

The more interesting part wasn't the fix — it was getting the fix wrong
first, on purpose using the data rather than the intuition. My first
attempt at tier-aware hotel pricing lowered the backpacker tier's price.
Re-running the evaluation showed every backpacker scenario got *worse*.
Ten minutes of arithmetic explained why: the scoring formula penalizes
underspending exactly as hard as overspending, the cost model only counts
hotel and food (no flight cost in this harness), and every tier was
*already* underspending — lowering the price further just widened a gap
that was never an overspending problem to begin with. I'd made almost this
exact mistake before, in Week 20, calibrating a semantic-cache similarity
threshold against a guess instead of real embeddings. The lesson is
starting to stick: a fix that looks right is a hypothesis, and the only way
to know if it's actually right is to measure it again after shipping it.

## What the rubric couldn't see

Formulas are precise about what they measure and blind to everything else.
Week 22's rubric has ten dimensions and none of them check whether the same
restaurant got scheduled twice. The plan's original ask for this week was
"have five friends or family test the app and collect feedback" — I don't
have five people available to recruit for a solo project, and inventing a
claim that real people tested it would break the one rule I've tried
hardest to keep for 23 weeks: only report what's actually true. So I built
five LLM personas instead — a backpacker, a luxury honeymoon couple, a
family with kids, a solo hiker, a business traveler — had each one drive
the real pipeline with their own natural-language request, and had them
react to the result, explicitly instructed not to be uniformly positive.
It's clearly labeled as simulation everywhere it's reported, not user
research, because an LLM roleplaying "annoyed by overpriced restaurants"
isn't the same signal as an actual annoyed backpacker.

Three of the five personas, independently, flagged a repeated restaurant.
That sent me back into code written in Week 5 and untouched since: the
arrival day's dinner and the very next day's lunch each picked their
restaurant from the same starting index in the list, with no awareness of
each other. Every single itinerary this agent has ever built repeated a
restaurant on day one. A one-line fix, a regression test, and it was gone —
found by five roleplaying personas after 620 real unit tests, an 85%+
coverage requirement, and a 10-dimension automated rubric had all missed
it, because none of them were evaluating the whole experience the way even
a simulated user does.

## From working to production

Weeks 13-19 are the least glamorous and most necessary part of the build:
a real PDF (WeasyPrint rendering an HTML template, not a screenshot), an
interactive Folium/Leaflet map with a day-by-day route-reveal timeline, a
FastAPI backend streaming progress and token-by-token narration over a
WebSocket, a React chat UI, then — because "it works on my laptop" isn't
the same claim as "it works" — a real test suite (600+ tests today, unit
through E2E, plus mutation testing to check the tests themselves aren't
just padding a coverage number), Docker Compose for the whole stack, a
CI/CD pipeline, and structured logging with correlation IDs that follow one
planning run through every layer down to a third-party library's own log
lines. None of this shows up in a demo the way a route-optimized map does.
All of it is why the map can be trusted. The Postgres migration in Week 18
in particular surfaced a genuinely subtle bug — `PostgresSaver`'s
connection-management context manager getting silently garbage-collected
because nothing kept a reference to it, closing the database connection out
from under a checkpointer that looked, on the surface, perfectly
constructed. A mocked-connection unit test would never have caught it;
running against a real local Postgres instance did, immediately.

## What I'd tell someone starting this

Live-test against real APIs, not just mocks — nearly every real bug in
this project (the Null Island coordinates, the tier-blind pricing, the
repeated restaurant, a GC bug that silently closed a Postgres connection)
was found by running the actual system against actual services and looking
at actual output, not by a unit test with a mock that couldn't have known
the mock itself was wrong. Measure before you trust a fix, and measure
again after you change it — a plausible-looking correction is exactly as
likely to be wrong as the thing it's replacing until you check. And build
in the failure modes from day one, not as an afterthought: the reason this
system has never had a demo fail outright because of a rate-limited API is
that graceful degradation was a Week 2 decision, not a Week 20 patch.

Twenty-three weeks in, the numbers are real, the bugs found along the way
are documented rather than smoothed over, and the thing that started as
fifteen browser tabs is now one conversation. That's the part worth being
proud of — not any single score, but that every score is something I could
re-measure tomorrow and trust.

_Full architecture, per-decision rationale, and the complete week-by-week
build log: [`README.md`](../README.md). Methodology and honest limitations
behind every number cited here: [`EVALUATION_REPORT.md`](EVALUATION_REPORT.md)._
