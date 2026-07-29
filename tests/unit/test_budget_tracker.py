import pytest
from pydantic import ValidationError

from travel_agent.tools.budget_tracker import BudgetTrackerTool


def test_starts_with_zero_spent():
    tracker = BudgetTrackerTool(total_budget=1000)
    assert tracker.total_spent == 0
    assert tracker.remaining == 1000
    assert tracker.breakdown() == {}


def test_add_cost_accumulates_per_category():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 300)
    tracker.add_cost("flights", 50)
    assert tracker.breakdown()["flights"] == 350


def test_add_cost_tracks_multiple_categories():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 300)
    tracker.add_cost("hotel", 400)
    tracker.add_cost("food", 100)
    assert tracker.breakdown() == {"flights": 300, "hotel": 400, "food": 100}


def test_total_spent_sums_all_categories():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 300)
    tracker.add_cost("hotel", 400)
    assert tracker.total_spent == 700


def test_remaining_is_budget_minus_spent():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 600)
    assert tracker.remaining == 400


def test_is_over_budget_false_when_under():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 600)
    assert tracker.is_over_budget is False


def test_is_over_budget_true_when_exceeded():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 700)
    tracker.add_cost("hotel", 500)
    assert tracker.is_over_budget is True
    assert tracker.remaining == -200


def test_add_cost_rejects_negative_amount():
    tracker = BudgetTrackerTool(total_budget=1000)
    with pytest.raises(ValueError):
        tracker.add_cost("flights", -50)


def test_add_cost_zero_is_allowed():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 0)
    assert tracker.breakdown()["flights"] == 0


def test_breakdown_returns_a_copy_not_live_reference():
    tracker = BudgetTrackerTool(total_budget=1000)
    tracker.add_cost("flights", 100)
    snapshot = tracker.breakdown()
    snapshot["flights"] = 999999
    assert tracker.breakdown()["flights"] == 100


def test_summary_reflects_currency():
    tracker = BudgetTrackerTool(total_budget=1000, currency="EUR")
    assert tracker.summary.currency == "EUR"


def test_summary_total_budget_matches_constructor():
    tracker = BudgetTrackerTool(total_budget=2500)
    assert tracker.summary.total_budget == 2500


def test_rejects_negative_total_budget():
    with pytest.raises(ValidationError):
        BudgetTrackerTool(total_budget=-100)
