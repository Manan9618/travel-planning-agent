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

import re
from datetime import date

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from travel_agent.config import settings
from travel_agent.models.core import BudgetTier, Pace, TravelPreferences, TripStyle
from travel_agent.observability.metrics import record_llm_usage
from travel_agent.utils.semantic_cache import SemanticCache

_DIGIT_RE = re.compile(r"\d+")
# Rough proper-noun heuristic (capitalized words) - imperfect (it also
# catches an ordinary sentence-initial capital, e.g. "Two of us..."), but
# that only ever makes the guard MORE restrictive (an extra token to match),
# never less safe. Needed because embedding similarity alone can't be
# trusted to separate "Paris" from "Tokyo" - see the guard docstring below
# and `SemanticCache`'s DEFAULT_SIMILARITY_THRESHOLD comment for the real
# numbers from live-testing that motivated this.
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z]*\b")

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
    # travelers/budget_currency/pace default to None here, NOT TravelPreferences's
    # real defaults (1/"USD"/MODERATE) - Week 21 fix for a real bug found
    # live-testing incremental refinement: with a concrete non-None default, these
    # three fields were indistinguishable in parse_partial()'s output between "the
    # LLM found this" and "the LLM found nothing, the default filled in", so
    # /refine's `updates` filter (`v not in (None, [], {}, "")`) could never
    # exclude them - every single refinement silently reset travelers to 1,
    # budget_currency to "USD", and pace to "moderate" in the merged preferences,
    # even when the refinement had nothing to do with any of them (and, once Week
    # 21 added invalidation-by-changed-field, spuriously re-ran search_hotels on
    # every refinement too, since it's keyed on "travelers"). parse() below
    # applies TravelPreferences's real defaults itself when these come back None.
    travelers: int | None = Field(default=None, ge=1, le=20)
    budget_total: float | None = Field(default=None, ge=0)
    budget_currency: str | None = Field(default=None)
    budget_tier: BudgetTier | None = None
    trip_style: TripStyle | None = None
    pace: Pace | None = Field(default=None)
    interests: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    accessibility_needs: list[str] = Field(default_factory=list)
    priority_weights: dict[str, float] = Field(default_factory=dict)


class PreferenceParser:
    """Wraps an LLM with structured output to turn free text into `TravelPreferences`."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
        semantic_cache: SemanticCache | None = None,
    ) -> None:
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
        # Week 20: catches paraphrases of the same request ("5 days in Paris
        # under $3000" vs "a five-day Paris trip, $3000 budget") that exact
        # caching would miss, without an extra network round trip on a miss
        # (embedding happens locally in this call, same request either way).
        # text-embedding-3-small: cheap enough (~$0.02/1M tokens) that even a
        # 100% miss rate costs far less than the LLM call it might save.
        self._embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", api_key=settings.openai_api_key or None
        )
        self._semantic_cache = semantic_cache or SemanticCache(
            "preference_parser", embed=lambda text: self._embeddings.embed_query(text)
        )

    @staticmethod
    def _cache_guard(text: str, reference_date: date) -> str:
        """A semantic-cache hit is only safe when it can't silently swap in
        the wrong destination, budget, or date - two texts embedding as
        "similar" doesn't mean any of those actually match (live-tested:
        "5 days in Paris under $3000" vs "5 days in Tokyo under $3000"
        scored ~0.78 cosine similarity, uncomfortably close to ~0.82 for a
        genuine same-trip paraphrase - see SemanticCache's threshold
        comment). Digits and capitalized words (city/month names, in
        practice) are compared as sets, not raw substrings, so word order
        doesn't matter but the actual facts must. `reference_date` is
        included because the same text ("next month") resolves to a
        different real date on a different day."""
        digits = sorted(set(_DIGIT_RE.findall(text)))
        proper_nouns = sorted({w.lower() for w in _PROPER_NOUN_RE.findall(text)})
        return f"{reference_date.isoformat()}:{','.join(digits)}:{','.join(proper_nouns)}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _invoke(self, text: str, reference_date: date) -> _ParsedFields:
        guard = self._cache_guard(text, reference_date)
        if cached := self._semantic_cache.get(text, guard=guard):
            return _ParsedFields(**cached)

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
        self._semantic_cache.set(text, parsed.model_dump(mode="json"), guard=guard)
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
        # Drop None values (travelers/budget_currency/pace when the LLM found no
        # signal for them - see _ParsedFields's docstring comment) so
        # TravelPreferences's OWN defaults (1/"USD"/MODERATE) apply, same as
        # always omitting the key would - `_ParsedFields` no longer carries
        # those defaults itself.
        fields = {k: v for k, v in parsed.model_dump().items() if v is not None}
        return TravelPreferences(**fields, raw_text=text)

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
