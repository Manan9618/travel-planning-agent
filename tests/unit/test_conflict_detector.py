from datetime import date, datetime

from travel_agent.models.core import (
    DayPlan,
    FlightOption,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
)
from travel_agent.tools.conflict_detector import ConflictDetector


class FixedTravelTime:
    def __init__(self, minutes: int = 15):
        self.minutes = minutes

    def minutes_between(self, olat, olng, dlat, dlng, mode="driving"):
        return self.minutes


def _prefs(budget_total=None, currency="USD"):
    return TravelPreferences(
        destination="Paris", raw_text="test", budget_total=budget_total, budget_currency=currency
    )


def _item(title, start, end, activity_type="attraction", lat=48.85, lng=2.35, cost=None):
    return ItineraryItem(
        time_slot="morning",
        start_time=start,
        end_time=end,
        activity_type=activity_type,
        title=title,
        lat=lat,
        lng=lng,
        cost=cost,
    )


def _day(day_number, items, day_date=date(2026, 9, 1)):
    return DayPlan(day_number=day_number, date=day_date, items=items)


def _itinerary(days, budget_total=None, flights=None, hotel=None):
    return Itinerary(
        preferences=_prefs(budget_total=budget_total), days=days, flights=flights or [], hotel=hotel
    )


def _detector(minutes=15):
    return ConflictDetector(travel_time_estimator=FixedTravelTime(minutes))


D = date(2026, 9, 1)


def _dt(hour, minute=0):
    return datetime(2026, 9, 1, hour, minute)


# --- overlap ---------------------------------------------------------------


def test_overlapping_items_flagged():
    items = [_item("A", _dt(9), _dt(11)), _item("B", _dt(10), _dt(12))]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector().detect(itinerary)
    assert [c.conflict_type for c in conflicts] == ["overlap"]


def test_two_separate_overlaps_both_flagged():
    items = [
        _item("A", _dt(9), _dt(11)),
        _item("B", _dt(10), _dt(13)),
        _item("C", _dt(12), _dt(14)),
    ]
    itinerary = _itinerary([_day(1, items)])
    conflicts = [c for c in _detector().detect(itinerary) if c.conflict_type == "overlap"]
    assert len(conflicts) == 2


def test_back_to_back_items_not_an_overlap():
    items = [_item("A", _dt(9), _dt(11)), _item("B", _dt(11), _dt(12))]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "overlap" for c in conflicts)


def test_single_item_no_overlap():
    itinerary = _itinerary([_day(1, [_item("A", _dt(9), _dt(11))])])
    assert _detector().detect(itinerary) == []


def test_empty_day_no_crash():
    itinerary = _itinerary([_day(1, [])])
    assert _detector().detect(itinerary) == []


# --- impossible travel -------------------------------------------------


def test_impossible_travel_flagged_when_gap_too_short():
    items = [
        _item("A", _dt(9), _dt(10), lat=48.85, lng=2.35),
        _item("B", _dt(10, 5), _dt(11), lat=48.90, lng=2.40),  # only 5 min gap
    ]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector(minutes=60).detect(itinerary)
    assert any(c.conflict_type == "impossible_travel" for c in conflicts)


def test_travel_gap_exactly_equal_to_required_is_not_impossible():
    items = [
        _item("A", _dt(9), _dt(10)),
        _item("B", _dt(10, 30), _dt(11)),  # 30 min gap
    ]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector(minutes=30).detect(itinerary)
    assert not any(c.conflict_type == "impossible_travel" for c in conflicts)


def test_travel_gap_larger_than_required_is_fine():
    items = [_item("A", _dt(9), _dt(10)), _item("B", _dt(14), _dt(15))]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector(minutes=30).detect(itinerary)
    assert not any(c.conflict_type == "impossible_travel" for c in conflicts)


def test_items_missing_coordinates_are_skipped_not_crashed():
    items = [
        ItineraryItem(
            time_slot="morning",
            start_time=_dt(9),
            end_time=_dt(10),
            activity_type="hotel_checkin",
            title="Check in",
            lat=None,
            lng=None,
        ),
        _item("B", _dt(10, 1), _dt(11)),
    ]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector(minutes=999).detect(itinerary)
    assert not any(c.conflict_type == "impossible_travel" for c in conflicts)


