from datetime import date, datetime

from travel_agent.models.core import (
    Conflict,
    DayPlan,
    FlightOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
)
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.conflict_resolver import ConflictResolver, detect_and_resolve


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


def _resolver(minutes=15):
    return ConflictResolver(travel_time_estimator=FixedTravelTime(minutes))


def _dt(hour, minute=0):
    return datetime(2026, 9, 1, hour, minute)


# --- overlap ---------------------------------------------------------------


def test_resolve_overlap_shifts_later_item():
    items = [_item("A", _dt(9), _dt(11)), _item("B", _dt(10), _dt(12))]
    itinerary = _itinerary([_day(1, items)])
    conflict = Conflict(day_number=1, conflict_type="overlap", description="x")
    resolved, log, unresolved = _resolver().resolve(itinerary, [conflict])

    assert unresolved == []
    assert log[0].resolved is True
    day = resolved.days[0]
    b = next(i for i in day.items if i.title == "B")
    a = next(i for i in day.items if i.title == "A")
    assert b.start_time >= a.end_time


def test_resolve_overlap_original_itinerary_untouched():
    items = [_item("A", _dt(9), _dt(11)), _item("B", _dt(10), _dt(12))]
    itinerary = _itinerary([_day(1, items)])
    conflict = Conflict(day_number=1, conflict_type="overlap", description="x")
    _resolver().resolve(itinerary, [conflict])
    # resolve() works on a deep copy; caller's original object must be unchanged
    b_original = next(i for i in itinerary.days[0].items if i.title == "B")
    assert b_original.start_time == _dt(10)


# --- impossible travel -------------------------------------------------


def test_resolve_impossible_travel_pushes_later_item_back():
    items = [_item("A", _dt(9), _dt(10)), _item("B", _dt(10, 5), _dt(11))]
    itinerary = _itinerary([_day(1, items)])
    conflict = Conflict(day_number=1, conflict_type="impossible_travel", description="x")
    resolved, log, unresolved = _resolver(minutes=60).resolve(itinerary, [conflict])

    assert unresolved == []
    day = resolved.days[0]
    a = next(i for i in day.items if i.title == "A")
    b = next(i for i in day.items if i.title == "B")
    assert (b.start_time - a.end_time).total_seconds() / 60 >= 60


# --- max activities ---------------------------------------------------


def test_resolve_max_activities_removes_lowest_cost_items():
    items = [
        _item("Expensive", _dt(9), _dt(10), cost=100),
        _item("Mid", _dt(11), _dt(12), cost=50),
        _item("Cheap", _dt(13), _dt(14), cost=10),
        _item("Free1", _dt(15), _dt(16), cost=None),
        _item("Free2", _dt(17), _dt(18), cost=None),
    ]
    itinerary = _itinerary([_day(1, items)])
    conflict = Conflict(day_number=1, conflict_type="max_activities_exceeded", description="x")
    resolved, log, unresolved = _resolver().resolve(itinerary, [conflict])

    assert unresolved == []
    remaining_titles = {i.title for i in resolved.days[0].items}
    assert len(remaining_titles) == 4
    assert "Expensive" in remaining_titles  # the priciest one should survive


def test_resolve_max_activities_already_within_limit_is_a_noop():
    items = [_item(f"A{i}", _dt(9 + i), _dt(9 + i, 30)) for i in range(3)]
    itinerary = _itinerary([_day(1, items)])
    conflict = Conflict(day_number=1, conflict_type="max_activities_exceeded", description="x")
    resolved, log, unresolved = _resolver().resolve(itinerary, [conflict])
    assert len(resolved.days[0].items) == 3
    assert log[0].resolved is True


# --- meal time ---------------------------------------------------------


def test_resolve_meal_time_moves_restaurant_into_nearest_window():
    items = [_item("Odd Hour Meal", _dt(3), _dt(4), activity_type="restaurant")]
    itinerary = _itinerary([_day(1, items)])
    conflict = Conflict(day_number=1, conflict_type="meal_time_violation", description="x")
    resolved, log, unresolved = _resolver().resolve(itinerary, [conflict])

    assert unresolved == []
    item = resolved.days[0].items[0]
    from travel_agent.tools.conflict_detector import DINNER_WINDOW, LUNCH_WINDOW

    t = item.start_time.time()
    assert (LUNCH_WINDOW[0] <= t <= LUNCH_WINDOW[1]) or (DINNER_WINDOW[0] <= t <= DINNER_WINDOW[1])


