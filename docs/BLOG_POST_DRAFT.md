# Building a Production AI Travel Agent: What 22 Weeks of Honest Measurement Taught Me

_Draft — Week 22 deliverable. Not yet published externally._

Twenty-two weeks ago I set out to build an autonomous AI travel planning
agent — a LangGraph-orchestrated system that takes "5 days in Paris under
$3000" and turns it into a real, bookable, day-by-day itinerary with flights,
hotels, attractions, restaurants, a PDF, and an interactive map. This week
was the checkpoint the whole plan had been building toward: run a real
evaluation, compare it honestly against where the project started, fix what
the data says is actually broken, and write down what I found — including
the parts that didn't go the way I expected.

## The number that mattered least

Week 12 first measured this agent's output quality across 25 real trip
scenarios, using a 10-dimension rubric — 6 dimensions computed directly from
the itinerary (does it avoid conflicts, does it stay near budget, is the
route efficient) and 4 judged by GPT-4o (does it fit what the traveler
asked for, does it read well, is the pacing sane, would a traveler be
happy). The average score was 5.52/10.

This week I extended that to 30 scenarios — including the two trip styles
the original plan named but the evaluation had never actually exercised,
`business` and `road_trip` — and re-ran the exact same rubric, unchanged,
against the system as nine weeks of unrelated work (Docker, observability,
performance optimization, incremental refinement) had left it. **5.51/10.**
Almost identical to Week 12. That's not a failure — it's confirmation that
nothing quietly regressed across nine weeks of changes that had nothing to
do with itinerary quality. It also meant the two problems Week 12 diagnosed
and never got around to fixing were still exactly where they'd been left.

## The two bugs that were always going to be there

Week 12's own analysis had already named the root causes of the two
lowest-scoring dimensions:

**`variety` scored 2.5/10** — not because the itineraries this agent builds
actually lack variety, but because the attraction-search API returns the
generic label `"Tourist attraction"` for nearly everything, and the variety
score is literally "how many distinct categories are scheduled." The data
was blind, not the itinerary.

**`budget_accuracy` scored 3.9/10** — and the three worst-scoring scenarios
in that baseline were all luxury-tier honeymoons. The hotel search's
mock-data fallback (which fires constantly — the free-tier hotel API's
quota has been exhausted since Week 2) priced every mock hotel identically
regardless of whether the trip was backpacker or luxury tier.

Both fixes were conceptually simple. Neither shipped cleanly on the first
try, and that's the more interesting part of this week.

## The fix that made things worse (on purpose, then measurably not)

For the budget fix, my first instinct was a three-tier price table:
backpacker cheaper, mid-range unchanged, luxury more expensive. I shipped
it, re-ran the evaluation, and looked at the numbers before writing anything
down — a habit this project has needed more than once. Luxury scores
improved, as expected. **Every single backpacker scenario got worse.**

The reason took ten minutes of arithmetic, not guessing: the adherence
score penalizes underspending exactly as much as overspending, and this
evaluation's cost model only counts hotel and food — no flight cost, since
the harness never calls the flight tool, and attractions almost never carry
price data. Every tier was already *underspending* at the original flat
price. Lowering backpacker's price further didn't fix an overspending
problem that didn't exist; it just widened an underspending gap that did.
I put the backpacker and mid-range prices back to the original value,
raised only luxury — by more than my first guess, reverse-engineered from
the actual spend deltas the first attempt produced — and re-ran again.
This time every tier moved in the right direction.

I'd made almost exactly this mistake before, in Week 20, calibrating a
semantic-cache similarity threshold against real embeddings instead of
intuition. The lesson didn't fully stick the first time. It might stick
now: **a plausible-looking fix is a hypothesis, not a result, until you
re-measure it.**

## The bug my own fix introduced, and how a five-minute check caught it

While building the variety fix — a keyword classifier that turns
"Tower Bridge" into "Landmark & Viewpoint" instead of the generic
"Tourist attraction" — I gave zoos and aquariums one combined category:
"Zoo, Aquarium & Wildlife." It read fine. It was also a bug.

A separate module, written back in Week 7, derives whether an attraction is
"indoor" or "outdoor" from a keyword search over the same category-plus-name
text, to decide whether to schedule it on a good-weather or bad-weather day.
"Aquarium" is one of its indoor keywords. "Zoo" is one of its outdoor
keywords. My combined label put both words into the text for *every zoo*,
and the indoor check runs first — meaning every genuinely outdoor zoo this
agent might ever schedule would have been silently reclassified as indoor.

Nothing in the test suite would have caught this; the two modules had never
been reasoned about together before. I only found it because deriving a new
category label felt like exactly the kind of change that's worth checking
against every OTHER piece of code reading that same field — not because a
test failed. I split the category into two, wrote a test that checks no
future category label can ever contain both an indoor and an outdoor
keyword, and moved on. It's a small thing. It's also the kind of bug that
survives in production for months because nothing ever crashes.

## What the AI personas actually caught

The original plan called for five friends or family members to use the app
and give feedback. I don't have five friends and family members available
to recruit for a solo capstone project, and inventing a claim that real
people tested it would contradict the one rule I've tried hardest to keep
throughout this whole project: only report what's actually true.

So I built five LLM personas instead — a broke backpacker, a luxury
honeymoon couple, a parent planning around two kids, a solo hiker chasing
the northern lights, a time-pressed business traveler — and had each of
them drive the *real* pipeline (real NLU parsing of their own natural-
language request, real API calls, real optimizer) before giving first-
person, explicitly-not-uniformly-positive feedback on the result. I want to
be clear about what this is and isn't: it's not user research, and an LLM
roleplaying "annoyed by anything overpriced" is not the same signal as an
actual annoyed backpacker. But it's also not nothing.

Three of the five personas — independently, without being prompted to look
for it — flagged the same restaurant appearing twice in the itinerary. That
sent me back into the itinerary-builder code, where I found a genuine,
deterministic bug: the arrival day's dinner and the very next day's lunch
both independently picked "the first restaurant in the list," with no
awareness of each other. Every single itinerary this agent has ever built,
since Week 5, repeated a restaurant on day one. Fixed with a one-line
change and a regression test. The evaluation rubric's ten dimensions never
would have caught it — none of them measure restaurant repetition. The
simulated personas did, because they were reacting to the whole experience,
not to a formula.

## Where this leaves things

Overall score moved from 5.51 to 5.87 out of 10 — a real, measured
improvement, not a large one. `variety` nearly doubled (2.48 → 4.41).
`budget_accuracy` improved by roughly a quarter (3.91 → 4.88). One
dimension, `weather_match`, dropped — and I want to be honest about that
too rather than bury it: it's driven by real-world weather variance across
only 2-3 of 30 scenarios (a structural limitation of a free-tier forecast
API with a 5-day horizon, not a regression from anything changed this
week — verified directly, not assumed).

None of these numbers are the point, exactly. The point is that every one
of them is real, measured twice, and open to being wrong in a way I'd
notice and write down. That's been true since Week 1, and it's the one
thing I'd want this project to be remembered for more than any individual
score.

_Full methodology, per-dimension breakdown, and honest limitations:
`docs/EVALUATION_REPORT.md`. Full 24-week history: the README._
