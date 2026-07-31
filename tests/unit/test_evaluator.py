from datetime import date

from travel_agent.models.core import (
    Conflict,
    DayPlan,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
    WeatherForecast,
)
from travel_agent.tools.evaluator import ItineraryEvaluator
from travel_agent.tools.itinerary_judge import JudgeScores


class FakeConflictDetector:
    def __init__(self, conflicts=None):
        self._conflicts = conflicts or []

    def detect(self, itinerary):
        return self._conflicts


class FakeDistanceMatrix:
    """Flat travel time between every pair, so 'as-scheduled' and 'naive
    random' tours cost the same — isolates geo_efficiency's arithmetic from
    needing genuinely different real-world distances."""

    def __init__(self, minutes=10):
        self.minutes = minutes

    def compute_matrix(self, points, mode="driving"):
        n = len(points)
        return [[0 if i == j else self.minutes for j in range(n)] for i in range(n)]


class FakeJudge:
    def __init__(self, scores: JudgeScores):
        self._scores = scores

    def judge(self, preferences, itinerary):
        return self._scores


DEFAULT_JUDGE_SCORES = JudgeScores(
    personalization_fit=7,
    narrative_quality=8,
    practicality=6,
    overall_satisfaction=7,
    explanation="Reasonable plan overall.",
)


def _prefs(**overrides):
    defaults = dict(destination="Paris", start_date=date(2026, 9, 1), duration_days=4, raw_text="t")
    defaults.update(overrides)
    return TravelPreferences(**defaults)


def _hotel():
    return HotelOption(name="Hotel", address="Paris", lat=48.85, lng=2.35, price_per_night=100)


def _attraction_item(title, lat=48.86, lng=2.33, category="Museum", cost=None):
    return ItineraryItem(
        time_slot="morning",
        start_time="2026-09-02T09:00:00",
        end_time="2026-09-02T11:00:00",
        activity_type="attraction",
        title=title,
        category=category,
        lat=lat,
        lng=lng,
        cost=cost,
    )


def _restaurant_item(title="Bistro", cost=30):
    return ItineraryItem(
        time_slot="afternoon",
        start_time="2026-09-02T12:30:00",
        end_time="2026-09-02T13:30:00",
        activity_type="restaurant",
        title=title,
        cost=cost,
    )


def _evaluator(conflicts=None, matrix_minutes=10, judge_scores=DEFAULT_JUDGE_SCORES):
    return ItineraryEvaluator(
        judge=FakeJudge(judge_scores),
        conflict_detector=FakeConflictDetector(conflicts),
        distance_matrix_tool=FakeDistanceMatrix(matrix_minutes),
    )


def _full_day_itinerary(items_day2=None, must_see=None, budget_total=None, weather=None):
    items_day2 = (
        items_day2
        if items_day2 is not None
        else [
            _attraction_item("Louvre", category="Museum"),
            _attraction_item("Eiffel Tower", lat=48.858, lng=2.294, category="Landmark"),
        ]
    )
    day1 = DayPlan(day_number=1, date=date(2026, 9, 1), items=[])
    day2 = DayPlan(day_number=2, date=date(2026, 9, 2), items=items_day2, weather=weather)
    day3 = DayPlan(day_number=3, date=date(2026, 9, 3), items=[])
    return Itinerary(
        preferences=_prefs(must_see=must_see or [], budget_total=budget_total),
        days=[day1, day2, day3],
        hotel=_hotel(),
    )


# --- feasibility -------------------------------------------------------------


def test_feasibility_is_ten_when_no_conflicts():
    itinerary = _full_day_itinerary()
    report = _evaluator(conflicts=[]).evaluate(itinerary)
    assert report.scores_by_name["feasibility"] == 10.0


def test_feasibility_penalizes_each_conflict():
    conflicts = [
        Conflict(day_number=2, conflict_type="overlap", description="x"),
        Conflict(day_number=2, conflict_type="impossible_travel", description="y"),
    ]
    itinerary = _full_day_itinerary()
    report = _evaluator(conflicts=conflicts).evaluate(itinerary)
    assert report.scores_by_name["feasibility"] == 6.0  # 10 - 2*2


def test_feasibility_never_goes_below_zero():
    conflicts = [Conflict(day_number=2, conflict_type="overlap", description="x")] * 10
    itinerary = _full_day_itinerary()
    report = _evaluator(conflicts=conflicts).evaluate(itinerary)
    assert report.scores_by_name["feasibility"] == 0.0


# --- budget_accuracy ----------------------------------------------------------


def test_budget_accuracy_none_when_no_budget_stated():
    itinerary = _full_day_itinerary(budget_total=None)
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["budget_accuracy"] is None


def test_budget_accuracy_high_when_spend_matches_budget():
    # hotel: 100/night * 2 nights = 200; no other costs -> total 200
    itinerary = _full_day_itinerary(budget_total=200)
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["budget_accuracy"] == 10.0


