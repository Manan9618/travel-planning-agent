import time
from datetime import date

from travel_agent.models.core import (
    Attraction,
    HotelOption,
    Restaurant,
    TravelPreferences,
)
from travel_agent.tools.multi_day_optimizer import (
    MAX_BALANCE_SWAPS,
    MultiDayOptimizer,
    _is_must_see,
    _priority_sorted,
)


class FixedTravelTime:
    """Test double: always returns a fixed number of minutes, no network calls."""

    def __init__(self, minutes: int = 15):
        self.minutes = minutes
        self.calls = 0

    def minutes_between(self, olat, olng, dlat, dlng, mode="driving"):
        self.calls += 1
        return self.minutes


class FixedDistanceMatrix:
    """Test double for DistanceMatrixTool: flat travel time between every pair,
    tracking how many times it was invoked (should always be exactly once per
    `build()` call, regardless of how much balancing/ordering search happens)."""

    def __init__(self, minutes: int = 15):
        self.minutes = minutes
        self.calls = 0

    def compute_matrix(self, points, mode="driving"):
        self.calls += 1
        n = len(points)
        return [[0 if i == j else self.minutes for j in range(n)] for i in range(n)]


class GeoDistanceMatrix:
    """Test double approximating real driving distances from lat/lng deltas,
    so clustering/balancing tests can rely on genuinely different distances
    between near vs. far points rather than a uniform flat time."""

    def compute_matrix(self, points, mode="driving"):
        n = len(points)
        matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    dlat = points[i][0] - points[j][0]
                    dlng = points[i][1] - points[j][1]
                    matrix[i][j] = round(((dlat**2 + dlng**2) ** 0.5) * 10000)
        return matrix


def _prefs(destination="Paris", start=date(2026, 9, 1), duration=6, **kw):
    return TravelPreferences(
        destination=destination,
        origin="Boston",
        start_date=start,
        duration_days=duration,
        raw_text="test",
        **kw,
    )


def _hotel(lat=48.85, lng=2.35):
    return HotelOption(
        name="Test Hotel", address="Paris, France", lat=lat, lng=lng, price_per_night=100
    )


def _attraction(name, lat=48.86, lng=2.33, rating=4.5, price=None):
    return Attraction(name=name, lat=lat, lng=lng, rating=rating, price=price)


def _restaurant(name, lat=48.85, lng=2.35):
    return Restaurant(name=name, lat=lat, lng=lng, rating=4.5)


def _optimizer(travel_minutes=15, matrix_minutes=15):
    return MultiDayOptimizer(
        travel_time_estimator=FixedTravelTime(travel_minutes),
        distance_matrix_tool=FixedDistanceMatrix(matrix_minutes),
    )


RESTAURANTS = [_restaurant(f"Restaurant {i}") for i in range(10)]


# --- must-see priority ---------------------------------------------------


def test_is_must_see_matches_case_insensitively():
    assert _is_must_see(_attraction("The Louvre Museum"), ["louvre"])
    assert not _is_must_see(_attraction("City Park"), ["louvre"])


def test_is_must_see_false_when_no_terms():
    assert not _is_must_see(_attraction("Anything"), [])


def test_priority_sorted_places_must_see_before_everything_else():
    attractions = [
        _attraction("Random Cafe", rating=4.9),
        _attraction("Louvre Museum", rating=3.0),  # lower rating, but must-see
        _attraction("City Park", rating=4.5),
    ]
    labels = [0, -1, 0]
    ordered = _priority_sorted(attractions, labels, ["Louvre"])
    assert ordered[0].name == "Louvre Museum"


def test_priority_sorted_groups_nice_to_have_by_cluster_size_first():
    a1, a2 = _attraction("A1"), _attraction("A2")  # cluster 0, two members
    b1 = _attraction("B1")  # cluster 1, single member
    ordered = _priority_sorted([b1, a1, a2], [1, 0, 0], must_see_terms=[])
    # the size-2 cluster (0) should be grouped ahead of the size-1 cluster (1)
    assert {o.name for o in ordered[:2]} == {"A1", "A2"}
    assert ordered[2].name == "B1"


def test_must_see_attraction_is_guaranteed_scheduled_somewhere():
    attractions = [_attraction(f"Attraction {i}", rating=3.0 + i * 0.1) for i in range(8)]
    attractions.append(_attraction("Hidden Gem", rating=1.0))  # lowest rated
    prefs = _prefs(duration=4, must_see=["Hidden Gem"])
    itinerary = _optimizer().build(prefs, _hotel(), attractions, RESTAURANTS)
    titles = {i.title for d in itinerary.days for i in d.items}
    assert "Hidden Gem" in titles


