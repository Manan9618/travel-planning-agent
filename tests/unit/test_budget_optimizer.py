from datetime import date, datetime

from travel_agent.models.core import (
    BudgetTier,
    DayPlan,
    FlightOption,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
)
from travel_agent.tools.budget_optimizer import BudgetOptimizer


def _prefs(budget_total=None, tier=None, priority_weights=None):
    return TravelPreferences(
        destination="Paris",
        raw_text="t",
        budget_total=budget_total,
        budget_tier=tier,
        priority_weights=priority_weights or {},
    )


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


def _day(day_number, items=None, day_date=date(2026, 9, 1)):
    return DayPlan(day_number=day_number, date=day_date, items=items or [])


def _itinerary(prefs, days, flights=None, hotel=None):
    return Itinerary(preferences=prefs, days=days, flights=flights or [], hotel=hotel)


def _optimizer():
    return BudgetOptimizer()


# --- allocate: tier defaults ---------------------------------------------------


def test_default_split_is_mid_range_when_no_tier_given():
    allocation = _optimizer().allocate(1000, flight_cost=0, tier=None)
    assert allocation.hotel == 500
    assert allocation.food == 250
    assert allocation.activities == 250


def test_backpacker_split():
    allocation = _optimizer().allocate(1000, flight_cost=0, tier=BudgetTier.BACKPACKER)
    assert allocation.hotel == 350
    assert allocation.food == 350
    assert allocation.activities == 300


def test_mid_range_split():
    allocation = _optimizer().allocate(1000, flight_cost=0, tier=BudgetTier.MID_RANGE)
    assert allocation.hotel == 500
    assert allocation.food == 250
    assert allocation.activities == 250


def test_luxury_split():
    allocation = _optimizer().allocate(1000, flight_cost=0, tier=BudgetTier.LUXURY)
    assert allocation.hotel == 600
    assert allocation.food == 250
    assert allocation.activities == 150


def test_flight_cost_is_a_pass_through_not_split():
    allocation = _optimizer().allocate(1000, flight_cost=300, tier=BudgetTier.MID_RANGE)
    assert allocation.flights == 300
    # remaining 700 split 50/25/25
    assert allocation.hotel == 350
    assert allocation.food == 175
    assert allocation.activities == 175


def test_flight_cost_exceeding_budget_leaves_nothing_for_rest():
    allocation = _optimizer().allocate(500, flight_cost=800, tier=BudgetTier.MID_RANGE)
    assert allocation.flights == 800
    assert allocation.hotel == 0
    assert allocation.food == 0
    assert allocation.activities == 0


def test_allocation_categories_sum_to_budget_when_flight_within_budget():
    allocation = _optimizer().allocate(1000, flight_cost=200, tier=BudgetTier.LUXURY)
    assert allocation.flights + allocation.hotel + allocation.food + allocation.activities == 1000


# --- allocate: priority_weights ---------------------------------------------------


def test_priority_weights_override_tier_default():
    allocation = _optimizer().allocate(
        1000,
        flight_cost=0,
        tier=BudgetTier.MID_RANGE,
        priority_weights={"accommodation": 0.6, "dining": 0.1, "activities": 0.3},
    )
    assert allocation.hotel == 600
    assert allocation.food == 100
    assert allocation.activities == 300


def test_priority_weights_normalized_even_if_not_summing_to_one():
    allocation = _optimizer().allocate(
        1000, flight_cost=0, priority_weights={"accommodation": 3, "dining": 1}
    )
    # normalized among mentioned categories: hotel 0.75, food 0.25, activities 0
    assert allocation.hotel == 750
    assert allocation.food == 250
    assert allocation.activities == 0


def test_priority_weights_accepts_aliases():
    allocation = _optimizer().allocate(
        1000, flight_cost=0, priority_weights={"hotel": 1.0, "food": 0.0}
    )
    assert allocation.hotel == 1000


def test_empty_priority_weights_falls_back_to_tier_default():
    allocation = _optimizer().allocate(
        1000, flight_cost=0, tier=BudgetTier.LUXURY, priority_weights={}
    )
    assert allocation.hotel == 600


