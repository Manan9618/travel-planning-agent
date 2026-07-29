"""RestaurantFinderTool — Week 3 deliverable.

Backed by Serper's /places endpoint, same as AttractionFinderTool. Restaurant
listings additionally carry a `priceLevel` string (e.g. "€20-40" or "$$"), which is
parsed into the model's 1-4 `price_level` bucket.
"""

from __future__ import annotations

import logging
import re

from travel_agent.config import settings
from travel_agent.models.core import Restaurant
from travel_agent.utils.cache import Cache
from travel_agent.utils.http import TransientError, post_json

logger = logging.getLogger(__name__)

PLACES_URL = "https://google.serper.dev/places"
CACHE_TTL_SECONDS = 24 * 3600

_SYMBOL_RE = re.compile(r"^[€$£¥]+$")
_NUMBER_RE = re.compile(r"\d+")

# Rough per-person cost estimate for each price_level bucket, used by ItineraryBuilder
# / ConflictDetector to include meals in budget calculations. Restaurant only carries
# the 1-4 bucket, never a real dollar amount, so this is an estimate, not a quote.
MEAL_COST_ESTIMATES: dict[int, float] = {1: 15.0, 2: 30.0, 3: 55.0, 4: 90.0}


def estimate_meal_cost(price_level: int) -> float:
    return MEAL_COST_ESTIMATES.get(price_level, 30.0)


def _parse_price_level(price_level: str | None) -> int:
    """Map Serper's free-text priceLevel (e.g. "€20-40", "$$") to a 1-4 bucket."""
    if not price_level:
        return 2
    stripped = price_level.strip()
    if _SYMBOL_RE.match(stripped):
        return max(1, min(4, len(stripped)))
    numbers = [int(n) for n in _NUMBER_RE.findall(stripped)]
    if not numbers:
        return 2
    avg = sum(numbers) / len(numbers)
    if avg < 15:
        return 1
    if avg < 30:
        return 2
    if avg < 60:
        return 3
    return 4


class RestaurantFinderTool:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None) -> None:
        self._api_key = api_key or settings.serper_api_key
        self._cache = cache or Cache()

    def search(
        self,
        location: str,
        cuisine: str | None = None,
        max_results: int = 10,
    ) -> list[Restaurant]:
        """Return up to `max_results` restaurants in `location`, highest-rated first."""
        cache_key = f"restaurants:{location}:{cuisine}:{max_results}"
        if cached := self._cache.get(cache_key):
            return [Restaurant(**item) for item in cached]

        query = (
            f"best {cuisine} restaurants in {location}"
            if cuisine
            else f"best restaurants in {location}"
        )
        try:
            places = self._fetch_places(query)
        except TransientError as exc:
            logger.warning("Serper places search failed for %r: %s", query, exc)
            places = []

        results: list[Restaurant] = []
        for place in places:
            try:
                results.append(
                    Restaurant(
                        name=place["title"],
                        cuisine=place.get("category", cuisine),
                        lat=place["latitude"],
                        lng=place["longitude"],
                        rating=place.get("rating"),
                        price_level=_parse_price_level(place.get("priceLevel")),
                    )
                )
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping malformed restaurant entry: %s", exc)

        if not results:
            logger.warning("No restaurants found for %s; falling back to mock data", location)
            results = self._mock_restaurants(location, cuisine)

        final = sorted(results, key=lambda r: r.rating or 0, reverse=True)[:max_results]
        self._cache.set(cache_key, [r.model_dump(mode="json") for r in final], CACHE_TTL_SECONDS)
        return final

    def _fetch_places(self, query: str) -> list[dict]:
        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        body = post_json(PLACES_URL, {"q": query}, headers=headers)
        return body.get("places", [])

    def _mock_restaurants(self, location: str, cuisine: str | None) -> list[Restaurant]:
        return [
            Restaurant(
                name=f"{location} Mock Restaurant {i + 1}",
                cuisine=cuisine or "International",
                lat=0.0,
                lng=0.0,
                rating=4.0 + i * 0.1,
                price_level=2,
                is_mock_data=True,
            )
            for i in range(5)
        ]