# --- backtracking against a per-day activity budget -----------------------


def test_backtracking_prefers_cheaper_combo_when_budget_is_tight():
    expensive = [_attraction("Expensive A", price=200), _attraction("Expensive B", price=200)]
    cheap = [_attraction("Cheap A", price=5), _attraction("Cheap B", price=5)]
    prefs = _prefs(duration=4, budget_total=1000, budget_tier="backpacker")
    itinerary = _optimizer().build(prefs, _hotel(), expensive + cheap, RESTAURANTS)

    day1_attractions = [i for i in itinerary.days[1].items if i.activity_type == "attraction"]
    day1_cost = sum(i.cost or 0 for i in day1_attractions)
    day2_attractions = [i for i in itinerary.days[2].items if i.activity_type == "attraction"]
    day2_cost = sum(i.cost or 0 for i in day2_attractions)
    # the cheap pair should be scheduled on the cheaper day, deferring the
    # expensive pair rather than blindly taking highest-priority order
    assert min(day1_cost, day2_cost) == 10.0
    assert max(day1_cost, day2_cost) == 400.0


def test_backtracking_never_leaves_a_day_empty_when_attractions_remain():
    # every attraction is expensive enough that no combo satisfies the budget —
    # backtracking must still gracefully degrade to a full assignment
    attractions = [_attraction(f"Pricey {i}", price=500) for i in range(4)]
    prefs = _prefs(duration=4, budget_total=100, budget_tier="backpacker")
    itinerary = _optimizer().build(prefs, _hotel(), attractions, RESTAURANTS)
    full_days = itinerary.days[1:-1]
    scheduled = {i.title for d in full_days for i in d.items if i.activity_type == "attraction"}
    assert scheduled == {a.name for a in attractions}


def test_no_budget_falls_back_to_priority_order_without_filtering():
    attractions = [
        _attraction(f"Attraction {i}", rating=5.0 - i * 0.1, price=1000) for i in range(4)
    ]
    prefs = _prefs(duration=4)  # no budget_total set
    itinerary = _optimizer().build(prefs, _hotel(), attractions, RESTAURANTS)
    scheduled = {
        i.title for d in itinerary.days[1:-1] for i in d.items if i.activity_type == "attraction"
    }
    assert scheduled == {a.name for a in attractions}


# --- route ordering + cross-day balancing ----------------------------------


def test_full_day_still_gets_both_attractions_via_build_day_delegation():
    attractions = [_attraction(f"Attraction {i}") for i in range(8)]
    itinerary = _optimizer().build(_prefs(duration=4), _hotel(), attractions, RESTAURANTS)
    full_day = itinerary.days[1]
    types = [item.activity_type for item in full_day.items]
    assert types == ["attraction", "restaurant", "attraction", "restaurant"]


def test_cross_day_balancing_reduces_max_minus_min_travel_spread():
    # cluster of 4 far-apart attractions plus a tight cluster near the hotel —
    # naive priority order alone would pile the far ones onto one day
    far = [
        _attraction("Far North", lat=49.20, lng=2.35, rating=4.9),
        _attraction("Far South", lat=48.50, lng=2.35, rating=4.8),
        _attraction("Far East", lat=48.85, lng=3.00, rating=4.7),
        _attraction("Far West", lat=48.85, lng=1.70, rating=4.6),
    ]
    near = [
        _attraction("Near A", lat=48.851, lng=2.351, rating=4.0),
        _attraction("Near B", lat=48.852, lng=2.352, rating=3.9),
        _attraction("Near C", lat=48.853, lng=2.353, rating=3.8),
        _attraction("Near D", lat=48.854, lng=2.354, rating=3.7),
    ]
    # duration=6 -> 4 full days, 2 slots each = 8 slots for 8 attractions
    optimizer = MultiDayOptimizer(
        travel_time_estimator=FixedTravelTime(), distance_matrix_tool=GeoDistanceMatrix()
    )

    labels = [0] * len(far + near)
    priority = _priority_sorted(far + near, labels, must_see_terms=[])
    per_day_budget = None
    unbalanced = optimizer._assign_attractions_to_days(priority, 4, per_day_budget)

    total_slots = 4 * 2
    pool = priority[:total_slots]
    points = [(48.85, 2.35)] + [(a.lat, a.lng) for a in pool]
    matrix = optimizer._distance_matrix_tool.compute_matrix(points)
    index_of = {id(a): i + 1 for i, a in enumerate(pool)}

    costs_before = [optimizer._day_travel_minutes(day, matrix, index_of) for day in unbalanced]
    balanced = optimizer._balance_days(unbalanced, matrix, index_of)
    costs_after = [optimizer._day_travel_minutes(day, matrix, index_of) for day in balanced]

    spread_before = max(costs_before) - min(costs_before)
    spread_after = max(costs_after) - min(costs_after)
    assert spread_after <= spread_before


