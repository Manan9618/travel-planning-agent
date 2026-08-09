"""ItineraryJudge — Week 12 deliverable: the LLM-as-judge half of the evaluation
framework (see `evaluator.py` for the code-computed half).

Four dimensions genuinely need human-like judgment rather than a formula: does
the plan actually fit what this traveler asked for, does it read well as a
day-by-day narrative, is the pacing realistic, and would a traveler be happy
with it overall. Everything a formula CAN measure exactly (budget adherence,
conflict count, weather-matching, route efficiency, slot-fill rate, category
variety) is computed directly in `evaluator.py` instead — asking an LLM to
re-derive a fact code already knows exactly would just add noise and cost.

Uses the same GPT-4o + `with_structured_output` + retry pattern as
PreferenceParser (Week 1); the plan's own suggestion of "Claude grades the
itinerary" is substituted for GPT-4o to stay on this project's one established
LLM choice, the same kind of documented substitution as TravelPayouts for
Amadeus (Week 2) and Serper for OSM/Google Places (Week 3).
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from travel_agent.config import settings
from travel_agent.models.core import Itinerary, TravelPreferences
from travel_agent.observability.metrics import record_llm_usage

_SYSTEM_PROMPT = """You are an expert travel agent grading a day-by-day itinerary that was \
generated automatically for a client. Score it honestly on four dimensions, each 0-10 \
(0 = fails completely, 10 = excellent):

- personalization_fit: does the plan reflect the client's stated interests, trip style, \
must-see list, and pace preference?
- narrative_quality: read as a day-by-day plan — is it coherent, well-paced, and easy to \
follow, with a sensible flow of activities and meals?
- practicality: is the pacing realistic given the stated pace preference (relaxed/moderate/ \
packed) — not exhausting, not empty, with sensible timing?
- overall_satisfaction: if you were this traveler, how happy would you be with this plan?

Be a strict, critical evaluator — reserve 9-10 for genuinely excellent plans. Give a short \
(1-3 sentence) explanation covering your reasoning across all four scores."""


class JudgeScores(BaseModel):
    personalization_fit: int = Field(ge=0, le=10)
    narrative_quality: int = Field(ge=0, le=10)
    practicality: int = Field(ge=0, le=10)
    overall_satisfaction: int = Field(ge=0, le=10)
    explanation: str


def render_itinerary_summary(preferences: TravelPreferences, itinerary: Itinerary) -> str:
    """A compact, human-readable day-by-day summary — cheaper and more
    reliable for the LLM to reason over than a raw JSON dump."""
    lines = [
        f"Destination: {preferences.destination}",
        f"Trip style: {preferences.trip_style.value if preferences.trip_style else 'unspecified'}",
        f"Pace: {preferences.pace.value}",
        f"Travelers: {preferences.travelers}",
        f"Interests: {', '.join(preferences.interests) or 'none stated'}",
        f"Must-see: {', '.join(preferences.must_see) or 'none stated'}",
    ]
    if preferences.budget_total:
        lines.append(f"Budget: {preferences.budget_total:.0f} {preferences.budget_currency}")
    if preferences.dietary_restrictions:
        lines.append(f"Dietary restrictions: {', '.join(preferences.dietary_restrictions)}")
    if preferences.accessibility_needs:
        lines.append(f"Accessibility needs: {', '.join(preferences.accessibility_needs)}")

    lines.append("")
    for day in itinerary.days:
        lines.append(f"Day {day.day_number} ({day.date}):")
        if not day.items:
            lines.append("  (nothing scheduled)")
        for item in day.items:
            cost = f", ${item.cost:.0f}" if item.cost else ""
            lines.append(f"  {item.start_time.time()} [{item.activity_type}] {item.title}{cost}")
        if day.warnings:
            lines.append(f"  Warnings: {'; '.join(day.warnings)}")
    return "\n".join(lines)


class ItineraryJudge:
    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        self._model = model or settings.openai_model
        self._llm = ChatOpenAI(
            model=self._model,
            temperature=temperature,
            api_key=settings.openai_api_key or None,
            # include_raw=True (Week 19): see PreferenceParser for why.
        ).with_structured_output(JudgeScores, include_raw=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _invoke(self, summary: str) -> JudgeScores:
        messages = [("system", _SYSTEM_PROMPT), ("human", summary)]
        response = self._llm.invoke(messages)
        parsed = response.get("parsed") if isinstance(response, dict) else None
        if not isinstance(parsed, JudgeScores):
            raise ValueError("LLM did not return structured output")
        raw = response.get("raw")
        if raw is not None:
            record_llm_usage(self._model, getattr(raw, "usage_metadata", None))
        return parsed

    def judge(self, preferences: TravelPreferences, itinerary: Itinerary) -> JudgeScores:
        summary = render_itinerary_summary(preferences, itinerary)
        return self._invoke(summary)