# --- budget overrun ---------------------------------------------------


def test_budget_within_limit_no_conflict():
    hotel = HotelOption(name="H", address="Paris", lat=48.85, lng=2.35, price_per_night=50)
    itinerary = _itinerary([_day(1, [])], budget_total=1000, hotel=hotel)
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "budget_overrun" for c in conflicts)


def test_budget_exceeded_flagged_at_trip_level():
    hotel = HotelOption(name="H", address="Paris", lat=48.85, lng=2.35, price_per_night=500)
    itinerary = _itinerary([_day(1, []), _day(2, [])], budget_total=100, hotel=hotel)
    conflicts = [c for c in _detector().detect(itinerary) if c.conflict_type == "budget_overrun"]
    assert len(conflicts) == 1
    assert conflicts[0].day_number == 0


def test_no_budget_set_skips_budget_check():
    hotel = HotelOption(name="H", address="Paris", lat=48.85, lng=2.35, price_per_night=5000)
    itinerary = _itinerary([_day(1, [])], budget_total=None, hotel=hotel)
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "budget_overrun" for c in conflicts)


def test_fixed_costs_alone_exceed_budget_flagged():
    flight = FlightOption(
        airline="AF",
        origin="BOS",
        destination="PAR",
        departure_time="2026-09-01T02:00:00",
        arrival_time="2026-09-01T14:00:00",
        duration_minutes=420,
        price=2000,
    )
    hotel = HotelOption(name="H", address="Paris", lat=48.85, lng=2.35, price_per_night=500)
    itinerary = _itinerary([_day(1, [])], budget_total=50, flights=[flight], hotel=hotel)
    conflicts = [c for c in _detector().detect(itinerary) if c.conflict_type == "budget_overrun"]
    assert len(conflicts) == 1


# --- max activities ---------------------------------------------------


def test_activities_at_max_no_conflict():
    items = [_item(f"A{i}", _dt(9 + i), _dt(10 + i)) for i in range(4)]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "max_activities_exceeded" for c in conflicts)


def test_activities_over_max_flagged():
    items = [_item(f"A{i}", _dt(9 + i), _dt(9 + i, 30)) for i in range(5)]
    itinerary = _itinerary([_day(1, items)])
    conflicts = [
        c for c in _detector().detect(itinerary) if c.conflict_type == "max_activities_exceeded"
    ]
    assert len(conflicts) == 1


def test_non_activity_items_dont_count_toward_max():
    items = [
        _item("Flight", _dt(2), _dt(2), activity_type="flight"),
        _item("Transfer", _dt(2), _dt(3), activity_type="transfer"),
        _item("Checkin", _dt(15), _dt(15), activity_type="hotel_checkin"),
        _item("A1", _dt(16), _dt(17)),
        _item("A2", _dt(18), _dt(19)),
    ]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "max_activities_exceeded" for c in conflicts)


# --- meal time violations ---------------------------------------------------


def test_restaurant_at_lunch_time_ok():
    items = [_item("Lunch", _dt(12, 30), _dt(13, 30), activity_type="restaurant")]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "meal_time_violation" for c in conflicts)


def test_restaurant_at_dinner_time_ok():
    items = [_item("Dinner", _dt(19, 30), _dt(20, 30), activity_type="restaurant")]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "meal_time_violation" for c in conflicts)


def test_restaurant_at_3am_flagged():
    items = [_item("Odd Hour Meal", _dt(3), _dt(4), activity_type="restaurant")]
    itinerary = _itinerary([_day(1, items)])
    conflicts = [
        c for c in _detector().detect(itinerary) if c.conflict_type == "meal_time_violation"
    ]
    assert len(conflicts) == 1


def test_non_restaurant_at_odd_time_not_flagged():
    items = [_item("Late Attraction", _dt(3), _dt(4), activity_type="attraction")]
    itinerary = _itinerary([_day(1, items)])
    conflicts = _detector().detect(itinerary)
    assert not any(c.conflict_type == "meal_time_violation" for c in conflicts)