def test_ordered_day_returns_valid_permutation_of_its_attractions():
    optimizer = _optimizer()
    day_attractions = [_attraction("A", lat=48.90, lng=2.40), _attraction("B", lat=48.80, lng=2.30)]
    matrix = optimizer._distance_matrix_tool.compute_matrix(
        [(48.85, 2.35), (48.90, 2.40), (48.80, 2.30)]
    )
    index_of = {id(day_attractions[0]): 1, id(day_attractions[1]): 2}
    ordered = optimizer._ordered_day(day_attractions, matrix, index_of)
    assert sorted(a.name for a in ordered) == ["A", "B"]


# --- distance matrix batching (network-call efficiency) --------------------


def test_distance_matrix_computed_exactly_once_per_build():
    matrix_double = FixedDistanceMatrix()
    optimizer = MultiDayOptimizer(
        travel_time_estimator=FixedTravelTime(), distance_matrix_tool=matrix_double
    )
    attractions = [_attraction(f"Attraction {i}") for i in range(10)]
    optimizer.build(_prefs(duration=6), _hotel(), attractions, RESTAURANTS)
    assert matrix_double.calls == 1


# --- edge cases -------------------------------------------------------------


def test_no_attractions_falls_back_gracefully():
    itinerary = _optimizer().build(_prefs(duration=4), _hotel(), [], RESTAURANTS)
    assert len(itinerary.days) == 4
    full_day_attractions = [i for i in itinerary.days[1].items if i.activity_type == "attraction"]
    assert full_day_attractions == []


def test_arrival_only_trip_num_full_days_zero_does_not_crash():
    attractions = [_attraction("Solo Attraction")]
    itinerary = _optimizer().build(_prefs(duration=1), _hotel(), attractions, RESTAURANTS)
    assert len(itinerary.days) == 1


def test_two_day_trip_has_no_full_days_and_does_not_crash():
    attractions = [_attraction("Solo Attraction")]
    itinerary = _optimizer().build(_prefs(duration=2), _hotel(), attractions, RESTAURANTS)
    assert len(itinerary.days) == 2


def test_fewer_attractions_than_slots_does_not_crash():
    attractions = [_attraction("Only One")]
    itinerary = _optimizer().build(_prefs(duration=6), _hotel(), attractions, RESTAURANTS)
    scheduled = {
        i.title for d in itinerary.days for i in d.items if i.activity_type == "attraction"
    }
    assert scheduled == {"Only One"}


def test_num_full_days_matches_middle_days_of_trip():
    attractions = [_attraction(f"Attraction {i}") for i in range(10)]
    itinerary = _optimizer().build(_prefs(duration=6), _hotel(), attractions, RESTAURANTS)
    assert len(itinerary.days) == 6
    assert itinerary.days[0].items[0].activity_type == "hotel_checkin"
    assert itinerary.days[-1].items[0].activity_type == "hotel_checkout"


# --- performance profiling (<5s / 7-day trip target) ------------------------


def test_optimizer_completes_well_under_five_seconds_for_a_seven_day_trip():
    attractions = [
        _attraction(f"Attraction {i}", lat=48.85 + (i % 5) * 0.01, lng=2.35 + (i // 5) * 0.01)
        for i in range(20)
    ]
    restaurants = [_restaurant(f"Restaurant {i}") for i in range(20)]
    prefs = _prefs(
        duration=7, budget_total=5000, budget_tier="mid_range", must_see=["Attraction 15"]
    )

    start = time.perf_counter()
    itinerary = _optimizer().build(prefs, _hotel(), attractions, restaurants)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0
    assert len(itinerary.days) == 7


def test_max_balance_swaps_bounds_the_rebalancing_loop():
    # sanity check on the constant itself, so a future accidental edit that
    # sets it to something unbounded (e.g. removing the cap) is caught
    assert 0 < MAX_BALANCE_SWAPS <= 10
