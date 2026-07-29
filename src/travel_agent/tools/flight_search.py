"""FlightSearchTool — Week 2 deliverable.

Backed by TravelPayouts' Data API, which (without an affiliate marker) only exposes
cached/aggregated fares rather than a live GDS search. Two endpoints are merged to get
close to "top N options with price/stops/duration":

- `/v1/prices/cheap`: at most one result per stop-count, but with a real departure
  timestamp, IATA airline code, and flight number (`has_exact_time=True`).
- `/v2/prices/latest`: many more results, but only a depart date (no time-of-day) and
  the "airline" field is actually the OTA/booking-site name (`has_exact_time=False`).

Results are merged (exact-time entries first), sorted by price, and truncated to
`max_results`. On timeout, rate-limit, or empty results from both endpoints, falls back
to deterministic mock data tagged `is_mock_data=True` rather than raising.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from travel_agent.config import settings
from travel_agent.models.core import FlightOption
from travel_agent.utils.cache import Cache

logger = logging.getLogger(__name__)

BASE_URL = "https://api.travelpayouts.com"
CACHE_TTL_SECONDS = 6 * 3600
TIMEOUT = 10


class _TransientError(Exception):
    """Raised for retryable failures (timeouts, connection errors, 429/5xx)."""


class FlightSearchTool:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None) -> None:
        self._api_key = api_key or settings.travelpayouts_api_key
        self._cache = cache or Cache()

    def search(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date | None = None,
        max_results: int = 5,
        max_price: float | None = None,
    ) -> list[FlightOption]:
        """Return up to `max_results` flight options, cheapest first.

        Args:
            origin: IATA city/airport code, e.g. "LON"
            destination: IATA city/airport code, e.g. "PAR"
            depart_date: outbound date
            return_date: inbound date, or None for a one-way search
            max_results: cap on returned options
            max_price: drop options priced above this (in the response currency, USD)
        """
        cache_key = (
            f"flights:{origin}:{destination}:{depart_date}:{return_date}:"
            f"{max_results}:{max_price}"
        )
        if cached := self._cache.get(cache_key):
            return [FlightOption(**item) for item in cached]

        try:
            exact = self._fetch_cheap(origin, destination, depart_date, return_date)
        except _TransientError as exc:
            logger.warning("TravelPayouts /prices/cheap failed: %s", exc)
            exact = []

        try:
            approx = self._fetch_latest(origin, destination, depart_date, return_date)
        except _TransientError as exc:
            logger.warning("TravelPayouts /prices/latest failed: %s", exc)
            approx = []

        seen_keys = {(f.departure_time.date(), round(f.price)) for f in exact}
        merged = exact + [
            f for f in approx if (f.departure_time.date(), round(f.price)) not in seen_keys
        ]

        if max_price is not None:
            merged = [f for f in merged if f.price <= max_price]

        if not merged:
            logger.warning(
                "No flight results for %s->%s on %s; falling back to mock data",
                origin,
                destination,
                depart_date,
            )
            merged = self._mock_flights(origin, destination, depart_date, return_date)

        results = sorted(merged, key=lambda f: f.price)[:max_results]
        self._cache.set(cache_key, [r.model_dump(mode="json") for r in results], CACHE_TTL_SECONDS)
        return results

    # --- data sources -----------------------------------------------------

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(_TransientError),
        reraise=True,
    )
    def _fetch_cheap(
        self, origin: str, destination: str, depart_date: date, return_date: date | None
    ) -> list[FlightOption]:
        params = {
            "origin": origin,
            "destination": destination,
            "depart_date": depart_date.strftime("%Y-%m"),
            "currency": "usd",
            "token": self._api_key,
        }
        if return_date:
            params["return_date"] = return_date.strftime("%Y-%m")
        body = self._get(f"{BASE_URL}/v1/prices/cheap", params)
        if not body.get("success"):
            return []

        results: list[FlightOption] = []
        for dest_data in body.get("data", {}).values():
            for stops_key, fare in dest_data.items():
                try:
                    departure_at = datetime.fromisoformat(fare["departure_at"])
                    duration_to = fare.get("duration_to", fare.get("duration", 0))
                    results.append(
                        FlightOption(
                            airline=fare.get("airline", "?"),
                            flight_number=str(fare.get("flight_number", "")) or None,
                            origin=origin,
                            destination=destination,
                            departure_time=departure_at,
                            arrival_time=departure_at + timedelta(minutes=duration_to),
                            duration_minutes=duration_to,
                            stops=int(stops_key),
                            price=float(fare["price"]),
                            currency=body.get("currency", "usd").upper(),
                            has_exact_time=True,
                        )
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("Skipping malformed /prices/cheap fare: %s", exc)
        return results

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(_TransientError),
        reraise=True,
    )
    def _fetch_latest(
        self, origin: str, destination: str, depart_date: date, return_date: date | None
    ) -> list[FlightOption]:
        params = {
            "origin": origin,
            "destination": destination,
            "currency": "usd",
            "sorting": "price",
            "limit": 20,
            "token": self._api_key,
        }
        body = self._get(f"{BASE_URL}/v2/prices/latest", params)
        if body.get("error"):
            return []

        results: list[FlightOption] = []
        for fare in body.get("data", []):
            try:
                flight_date = datetime.strptime(fare["depart_date"], "%Y-%m-%d").date()
                departure_at = datetime.combine(flight_date, time.min)
                duration = int(fare.get("duration", 0))
                results.append(
                    FlightOption(
                        airline=fare.get("gate", "Unknown"),
                        flight_number=None,
                        origin=origin,
                        destination=destination,
                        departure_time=departure_at,
                        arrival_time=departure_at + timedelta(minutes=duration),
                        duration_minutes=duration,
                        stops=int(fare.get("number_of_changes", 0)),
                        price=float(fare["value"]),
                        currency=body.get("currency", "usd").upper(),
                        has_exact_time=False,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed /prices/latest fare: %s", exc)
        return results

    def _get(self, url: str, params: dict) -> dict:
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise _TransientError(str(exc)) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _TransientError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            logger.warning("TravelPayouts returned HTTP %s: %s", resp.status_code, resp.text[:200])
            return {}
        return resp.json()

    # --- fallback -----------------------------------------------------

    def _mock_flights(
        self, origin: str, destination: str, depart_date: date, return_date: date | None
    ) -> list[FlightOption]:
        departure_at = datetime.combine(depart_date, time(hour=9))
        base_price = 250.0
        mocks = []
        for i, stops in enumerate([0, 0, 1, 1, 2]):
            dep = departure_at + timedelta(hours=i)
            mocks.append(
                FlightOption(
                    airline="MOCK",
                    flight_number=f"MK{100 + i}",
                    origin=origin,
                    destination=destination,
                    departure_time=dep,
                    arrival_time=dep + timedelta(hours=2 + stops),
                    duration_minutes=(2 + stops) * 60,
                    stops=stops,
                    price=base_price + i * 40,
                    currency="USD",
                    has_exact_time=True,
                    is_mock_data=True,
                )
            )
        return mocks
