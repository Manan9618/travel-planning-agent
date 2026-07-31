#!/usr/bin/env python3
"""Week 8 deliverable: full constraint satisfaction test across 20 budget
scenarios with varying tiers, priority weights, and budget levels.

One real itinerary (real attractions/restaurants/hotel via Serper/Booking.com) is
built once for a fixed destination; each scenario just varies the traveler's
budget preferences and re-runs BudgetOptimizer.evaluate() against the same
itinerary. That's deliberate: the point is to exercise the OPTIMIZER's
allocation/scoring logic across many preference combinations, not to re-fetch
search results 20 times for what would be the same underlying trip.

Usage:
    poetry run python scripts/budget_scenarios_test.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, "src")

from travel_agent.models.core import BudgetTier, TravelPreferences  # noqa: E402
from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.budget_optimizer import BudgetOptimizer  # noqa: E402
from travel_agent.tools.hotel_search import HotelSearchTool  # noqa: E402
from travel_agent.tools.itinerary_builder import ItineraryBuilder  # noqa: E402
from travel_agent.tools.restaurant_finder import RestaurantFinderTool  # noqa: E402

DESTINATION = "Paris"
TRIP_START = date.today() + timedelta(days=45)
TRIP_LENGTH_DAYS = 5

# (label, budget_total, tier, priority_weights)
SCENARIOS = [
    ("Backpacker / low budget", 800, BudgetTier.BACKPACKER, {}),
    ("Backpacker / mid budget", 1500, BudgetTier.BACKPACKER, {}),
    ("Backpacker / high budget", 3000, BudgetTier.BACKPACKER, {}),
    ("Mid-range / low budget", 800, BudgetTier.MID_RANGE, {}),
    ("Mid-range / mid budget", 1500, BudgetTier.MID_RANGE, {}),
    ("Mid-range / high budget", 3000, BudgetTier.MID_RANGE, {}),
    ("Luxury / low budget", 800, BudgetTier.LUXURY, {}),
    ("Luxury / mid budget", 1500, BudgetTier.LUXURY, {}),
    ("Luxury / high budget", 3000, BudgetTier.LUXURY, {}),
    ("No tier specified", 1500, None, {}),
    (
        "Backpacker, prioritize accommodation",
        1500,
        BudgetTier.BACKPACKER,
        {"accommodation": 0.7, "dining": 0.15, "activities": 0.15},
    ),
    (
        "Mid-range, prioritize accommodation",
        1500,
        BudgetTier.MID_RANGE,
        {"accommodation": 0.7, "dining": 0.15, "activities": 0.15},
    ),
    (
        "Luxury, prioritize accommodation",
        1500,
        BudgetTier.LUXURY,
        {"accommodation": 0.7, "dining": 0.15, "activities": 0.15},
    ),
    (
        "Backpacker, prioritize dining",
        1500,
        BudgetTier.BACKPACKER,
        {"accommodation": 0.15, "dining": 0.7, "activities": 0.15},
    ),
    (
        "Mid-range, prioritize dining",
        1500,
        BudgetTier.MID_RANGE,
        {"accommodation": 0.15, "dining": 0.7, "activities": 0.15},
    ),
    (
        "Luxury, prioritize dining",
        1500,
        BudgetTier.LUXURY,
        {"accommodation": 0.15, "dining": 0.7, "activities": 0.15},
    ),
    (
        "Backpacker, prioritize activities",
        1500,
        BudgetTier.BACKPACKER,
        {"accommodation": 0.15, "dining": 0.15, "activities": 0.7},
    ),
    (
        "Mid-range, prioritize activities",
        1500,
        BudgetTier.MID_RANGE,
        {"accommodation": 0.15, "dining": 0.15, "activities": 0.7},
    ),
    (
        "Luxury, prioritize activities",
        1500,
        BudgetTier.LUXURY,
        {"accommodation": 0.15, "dining": 0.15, "activities": 0.7},
    ),
    ("Extremely tight budget (below fixed costs)", 100, BudgetTier.MID_RANGE, {}),
]


def main() -> int:
    assert len(SCENARIOS) == 20, f"expected 20 scenarios, got {len(SCENARIOS)}"

    end = TRIP_START + timedelta(days=TRIP_LENGTH_DAYS - 1)
    attractions = AttractionFinderTool().search(DESTINATION, max_results=10)
    restaurants = RestaurantFinderTool().search(DESTINATION, max_results=10)
    hotel = HotelSearchTool().search(DESTINATION, TRIP_START, end)[0]
    optimizer = BudgetOptimizer()
    builder = ItineraryBuilder()

    print(f"{'Scenario':<42} {'Adherence':>10} {'Hotel':>8} {'Food':>8} {'Activities':>11}")
    print("-" * 84)

    adherence_scores = []
    for label, budget_total, tier, priority_weights in SCENARIOS:
        prefs = TravelPreferences(
            destination=DESTINATION,
            start_date=TRIP_START,
            duration_days=TRIP_LENGTH_DAYS,
            budget_total=budget_total,
            budget_tier=tier,
            priority_weights=priority_weights,
            raw_text=label,
        )
        itinerary = builder.build(prefs, hotel, attractions, restaurants)
        evaluation = optimizer.evaluate(itinerary)
        assert evaluation is not None, f"{label}: expected an evaluation since budget_total is set"

        adherence_scores.append(evaluation.adherence_score)
        statuses = {c.category: c.status for c in evaluation.categories}
        print(
            f"{label:<42} {evaluation.adherence_score:>10.0%} "
            f"{statuses['hotel']:>8} {statuses['food']:>8} {statuses['activities']:>11}"
        )

    print("-" * 84)
    print(f"{'AVERAGE ADHERENCE':<42} {sum(adherence_scores) / len(adherence_scores):>10.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
