"""UnsplashPhotoTool — Week 14 deliverable: a destination cover photo for the
PDF itinerary's cover page. Generalized post-Week-16 into `get_photo`, a
lookup for an arbitrary search query, so `PDFGenerator` can also fetch a
thumbnail per attraction (e.g. "Eiffel Tower Paris"), not just one cover
photo for the whole trip.

Entirely optional: without `UNSPLASH_ACCESS_KEY` set, or if a lookup fails
for any reason (rate limit, no results, network error), the lookup returns
`None` and callers fall back gracefully (a CSS gradient cover, or simply no
thumbnail for that row) instead of leaving a broken image or blocking PDF
generation on a third-party call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from travel_agent.config import settings
from travel_agent.utils.cache import Cache
from travel_agent.utils.http import TransientError, get_json

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.unsplash.com/search/photos"
CACHE_TTL_SECONDS = 7 * 24 * 3600  # destination photos don't need to be fresh


@dataclass
class CoverPhoto:
    url: str
    photographer_name: str
    photographer_url: str


class UnsplashPhotoTool:
    def __init__(self, access_key: str | None = None, cache: Cache | None = None) -> None:
        self._access_key = access_key if access_key is not None else settings.unsplash_access_key
        self._cache = cache or Cache()

    def get_cover_photo(self, destination: str) -> CoverPhoto | None:
        return self.get_photo(f"{destination} travel landmark")

    def get_photo(self, query: str, *, thumbnail: bool = False) -> CoverPhoto | None:
        if not self._access_key:
            return None

        cache_key = f"unsplash:{'thumb:' if thumbnail else ''}{query.lower()}"
        if (cached := self._cache.get(cache_key)) is not None:
            return CoverPhoto(**cached) if cached else None

        try:
            body = get_json(
                SEARCH_URL,
                params={
                    "query": query,
                    "per_page": 1,
                    "orientation": "landscape",
                },
                headers={"Authorization": f"Client-ID {self._access_key}"},
            )
        except TransientError as exc:
            logger.warning("Unsplash lookup failed for %r: %s", query, exc)
            return None

        results = body.get("results") or []
        if not results:
            self._cache.set(cache_key, {}, CACHE_TTL_SECONDS)
            return None

        try:
            photo = results[0]
            size = "thumb" if thumbnail else "regular"
            found = CoverPhoto(
                url=photo["urls"][size],
                photographer_name=photo["user"]["name"],
                photographer_url=photo["user"]["links"]["html"],
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Malformed Unsplash response for %r: %s", query, exc)
            return None

        self._cache.set(cache_key, found.__dict__, CACHE_TTL_SECONDS)
        return found
