from datetime import date, datetime

import pytest
from pydantic import ValidationError

from travel_agent.models.core import (
    DayPlan,
    FlightOption,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
)
from travel_agent.tools.budget_tracker import (
    BudgetTrackerTool,
    budget_adherence_score,
    estimate_itinerary_cost,
    itinerary_cost_breakdown,
)


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


# --- itinerary_cost_breakdown / estimate_itinerary_cost / budget_adherence_score (Week 8) --------


def _prefs(budget_total=None):
    return TravelPreferences(destination="Paris", raw_text="t", budget_total=budget_total)


def _flight(price):
    return FlightOption(
        airline="AF",
        origin="BOS",
        destination="PAR",
        departure_time="2026-09-01T02:00:00",
        arrival_time="2026-09-01T14:00:00",
        duration_minutes=420,
        price=price,
    )


def _hotel(price_per_night):
    return HotelOption(
        name="H", address="Paris", lat=48.85, lng=2.35, price_per_night=price_per_night
    )


def _item(activity_type, cost):
    dt = datetime(2026, 9, 1)
    return ItineraryItem(
        time_slot="morning",
        start_time=dt,
        end_time=dt,
        activity_type=activity_type,
        title="x",
        cost=cost,
    )


def _itinerary(days, budget_total=None, flights=None, hotel=None):
    return Itinerary(
        preferences=_prefs(budget_total), days=days, flights=flights or [], hotel=hotel
    )


def _day(day_number, items=None, day_date=date(2026, 9, 1)):
    return DayPlan(day_number=day_number, date=day_date, items=items or [])


def test_breakdown_includes_flight_price():
    itinerary = _itinerary([_day(1)], flights=[_flight(500)])
    assert itinerary_cost_breakdown(itinerary)["flights"] == 500


def test_breakdown_hotel_multiplied_by_nights():
    days = [_day(i, day_date=date(2026, 9, i)) for i in range(1, 4)]  # 3 days -> 2 nights
    itinerary = _itinerary(days, hotel=_hotel(100))
    assert itinerary_cost_breakdown(itinerary)["hotel"] == 200


def test_breakdown_single_day_trip_counts_as_one_night():
    itinerary = _itinerary([_day(1)], hotel=_hotel(100))
    assert itinerary_cost_breakdown(itinerary)["hotel"] == 100


def test_breakdown_no_hotel_is_zero():
    itinerary = _itinerary([_day(1)])
    assert itinerary_cost_breakdown(itinerary)["hotel"] == 0


def test_breakdown_food_sums_restaurant_item_costs():
    day = _day(1, items=[_item("restaurant", 30), _item("restaurant", 50)])
    itinerary = _itinerary([day])
    assert itinerary_cost_breakdown(itinerary)["food"] == 80


def test_breakdown_activities_sums_attraction_item_costs():
    day = _day(1, items=[_item("attraction", 20)])
    itinerary = _itinerary([day])
    assert itinerary_cost_breakdown(itinerary)["activities"] == 20


def test_breakdown_ignores_items_without_cost():
    day = _day(1, items=[_item("attraction", None)])
    itinerary = _itinerary([day])
    assert itinerary_cost_breakdown(itinerary)["activities"] == 0


def test_breakdown_ignores_non_attraction_restaurant_types():
    day = _day(1, items=[_item("transfer", 40)])
    breakdown = itinerary_cost_breakdown(_itinerary([day]))
    assert breakdown["food"] == 0
    assert breakdown["activities"] == 0


def test_estimate_itinerary_cost_sums_all_categories():
    day = _day(1, items=[_item("restaurant", 30), _item("attraction", 20)])
    itinerary = _itinerary([day], flights=[_flight(500)], hotel=_hotel(100))
    assert estimate_itinerary_cost(itinerary) == 500 + 100 + 30 + 20


def test_adherence_score_perfect_match_is_one():
    itinerary = _itinerary([_day(1)], budget_total=500, flights=[_flight(500)])
    assert budget_adherence_score(itinerary) == 1.0


def test_adherence_score_decreases_with_overspend():
    itinerary = _itinerary([_day(1)], budget_total=500, flights=[_flight(750)])
    assert budget_adherence_score(itinerary) == pytest.approx(0.5)


def test_adherence_score_decreases_with_underspend():
    itinerary = _itinerary([_day(1)], budget_total=1000, flights=[_flight(500)])
    assert budget_adherence_score(itinerary) == pytest.approx(0.5)


def test_adherence_score_clips_at_zero_for_extreme_overspend():
    itinerary = _itinerary([_day(1)], budget_total=100, flights=[_flight(1000)])
    assert budget_adherence_score(itinerary) == 0.0


def test_adherence_score_none_without_budget():
    itinerary = _itinerary([_day(1)], budget_total=None)
    assert budget_adherence_score(itinerary) is None
