"""PreferenceParser v1 — extracts structured TravelPreferences from natural language.

Week 1 deliverable: 'I want to visit Paris for 5 days in July under $3000' -> TravelPreferences.

Post-Week-16 addition: `parse_partial()`, for the `/refine` endpoint. A refinement
like "more outdoor activities" mentions no destination at all, and `_ParsedFields.
destination` used to be a required field — the LLM correctly left it out per its own
system-prompt instructions ("never invent a destination... not stated"), which made
the structured-output call itself raise a pydantic ValidationError deep inside
LangChain, an unhandled 500 that the frontend surfaced as a bare "Load failed".
`destination` is now optional on `_ParsedFields`; `parse()` (used for a brand-new
`/plan` request, which must have a real destination) still enforces it explicitly,
while `parse_partial()` (used for `/refine`, which only overlays whatever the LLM
was confident about onto the existing session's preferences) does not.
"""

from __future__ import annotations

from datetime import date

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from travel_agent.config import settings
from travel_agent.models.core import BudgetTier, Pace, TravelPreferences, TripStyle
from travel_agent.observability.metrics import record_llm_usage

_SYSTEM_PROMPT = """You extract structured travel-planning details from a user's natural \
language request. Today's date is {today}. Resolve relative dates ("next month", "in July", \
"for a week starting Friday") against today's date, choosing the nearest future occurrence. \
Only fill fields you can reasonably infer; leave others empty. Never invent a destination, \
budget, or date that was not stated or clearly implied."""


class _ParsedFields(BaseModel):
    """LLM-facing schema. Mirrors TravelPreferences minus fields we fill in ourselves."""

    origin: str | None = Field(default=None, description="Departure city or airport")
    destination: str | None = Field(default=None, description="Primary destination city or region")
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
        self._model = model or settings.openai_model
        self._llm = ChatOpenAI(
            model=self._model,
            temperature=temperature,
            api_key=settings.openai_api_key or None,
            # include_raw=True (Week 19): with_structured_output() normally
            # returns just the parsed schema instance, discarding the raw
            # AIMessage - and with it, usage_metadata, needed for cost
            # tracking. include_raw=True returns {"raw", "parsed",
            # "parsing_error"} instead and stops raising on a parse failure
            # (parsed is None instead) - the explicit check below restores
            # the original raise-on-failure behavior tenacity's retry here
            # depends on.
        ).with_structured_output(_ParsedFields, include_raw=True)

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
        response = self._llm.invoke(messages)
        parsed = response.get("parsed") if isinstance(response, dict) else None
        if not isinstance(parsed, _ParsedFields):
            raise ValueError("LLM did not return structured output")
        raw = response.get("raw")
        if raw is not None:
            record_llm_usage(self._model, getattr(raw, "usage_metadata", None))
        return parsed

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
        if not parsed.destination:
            raise ValueError("Could not determine a destination from the request")
        return TravelPreferences(**parsed.model_dump(), raw_text=text)

    def parse_partial(self, text: str, reference_date: date | None = None) -> dict:
        """Parse a *partial* update from a refinement request (e.g. "less walking",
        "more outdoor activities") — unlike `parse()`, does not require a destination,
        since a refinement rarely restates the whole trip. Returns a raw field dict for
        the caller to merge over the session's existing preferences; fields the LLM
        wasn't confident enough to fill in come back as None/empty and should be
        treated as "unchanged" by the caller.
        """
        if not text or not text.strip():
            raise ValueError("text must be a non-empty travel request")

        reference_date = reference_date or date.today()
        parsed = self._invoke(text, reference_date)
        return parsed.model_dump(mode="json")
