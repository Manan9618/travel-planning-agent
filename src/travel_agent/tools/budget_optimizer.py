"""BudgetOptimizer — Week 8 deliverable.

Flights are treated as a pass-through: their price is set by the market (whatever
FlightSearchTool found), not something to "allocate" a percentage toward. The
optimizer splits whatever budget remains *after* flights across hotel/food/
activities, using tier-based defaults (backpacker/mid-range/luxury) that can be
shifted by the user's TravelPreferences.priority_weights (e.g. "I prioritize
accommodation over dining"). It then compares that allocation against what the
built itinerary actually costs (via budget_tracker.itinerary_cost_breakdown) and
produces upgrade suggestions (categories using much less than their share) or cut
suggestions (categories running over), plus the overall budget_adherence_score.
"""

from __future__ import annotations

from travel_agent.models.core import (
    BudgetAllocation,
    BudgetEvaluation,
    BudgetTier,
    CategoryEvaluation,
    Itinerary,
)
from travel_agent.tools.budget_tracker import budget_adherence_score, itinerary_cost_breakdown

DEFAULT_TIER_SPLITS: dict[BudgetTier, dict[str, float]] = {
    BudgetTier.BACKPACKER: {"hotel": 0.35, "food": 0.35, "activities": 0.30},
    BudgetTier.MID_RANGE: {"hotel": 0.50, "food": 0.25, "activities": 0.25},
    BudgetTier.LUXURY: {"hotel": 0.60, "food": 0.25, "activities": 0.15},
}
_DEFAULT_SPLIT = DEFAULT_TIER_SPLITS[BudgetTier.MID_RANGE]

_PRIORITY_KEY_ALIASES = {
    "accommodation": "hotel",
    "hotel": "hotel",
    "hotels": "hotel",
    "dining": "food",
    "food": "food",
    "restaurants": "food",
    "meals": "food",
    "activities": "activities",
    "attractions": "activities",
    "sightseeing": "activities",
}

_UNDER_ALLOCATION_RATIO = 0.7  # actual/allocated below this -> "consider upgrading"
_OVER_ALLOCATION_RATIO = 1.1  # actual/allocated above this -> "over budget for category"


def _normalize_priority_weights(priority_weights: dict[str, float]) -> dict[str, float] | None:
    mapped = {"hotel": 0.0, "food": 0.0, "activities": 0.0}
    total = 0.0
    for key, value in priority_weights.items():
        canonical = _PRIORITY_KEY_ALIASES.get(key.lower())
        if canonical and value > 0:
            mapped[canonical] += value
            total += value
    if total <= 0:
        return None
    return {k: v / total for k, v in mapped.items()}


class BudgetOptimizer:
    def allocate(
        self,
        budget_total: float,
        flight_cost: float,
        tier: BudgetTier | None = None,
        priority_weights: dict[str, float] | None = None,
    ) -> BudgetAllocation:
        split = (
            dict(DEFAULT_TIER_SPLITS.get(tier, _DEFAULT_SPLIT)) if tier else dict(_DEFAULT_SPLIT)
        )
        if priority_weights:
            normalized = _normalize_priority_weights(priority_weights)
            if normalized:
                split = normalized

        remaining = max(budget_total - flight_cost, 0.0)
        return BudgetAllocation(
            flights=flight_cost,
            hotel=remaining * split["hotel"],
            food=remaining * split["food"],
            activities=remaining * split["activities"],
        )

    def evaluate(self, itinerary: Itinerary) -> BudgetEvaluation | None:
        prefs = itinerary.preferences
        if not prefs.budget_total:
            return None

        actual = itinerary_cost_breakdown(itinerary)
        allocation = self.allocate(
            prefs.budget_total,
            actual["flights"],
            tier=prefs.budget_tier,
            priority_weights=prefs.priority_weights,
        )

        categories = []
        suggestions = []
        for category in ("hotel", "food", "activities"):
            allocated = getattr(allocation, category)
            spent = actual[category]
            difference = spent - allocated
            status = self._status(spent, allocated)
            categories.append(
                CategoryEvaluation(
                    category=category,
                    allocated=allocated,
                    actual=spent,
                    difference=difference,
                    status=status,
                )
            )
            suggestions.extend(self._suggestions(category, allocated, spent, status))

        return BudgetEvaluation(
            allocation=allocation,
            categories=categories,
            total_allocated=allocation.flights
            + allocation.hotel
            + allocation.food
            + allocation.activities,
            total_actual=sum(actual.values()),
            adherence_score=budget_adherence_score(itinerary),
            suggestions=suggestions,
        )

    @staticmethod
    def _status(actual: float, allocated: float) -> str:
        if allocated <= 0:
            return "on_target" if actual <= 0 else "over"
        ratio = actual / allocated
        if ratio < _UNDER_ALLOCATION_RATIO:
            return "under"
        if ratio > _OVER_ALLOCATION_RATIO:
            return "over"
        return "on_target"

    @staticmethod
    def _suggestions(category: str, allocated: float, actual: float, status: str) -> list[str]:
        label = category.title()
        if status == "under" and allocated > 0:
            pct_used = actual / allocated
            return [
                f"{label} is only using {pct_used:.0%} of its ${allocated:.0f} budget — "
                f"consider upgrading (e.g. a nicer hotel or a special dinner)"
            ]
        if status == "over":
            over_amount = actual - allocated
            return [
                f"{label} is ${over_amount:.0f} over its ${allocated:.0f} budget — "
                f"consider cheaper options to cut costs"
            ]
        return []
