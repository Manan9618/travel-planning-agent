# ADR-0003: TravelPayouts instead of Amadeus for flight search

**Status**: Accepted (Week 2)

## Context

The plan specifies Amadeus for Developers (sandbox tier) for flight search.
Amadeus's sandbox API returns synthetic, non-representative flight/price
data by design — useful for testing request/response shapes, not for
producing itinerary output (PDFs, budget estimates, evaluation scores) that
should reflect plausible real-world numbers. TravelPayouts offers a
production-representative flight-price API (merging `/v1/prices/cheap` and
`/v2/prices/latest`) on a free tier with real, if approximate, pricing.

## Decision

Use TravelPayouts instead of Amadeus for `FlightSearchTool`. This is a
documented substitution, not a silent deviation — flagged in the README
since Week 2 alongside the project's other named stack substitutions
(Serper instead of OpenStreetMap/Google Places for attractions, GPT-4o
instead of "Claude 3.5 Sonnet / GPT-4o" as a single LLM choice).

## Consequences

- **Positive**: every PDF itinerary, budget estimate, and evaluation score
  this project has produced since Week 2 reflects a real flight price
  someone could plausibly pay, not sandbox placeholder data — meaningfully
  more useful for a portfolio piece meant to demonstrate the actual output
  quality.
- **Negative**: TravelPayouts returns the cheapest fare found *near* the
  requested month, not necessarily on the requested date — a real,
  documented characteristic that the itinerary builder has to work around
  (Week 5: "only the time-of-day is meaningful, so it's anchored to the
  itinerary's real start date rather than the flight's own date").
- **Negative**: diverges from the plan's named tool, meaning a reviewer
  checking deliverables against the plan literally needs this ADR (and the
  README's own inline notes) to understand why — worth the tradeoff for
  genuinely better output, but a real cost of not building exactly to spec.
