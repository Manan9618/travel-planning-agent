"""Minimal travel-time helper — used by ItineraryBuilder (Week 5) for buffers between
consecutive activities. A full NxN DistanceMatrixTool with batch queries and
clustering support is a separate, larger deliverable (Week 9); this is deliberately
just a single-pair lookup so Week 5 doesn't have to wait on that.
"""

from __future__ import annotations

import logging

from travel_agent.config import settings
from travel_agent.utils.cache import Cache
from travel_agent.utils.http import TransientError, get_json

logger = logging.getLogger(__name__)

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
CACHE_TTL_SECONDS = 30 * 24 * 3600  # travel time between two fixed points barely changes
DEFAULT_FALLBACK_MINUTES = 30


class TravelTimeEstimator:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None) -> None:
        self._api_key = api_key or settings.google_maps_api_key
        self._cache = cache or Cache()

    def minutes_between(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        mode: str = "driving",
    ) -> int:
        """Travel time in minutes. Falls back to a flat estimate on any failure,
        rather than blocking itinerary construction on a single API hiccup.
        """
        cache_key = f"traveltime:{origin_lat},{origin_lng}:{dest_lat},{dest_lng}:{mode}"
        if (cached := self._cache.get(cache_key)) is not None:
            return cached

        try:
            body = get_json(
                DISTANCE_MATRIX_URL,
                {
                    "origins": f"{origin_lat},{origin_lng}",
                    "destinations": f"{dest_lat},{dest_lng}",
                    "mode": mode,
                    "key": self._api_key,
                },
            )
            element = body["rows"][0]["elements"][0]
            if element["status"] != "OK":
                raise ValueError(f"element status {element['status']}")
            minutes = round(element["duration"]["value"] / 60)
        except (TransientError, KeyError, IndexError, ValueError) as exc:
            logger.warning(
                "Distance Matrix lookup failed (%s); using flat %d-minute fallback",
                exc,
                DEFAULT_FALLBACK_MINUTES,
            )
            minutes = DEFAULT_FALLBACK_MINUTES

        self._cache.set(cache_key, minutes, CACHE_TTL_SECONDS)
        return minutes
