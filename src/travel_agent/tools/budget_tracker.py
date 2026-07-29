"""BudgetTrackerTool — Week 3 deliverable. Pure computation, no external API."""

from __future__ import annotations

from travel_agent.models.core import BudgetSummary


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