def test_budget_accuracy_lower_when_spend_is_far_from_budget():
    itinerary = _full_day_itinerary(budget_total=10000)
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["budget_accuracy"] < 5.0


# --- weather_match -------------------------------------------------------------


def test_weather_match_none_when_no_forecast_anywhere():
    itinerary = _full_day_itinerary(weather=None)
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["weather_match"] is None


def test_weather_match_scored_when_forecast_present():
    forecast = WeatherForecast(
        day=date(2026, 9, 2),
        condition="Clear",
        temp_high_c=22,
        temp_low_c=14,
        rain_probability=0.1,
        wind_speed_kph=10,
        comfort_score=9.0,
    )
    items = [_attraction_item("Central Park", category="Park")]
    itinerary = _full_day_itinerary(items_day2=items, weather=forecast)
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["weather_match"] == 10.0  # outdoor matched to good weather


# --- completeness -------------------------------------------------------------


def test_completeness_full_when_both_slots_filled_and_no_must_see():
    itinerary = _full_day_itinerary()
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["completeness"] == 10.0


def test_completeness_penalized_when_slots_missing():
    itinerary = _full_day_itinerary(items_day2=[_attraction_item("Louvre")])
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["completeness"] == 0.0


def test_completeness_factors_in_must_see_coverage():
    itinerary = _full_day_itinerary(must_see=["Louvre", "Colosseum"])  # only Louvre scheduled
    report = _evaluator().evaluate(itinerary)
    # slot_fill_rate=1.0 (both slots filled), must_see_rate=0.5 -> 10*(0.5*1 + 0.5*0.5) = 7.5
    assert report.scores_by_name["completeness"] == 7.5


def test_completeness_vacuously_complete_with_no_full_days():
    day1 = DayPlan(day_number=1, date=date(2026, 9, 1), items=[])
    itinerary = Itinerary(preferences=_prefs(duration=1), days=[day1], hotel=_hotel())
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["completeness"] == 10.0


# --- variety -------------------------------------------------------------


def test_variety_full_when_all_categories_distinct():
    items = [
        _attraction_item("Louvre", category="Museum"),
        _attraction_item("Eiffel Tower", category="Landmark"),
    ]
    itinerary = _full_day_itinerary(items_day2=items)
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["variety"] == 10.0


def test_variety_low_when_categories_repeat():
    items = [
        _attraction_item("Louvre", category="Museum"),
        _attraction_item("Orsay", category="Museum"),
    ]
    itinerary = _full_day_itinerary(items_day2=items)
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["variety"] == 5.0


def test_variety_none_when_no_attractions_scheduled():
    itinerary = _full_day_itinerary(items_day2=[_restaurant_item()])
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["variety"] is None


# --- geo_efficiency -------------------------------------------------------------


def test_geo_efficiency_none_with_fewer_than_two_attractions():
    itinerary = _full_day_itinerary(items_day2=[_attraction_item("Louvre")])
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["geo_efficiency"] is None


def test_geo_efficiency_scored_when_enough_attractions_present():
    itinerary = _full_day_itinerary()
    report = _evaluator().evaluate(itinerary)
    assert report.scores_by_name["geo_efficiency"] is not None
    assert 0.0 <= report.scores_by_name["geo_efficiency"] <= 10.0


# --- llm-judged dimensions -----------------------------------------------------


def test_llm_judged_dimensions_present_with_correct_scores():
    itinerary = _full_day_itinerary()
    report = _evaluator(judge_scores=DEFAULT_JUDGE_SCORES).evaluate(itinerary)
    scores = report.scores_by_name
    assert scores["personalization_fit"] == 7.0
    assert scores["narrative_quality"] == 8.0
    assert scores["practicality"] == 6.0
    assert scores["overall_satisfaction"] == 7.0


def test_llm_judged_dimensions_carry_explanation():
    itinerary = _full_day_itinerary()
    report = _evaluator().evaluate(itinerary)
    llm_dims = [d for d in report.dimensions if d.method == "llm_judge"]
    assert len(llm_dims) == 4
    assert all(d.explanation == "Reasonable plan overall." for d in llm_dims)


# --- overall report -------------------------------------------------------------


def test_report_has_ten_dimensions():
    itinerary = _full_day_itinerary()
    report = _evaluator().evaluate(itinerary)
    assert len(report.dimensions) == 10


def test_overall_score_excludes_none_dimensions_from_average():
    # no budget, no weather -> those two dimensions are None and shouldn't
    # drag the average down to zero or otherwise be counted
    itinerary = _full_day_itinerary(budget_total=None, weather=None)
    report = _evaluator().evaluate(itinerary)
    scored = [d.score for d in report.dimensions if d.score is not None]
    assert report.overall_score == sum(scored) / len(scored)
    assert len(scored) == 8  # 10 dimensions minus budget_accuracy and weather_match


def test_scenario_label_is_preserved():
    itinerary = _full_day_itinerary()
    report = _evaluator().evaluate(itinerary, scenario_label="Paris backpacker trip")
    assert report.scenario_label == "Paris backpacker trip"