def test_unrecognized_priority_keys_ignored_falls_back_if_none_recognized():
    allocation = _optimizer().allocate(
        1000, flight_cost=0, tier=BudgetTier.MID_RANGE, priority_weights={"shopping": 1.0}
    )
    assert allocation.hotel == 500  # mid-range default, since "shopping" isn't a known category


def test_negative_priority_weight_ignored():
    allocation = _optimizer().allocate(
        1000, flight_cost=0, priority_weights={"accommodation": -1, "dining": 1.0}
    )
    assert allocation.food == 1000
    assert allocation.hotel == 0


# --- evaluate ---------------------------------------------------


def test_evaluate_returns_none_without_budget():
    itinerary = _itinerary(_prefs(budget_total=None), [_day(1)])
    assert _optimizer().evaluate(itinerary) is None


def test_evaluate_flags_underused_category():
    prefs = _prefs(budget_total=1000, tier=BudgetTier.MID_RANGE)
    itinerary = _itinerary(prefs, [_day(1)], hotel=_hotel(50))  # 1 night = $50, allocated $500
    evaluation = _optimizer().evaluate(itinerary)
    hotel_eval = next(c for c in evaluation.categories if c.category == "hotel")
    assert hotel_eval.status == "under"
    assert any("upgrading" in s for s in evaluation.suggestions)


def test_evaluate_flags_overused_category():
    prefs = _prefs(budget_total=200, tier=BudgetTier.MID_RANGE)
    day = _day(1, items=[_item("restaurant", 150)])
    itinerary = _itinerary(prefs, [day])
    evaluation = _optimizer().evaluate(itinerary)
    food_eval = next(c for c in evaluation.categories if c.category == "food")
    assert food_eval.status == "over"
    assert any("cut costs" in s for s in evaluation.suggestions)


def test_evaluate_on_target_produces_no_suggestion_for_that_category():
    prefs = _prefs(budget_total=1000, tier=BudgetTier.MID_RANGE)
    itinerary = _itinerary(
        prefs, [_day(1), _day(2)], hotel=_hotel(500)
    )  # 1 night = 500, allocated 500
    evaluation = _optimizer().evaluate(itinerary)
    hotel_eval = next(c for c in evaluation.categories if c.category == "hotel")
    assert hotel_eval.status == "on_target"


def test_evaluate_includes_adherence_score():
    prefs = _prefs(budget_total=500)
    itinerary = _itinerary(prefs, [_day(1)], flights=[_flight(500)])
    evaluation = _optimizer().evaluate(itinerary)
    assert evaluation.adherence_score == 1.0


def test_evaluate_total_actual_matches_estimate_itinerary_cost():
    prefs = _prefs(budget_total=1000)
    day = _day(1, items=[_item("attraction", 50)])
    itinerary = _itinerary(prefs, [day], flights=[_flight(200)], hotel=_hotel(100))
    evaluation = _optimizer().evaluate(itinerary)
    assert evaluation.total_actual == 200 + 100 + 50


def test_evaluate_respects_priority_weights_in_allocation():
    prefs = _prefs(
        budget_total=1000, priority_weights={"accommodation": 0.8, "dining": 0.1, "activities": 0.1}
    )
    itinerary = _itinerary(prefs, [_day(1)])
    evaluation = _optimizer().evaluate(itinerary)
    assert evaluation.allocation.hotel == 800


def test_evaluate_respects_budget_tier_in_allocation():
    # Found via mutation testing (Week 17): a mutant that replaced
    # evaluate()'s `tier=prefs.budget_tier` with `tier=None` survived,
    # because every other evaluate() test uses a tier-less or mid-range
    # preference, which produces the same split as the None default
    # (_DEFAULT_SPLIT *is* MID_RANGE) - so evaluate()'s pass-through of
    # budget_tier into allocate() was never actually exercised through
    # evaluate() itself, only tested directly against allocate(). LUXURY
    # (60% hotel) vs MID_RANGE's 50% default makes the difference visible.
    prefs = _prefs(budget_total=1000, tier=BudgetTier.LUXURY)
    itinerary = _itinerary(prefs, [_day(1)])
    evaluation = _optimizer().evaluate(itinerary)
    assert evaluation.allocation.hotel == 600
