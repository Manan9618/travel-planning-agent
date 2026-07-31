from datetime import date

from travel_agent.models.core import (
    DayPlan,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
)
from travel_agent.tools.itinerary_judge import ItineraryJudge, JudgeScores, render_itinerary_summary


def _prefs(**overrides):
    defaults = dict(destination="Paris", start_date=date(2026, 9, 1), duration_days=3, raw_text="t")
    defaults.update(overrides)
    return TravelPreferences(**defaults)


def _itinerary_with_items():
    item = ItineraryItem(
        time_slot="morning",
        start_time="2026-09-02T09:00:00",
        end_time="2026-09-02T11:00:00",
        activity_type="attraction",
        title="Louvre Museum",
        cost=20,
    )
    day = DayPlan(day_number=2, date=date(2026, 9, 2), items=[item], warnings=["Pack rain gear"])
    hotel = HotelOption(name="Hotel", address="Paris", lat=48.85, lng=2.35, price_per_night=100)
    return Itinerary(preferences=_prefs(), days=[day], hotel=hotel)


def _judge_with_result(monkeypatch, scores: JudgeScores) -> ItineraryJudge:
    judge = ItineraryJudge()
    monkeypatch.setattr(judge, "_invoke", lambda summary: scores)
    return judge


# --- render_itinerary_summary ------------------------------------------------


def test_summary_includes_destination_and_preferences():
    prefs = _prefs(must_see=["Louvre"], interests=["art", "history"])
    itinerary = Itinerary(preferences=prefs, days=[])
    summary = render_itinerary_summary(prefs, itinerary)
    assert "Paris" in summary
    assert "Louvre" in summary
    assert "art, history" in summary


def test_summary_includes_day_items_and_costs():
    itinerary = _itinerary_with_items()
    summary = render_itinerary_summary(itinerary.preferences, itinerary)
    assert "Louvre Museum" in summary
    assert "$20" in summary


def test_summary_includes_warnings():
    itinerary = _itinerary_with_items()
    summary = render_itinerary_summary(itinerary.preferences, itinerary)
    assert "Pack rain gear" in summary


def test_summary_handles_empty_day():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[])
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    summary = render_itinerary_summary(itinerary.preferences, itinerary)
    assert "(nothing scheduled)" in summary


def test_summary_omits_budget_line_when_not_stated():
    prefs = _prefs()
    itinerary = Itinerary(preferences=prefs, days=[])
    summary = render_itinerary_summary(prefs, itinerary)
    assert "Budget:" not in summary


def test_summary_includes_budget_when_stated():
    prefs = _prefs(budget_total=1500)
    itinerary = Itinerary(preferences=prefs, days=[])
    summary = render_itinerary_summary(prefs, itinerary)
    assert "1500" in summary


# --- ItineraryJudge.judge() ---------------------------------------------------


def test_judge_returns_the_invoked_scores(monkeypatch):
    scores = JudgeScores(
        personalization_fit=8,
        narrative_quality=7,
        practicality=9,
        overall_satisfaction=8,
        explanation="Solid plan matching stated interests.",
    )
    judge = _judge_with_result(monkeypatch, scores)
    itinerary = _itinerary_with_items()
    result = judge.judge(itinerary.preferences, itinerary)
    assert result == scores


def test_judge_scores_are_bounded_by_model_validation():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JudgeScores(
            personalization_fit=11,
            narrative_quality=5,
            practicality=5,
            overall_satisfaction=5,
            explanation="out of range",
        )