def test_resolve_meal_time_preserves_duration():
    items = [_item("Meal", _dt(3), _dt(4, 30), activity_type="restaurant")]  # 90 min
    itinerary = _itinerary([_day(1, items)])
    conflict = Conflict(day_number=1, conflict_type="meal_time_violation", description="x")
    resolved, _, _ = _resolver().resolve(itinerary, [conflict])
    item = resolved.days[0].items[0]
    assert (item.end_time - item.start_time).total_seconds() / 60 == 90


# --- budget overrun ---------------------------------------------------


def test_resolve_budget_overrun_removes_expensive_items_until_within_budget():
    items = [
        _item("Expensive Tour", _dt(9), _dt(11), cost=200),
        _item("Museum", _dt(12), _dt(13), cost=30),
    ]
    itinerary = _itinerary([_day(1, items)], budget_total=50)
    conflict = Conflict(day_number=0, conflict_type="budget_overrun", description="x")
    resolved, log, unresolved = _resolver().resolve(itinerary, [conflict])

    assert unresolved == []
    assert log[0].resolved is True
    remaining_titles = {i.title for i in resolved.days[0].items}
    assert "Expensive Tour" not in remaining_titles


def test_resolve_budget_overrun_unresolvable_when_fixed_costs_alone_exceed_budget():
    flight = FlightOption(
        airline="AF",
        origin="BOS",
        destination="PAR",
        departure_time="2026-09-01T02:00:00",
        arrival_time="2026-09-01T14:00:00",
        duration_minutes=420,
        price=2000,
    )
    itinerary = _itinerary([_day(1, [])], budget_total=50, flights=[flight])
    conflict = Conflict(day_number=0, conflict_type="budget_overrun", description="x")
    resolved, log, unresolved = _resolver().resolve(itinerary, [conflict])

    assert len(unresolved) == 1
    assert log[0].resolved is False
    assert "needs a decision" in log[0].action


def test_unknown_conflict_type_is_not_resolved():
    itinerary = _itinerary([_day(1, [])])
    conflict = Conflict(day_number=1, conflict_type="something_new", description="x")
    resolved, log, unresolved = _resolver().resolve(itinerary, [conflict])
    assert unresolved == [conflict]
    assert log[0].resolved is False


# --- detect_and_resolve (iterative loop) --------------------------------


def test_detect_and_resolve_converges_on_cascading_conflict():
    # a meal-time fix can create a new impossible-travel gap; verify the loop
    # keeps going until both are actually fixed, not just the first one found
    items = [
        _item("Morning Spot", _dt(9), _dt(10), lat=48.85, lng=2.35),
        _item("Late Night Meal", _dt(3), _dt(4), activity_type="restaurant", lat=48.90, lng=2.40),
    ]
    itinerary = _itinerary([_day(1, items)])
    detector = ConflictDetector(travel_time_estimator=FixedTravelTime(600))
    resolver = ConflictResolver(travel_time_estimator=FixedTravelTime(600))

    resolved, log, unresolved = detect_and_resolve(itinerary, detector, resolver, max_iterations=5)

    final_conflicts = detector.detect(resolved)
    assert final_conflicts == []
    assert unresolved == []
    assert len(log) >= 1


def test_detect_and_resolve_no_conflicts_returns_immediately():
    itinerary = _itinerary([_day(1, [_item("A", _dt(9), _dt(10))])])
    detector = ConflictDetector(travel_time_estimator=FixedTravelTime(5))
    resolver = ConflictResolver(travel_time_estimator=FixedTravelTime(5))
    resolved, log, unresolved = detect_and_resolve(itinerary, detector, resolver)
    assert log == []
    assert unresolved == []


def test_detect_and_resolve_bounded_by_max_iterations_for_persistent_conflict():
    flight = FlightOption(
        airline="AF",
        origin="BOS",
        destination="PAR",
        departure_time="2026-09-01T02:00:00",
        arrival_time="2026-09-01T14:00:00",
        duration_minutes=420,
        price=5000,
    )
    itinerary = _itinerary([_day(1, [])], budget_total=10, flights=[flight])
    detector = ConflictDetector()
    resolver = ConflictResolver()
    # must terminate rather than looping forever on the unresolvable budget conflict
    resolved, log, unresolved = detect_and_resolve(itinerary, detector, resolver, max_iterations=3)
    assert len(unresolved) == 1
    assert unresolved[0].conflict_type == "budget_overrun"
