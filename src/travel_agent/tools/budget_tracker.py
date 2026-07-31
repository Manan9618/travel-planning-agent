"""BudgetTrackerTool — Week 3 deliverable. Pure computation, no external API."""

from __future__ import annotations

from travel_agent.models.core import BudgetSummary, Itinerary

_ACTIVITY_TYPES = {"attraction", "restaurant"}


def itinerary_cost_breakdown(itinerary: Itinerary) -> dict[str, float]:
    """Best-effort cost by category: real flight/hotel prices plus whatever
    attraction/restaurant items happen to carry a cost (restaurants always do,
    via RestaurantFinderTool.estimate_meal_cost; attractions rarely do — Serper
    seldom supplies a price). Used by ConflictDetector/ConflictResolver/
    BudgetOptimizer for budget checks.
    """
    breakdown = {"flights": 0.0, "hotel": 0.0, "food": 0.0, "activities": 0.0}
    breakdown["flights"] = sum(f.price for f in itinerary.flights)
    if itinerary.hotel:
        nights = max(len(itinerary.days) - 1, 1)
        breakdown["hotel"] = itinerary.hotel.price_per_night * nights
    for day in itinerary.days:
        for item in day.items:
            if not item.cost:
                continue
            if item.activity_type == "restaurant":
                breakdown["food"] += item.cost
            elif item.activity_type == "attraction":
                breakdown["activities"] += item.cost
    return breakdown


def estimate_itinerary_cost(itinerary: Itinerary) -> float:
    return sum(itinerary_cost_breakdown(itinerary).values())


def budget_adherence_score(itinerary: Itinerary) -> float | None:
    """1.0 = actual spend exactly matches the stated budget; decreases toward 0
    the further actual spend is from budget_total, in either direction (both
    overspending and significant underspending count against "adherence" — the
    plan's own tips call this a target to hit, not just a ceiling to stay under).
    None if no budget was stated, since there's nothing to measure adherence to.
    """
    budget = itinerary.preferences.budget_total
    if not budget:
        return None
    actual = estimate_itinerary_cost(itinerary)
    return max(0.0, 1 - abs(actual - budget) / budget)


class BudgetTrackerTool:
    def __init__(self, total_budget: float, currency: str = "USD") -> None:
        self._summary = BudgetSummary(total_budget=total_budget, currency=currency)

    def add_cost(self, category: str, amount: float) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        current = self._summary.spent_by_category.get(category, 0.0)
        self._summary.spent_by_category[category] = current + amount

    @property
    def summary(self) -> BudgetSummary:
        return self._summary

    @property
    def remaining(self) -> float:
        return self._summary.remaining

    @property
    def total_spent(self) -> float:
        return self._summary.total_spent

    @property
    def is_over_budget(self) -> bool:
        return self._summary.remaining < 0

    def breakdown(self) -> dict[str, float]:
        return dict(self._summary.spent_by_category)
