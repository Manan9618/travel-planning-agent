"""PreferenceParser v1 — extracts structured TravelPreferences from natural language.

Week 1 deliverable: 'I want to visit Paris for 5 days in July under $3000' -> TravelPreferences.
"""

from __future__ import annotations

from datetime import date

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from travel_agent.config import settings
from travel_agent.models.core import BudgetTier, Pace, TravelPreferences, TripStyle

_SYSTEM_PROMPT = """You extract structured travel-planning details from a user's natural \
language request. Today's date is {today}. Resolve relative dates ("next month", "in July", \
"for a week starting Friday") against today's date, choosing the nearest future occurrence. \
Only fill fields you can reasonably infer; leave others empty. Never invent a destination, \
budget, or date that was not stated or clearly implied."""


class _ParsedFields(BaseModel):
    """LLM-facing schema. Mirrors TravelPreferences minus fields we fill in ourselves."""

    origin: str | None = Field(default=None, description="Departure city or airport")
    destination: str = Field(description="Primary destination city or region")
    start_date: date | None = None
    end_date: date | None = None
    duration_days: int | None = Field(default=None, ge=1, le=90)
    travelers: int = Field(default=1, ge=1, le=20)
    budget_total: float | None = Field(default=None, ge=0)
    budget_currency: str = Field(default="USD")
    budget_tier: BudgetTier | None = None
    trip_style: TripStyle | None = None
    pace: Pace = Field(default=Pace.MODERATE)
    interests: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    accessibility_needs: list[str] = Field(default_factory=list)
    priority_weights: dict[str, float] = Field(default_factory=dict)


class PreferenceParser:
    """Wraps an LLM with structured output to turn free text into `TravelPreferences`."""

    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        self._llm = ChatOpenAI(
            model=model or settings.openai_model,
            temperature=temperature,
            api_key=settings.openai_api_key or None,
        ).with_structured_output(_ParsedFields)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _invoke(self, text: str, reference_date: date) -> _ParsedFields:
        messages = [
            ("system", _SYSTEM_PROMPT.format(today=reference_date.isoformat())),
            ("human", text),
        ]
        result = self._llm.invoke(messages)
        if not isinstance(result, _ParsedFields):
            raise ValueError("LLM did not return structured output")
        return result

    def parse(self, text: str, reference_date: date | None = None) -> TravelPreferences:
        """Parse a natural language travel request into TravelPreferences.

        Args:
            text: e.g. "I want to visit Paris for 5 days in July under $3000"
            reference_date: date to resolve relative expressions against (defaults to today)
        """
        if not text or not text.strip():
            raise ValueError("text must be a non-empty travel request")

        reference_date = reference_date or date.today()
        parsed = self._invoke(text, reference_date)
        return TravelPreferences(**parsed.model_dump(), raw_text=text)
