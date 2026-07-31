"""HotelSearchTool — Week 2 deliverable.

Backed by the Booking.com API on RapidAPI (host: booking-com15.p.rapidapi.com), which
requires a two-step lookup: resolve a free-text location to a `dest_id` via
`searchDestination`, then query `searchHotels` with that id and stay dates.

The API doesn't return a street address or amenities list, so `address` is
approximated as "<city>, <country>" from the destination lookup, and `amenities`
is always empty. `price_per_night` is derived from the stay's total gross price
divided by nights. On timeout, rate-limit, or empty results, falls back to
deterministic mock data tagged `is_mock_data=True` rather than raising.
"""

from __future__ import annotations

import logging
from datetime import date

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from travel_agent.config import settings
from travel_agent.models.core import HotelOption
from travel_agent.utils.cache import Cache

logger = logging.getLogger(__name__)

HOST = "booking-com15.p.rapidapi.com"
BASE_URL = f"https://{HOST}"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
CACHE_TTL_SECONDS = 24 * 3600
TIMEOUT = 10


class _TransientError(Exception):
    """Raised for retryable failures (timeouts, connection errors, 429/5xx)."""


class HotelSearchTool:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None) -> None:
        self._api_key = api_key or settings.booking_rapidapi_key
        self._cache = cache or Cache()

    def search(
        self,
        location: str,
        check_in: date,
        check_out: date,
        adults: int = 1,
        rooms: int = 1,
        max_results: int = 10,
        max_price_per_night: float | None = None,
    ) -> list[HotelOption]:
        """Return up to `max_results` hotel options in `location`, cheapest first."""
        cache_key = (
            f"hotels:{location}:{check_in}:{check_out}:{adults}:{rooms}:"
            f"{max_results}:{max_price_per_night}"
        )
        if cached := self._cache.get(cache_key):
            return [HotelOption(**item) for item in cached]

        try:
            results = self._fetch(location, check_in, check_out, adults, rooms)
        except _TransientError as exc:
            logger.warning("Booking.com hotel search failed: %s", exc)
            results = []

        if max_price_per_night is not None:
            results = [h for h in results if h.price_per_night <= max_price_per_night]

        if not results:
            logger.warning(
                "No hotel results for %s (%s -> %s); falling back to mock data",
                location,
                check_in,
                check_out,
            )
            results = self._mock_hotels(location, check_in, check_out)

        final = sorted(results, key=lambda h: h.price_per_night)[:max_results]
        self._cache.set(cache_key, [h.model_dump(mode="json") for h in final], CACHE_TTL_SECONDS)
        return final

    # --- data source -----------------------------------------------------

    def _fetch(
        self, location: str, check_in: date, check_out: date, adults: int, rooms: int
    ) -> list[HotelOption]:
        dest = self._search_destination(location)
        if dest is None:
            return []
        return self._search_hotels(dest, check_in, check_out, adults, rooms)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(_TransientError),
        reraise=True,
    )
    def _search_destination(self, location: str) -> dict | None:
        body = self._get(f"{BASE_URL}/api/v1/hotels/searchDestination", {"query": location})
        if not body.get("status") or not body.get("data"):
            return None
        return next((d for d in body["data"] if d.get("dest_type") == "city"), body["data"][0])

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(_TransientError),
        reraise=True,
    )
    def _search_hotels(
        self, dest: dict, check_in: date, check_out: date, adults: int, rooms: int
    ) -> list[HotelOption]:
        params = {
            "dest_id": dest["dest_id"],
            "search_type": dest["search_type"].upper(),
            "adults": adults,
            "room_qty": rooms,
            "page_number": 1,
            "units": "metric",
            "temperature_unit": "c",
            "languagecode": "en-us",
            "currency_code": "USD",
            "arrival_date": check_in.isoformat(),
            "departure_date": check_out.isoformat(),
        }
        body = self._get(f"{BASE_URL}/api/v1/hotels/searchHotels", params)
        if not body.get("status"):
            return []

        nights = max((check_out - check_in).days, 1)
        location_label = f"{dest.get('city_name', dest.get('name', ''))}, {dest.get('country', '')}"
        results: list[HotelOption] = []
        for hotel in body.get("data", {}).get("hotels", []):
            try:
                prop = hotel["property"]
                gross = prop["priceBreakdown"]["grossPrice"]
                results.append(
                    HotelOption(
                        name=prop["name"],
                        address=location_label,
                        lat=prop["latitude"],
                        lng=prop["longitude"],
                        rating=prop.get("reviewScore"),
                        price_per_night=round(gross["value"] / nights, 2),
                        currency=gross.get("currency", "USD"),
                        amenities=[],
                    )
                )
            except (KeyError, TypeError, ZeroDivisionError) as exc:
                logger.warning("Skipping malformed hotel entry: %s", exc)
        return results

    def _get(self, url: str, params: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": HOST,
            "x-rapidapi-key": self._api_key,
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise _TransientError(str(exc)) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _TransientError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            logger.warning(
                "Booking.com API returned HTTP %s: %s", resp.status_code, resp.text[:200]
            )
            return {}
        return resp.json()

    # --- fallback -----------------------------------------------------

    def _mock_hotels(self, location: str, check_in: date, check_out: date) -> list[HotelOption]:
        lat, lng = self._geocode_fallback(location)
        base_price = 90.0
        mocks = []
        for i in range(5):
            mocks.append(
                HotelOption(
                    name=f"{location} Mock Hotel {i + 1}",
                    address=f"Mock Address {i + 1}, {location}",
                    lat=lat,
                    lng=lng,
                    rating=7.0 + i * 0.4,
                    price_per_night=base_price + i * 35,
                    currency="USD",
                    amenities=["wifi", "breakfast"] if i % 2 == 0 else ["wifi"],
                    is_mock_data=True,
                )
            )
        return mocks

    def _geocode_fallback(self, location: str) -> tuple[float, float]:
        """Best-effort city-center coordinates for the mock-hotel fallback.

        Previously hardcoded to (0.0, 0.0) ("Null Island") — harmless-looking,
        but it silently broke every distance calculation anchored on the
        hotel (explaining recurring Distance Matrix "ZERO_RESULTS" fallbacks
        seen in live tests since Week 9) and skewed any map centered on the
        itinerary (found while visually inspecting Week 13's map thumbnails).
        Reuses the Google Maps API key already authenticated for Distance
        Matrix rather than adding a new provider/credential. A single
        best-effort attempt, no retries: this only runs after the primary
        Booking.com lookup has already failed, so it shouldn't add its own
        retry delay on top before falling back to (0.0, 0.0) as a last resort.
        """
        try:
            resp = requests.get(
                GEOCODE_URL,
                params={"address": location, "key": settings.google_maps_api_key},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if results:
                loc = results[0]["geometry"]["location"]
                return loc["lat"], loc["lng"]
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            logger.warning("Geocoding fallback failed for %s: %s", location, exc)
        return 0.0, 0.0
