"""Travel-time tools: a single-pair estimator (Week 5) and a batched NxN matrix
(Week 9). Both share the same cache-key convention, so pairs computed by one are
reused by the other rather than re-fetched.
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
MAX_ELEMENTS_PER_REQUEST = 100  # Google Distance Matrix API's per-request element cap

Point = tuple[float, float]


def _pair_cache_key(origin: Point, dest: Point, mode: str) -> str:
    return f"traveltime:{origin[0]},{origin[1]}:{dest[0]},{dest[1]}:{mode}"


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
        cache_key = _pair_cache_key((origin_lat, origin_lng), (dest_lat, dest_lng), mode)
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


class DistanceMatrixTool:
    """Computes travel time between every pair in a list of points. Batches
    requests by origin (one origin against up to MAX_ELEMENTS_PER_REQUEST
    destinations per call) rather than issuing one request per pair — for N
    points that's N requests instead of N^2. Already-cached pairs (including
    ones TravelTimeEstimator computed earlier, since both share the same
    cache-key format) are never re-fetched.
    """

    def __init__(self, api_key: str | None = None, cache: Cache | None = None) -> None:
        self._api_key = api_key or settings.google_maps_api_key
        self._cache = cache or Cache()

    def compute_matrix(self, points: list[Point], mode: str = "driving") -> list[list[int]]:
        n = len(points)
        matrix = [[0] * n for _ in range(n)]
        pending_by_origin: dict[int, list[int]] = {}

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                cached = self._cache.get(_pair_cache_key(points[i], points[j], mode))
                if cached is not None:
                    matrix[i][j] = cached
                else:
                    pending_by_origin.setdefault(i, []).append(j)

        for i, dest_indices in pending_by_origin.items():
            for start in range(0, len(dest_indices), MAX_ELEMENTS_PER_REQUEST):
                chunk = dest_indices[start : start + MAX_ELEMENTS_PER_REQUEST]
                self._fetch_row(points, i, chunk, mode, matrix)

        return matrix

    def _fetch_row(
        self,
        points: list[Point],
        origin_idx: int,
        dest_indices: list[int],
        mode: str,
        matrix: list[list[int]],
    ) -> None:
        origin = points[origin_idx]
        destinations = [points[j] for j in dest_indices]
        try:
            body = get_json(
                DISTANCE_MATRIX_URL,
                {
                    "origins": f"{origin[0]},{origin[1]}",
                    "destinations": "|".join(f"{lat},{lng}" for lat, lng in destinations),
                    "mode": mode,
                    "key": self._api_key,
                },
            )
            elements = body["rows"][0]["elements"]
        except (TransientError, KeyError, IndexError) as exc:
            logger.warning(
                "Distance Matrix batch lookup failed (%s); using flat %d-minute fallback "
                "for %d pairs",
                exc,
                DEFAULT_FALLBACK_MINUTES,
                len(dest_indices),
            )
            elements = [{"status": "UNKNOWN"}] * len(dest_indices)

        for j, element in zip(dest_indices, elements, strict=False):
            if element.get("status") == "OK":
                minutes = round(element["duration"]["value"] / 60)
            else:
                minutes = DEFAULT_FALLBACK_MINUTES
            matrix[origin_idx][j] = minutes
            self._cache.set(
                _pair_cache_key(points[origin_idx], points[j], mode), minutes, CACHE_TTL_SECONDS
            )
