"""AttractionDescriberTool — post-Week-16: a short 2-3 sentence "why visit /
history" blurb per attraction, shown alongside its photo in both the web
itinerary UI and the PDF.

One batched GPT-4o call per itinerary (not one call per attraction) keeps
cost and latency bounded regardless of trip length, and results are cached
per (title, destination) pair — a landmark's history doesn't change, so a
long TTL is safe. Entirely optional in effect: if the LLM call fails for
any reason, every attraction simply has no description rather than
blocking planning, the same graceful-degradation pattern used by every
other optional enrichment in this project (e.g. `UnsplashPhotoTool`).
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from travel_agent.config import settings
from travel_agent.utils.cache import Cache

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30 * 24 * 3600

_SYSTEM_PROMPT = """You write short, engaging 2-3 sentence descriptions of tourist \
attractions for a travel itinerary, covering the place's history or why it's worth \
visiting. Be factual and concise. Return exactly one entry per attraction listed, \
using the exact same title given for each."""


class _AttractionDescription(BaseModel):
    title: str = Field(description="Exact attraction title, matching the input list")
    description: str = Field(description="2-3 sentence history / why-visit blurb")


class _AttractionDescriptions(BaseModel):
    attractions: list[_AttractionDescription]


class AttractionDescriberTool:
    def __init__(self, model: str | None = None, cache: Cache | None = None) -> None:
        self._llm = ChatOpenAI(
            model=model or settings.openai_model,
            temperature=0.3,
            api_key=settings.openai_api_key or None,
        ).with_structured_output(_AttractionDescriptions)
        self._cache = cache or Cache()

    def describe(self, titles: list[str], destination: str) -> dict[str, str]:
        """Return {title: description} for as many of `titles` as could be described.

        Titles already cached are served without a network call; only uncached
        titles trigger a single batched LLM call.
        """
        unique_titles = list(dict.fromkeys(t for t in titles if t))
        if not unique_titles:
            return {}

        result: dict[str, str] = {}
        uncached: list[str] = []
        for title in unique_titles:
            cached = self._cache.get(self._cache_key(title, destination))
            if cached is None:
                uncached.append(title)
            elif cached:
                result[title] = cached

        if uncached:
            fetched = self._fetch(uncached, destination)
            for title in uncached:
                description = fetched.get(title, "")
                self._cache.set(self._cache_key(title, destination), description, CACHE_TTL_SECONDS)
                if description:
                    result[title] = description

        return result

    def _fetch(self, titles: list[str], destination: str) -> dict[str, str]:
        listing = "\n".join(f"- {title}" for title in titles)
        try:
            response = self._llm.invoke(
                [
                    ("system", _SYSTEM_PROMPT),
                    ("human", f"Destination: {destination}\nAttractions:\n{listing}"),
                ]
            )
        except Exception as exc:
            logger.warning("Attraction description lookup failed for %s: %s", destination, exc)
            return {}
        if not isinstance(response, _AttractionDescriptions):
            return {}
        return {a.title: a.description for a in response.attractions}

    @staticmethod
    def _cache_key(title: str, destination: str) -> str:
        return f"attraction_description:{destination.lower()}:{title.lower()}"
