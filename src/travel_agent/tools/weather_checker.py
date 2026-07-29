"""WeatherCheckerTool — Week 3 deliverable.

Uses OpenWeatherMap's free-tier /data/2.5/forecast (3-hour steps, ~5 days ahead) rather
than One Call 3.0, which requires a separate paid subscription even at low volume. The
3-hour entries are aggregated into one WeatherForecast per calendar day.

Unlike the search tools, there is no mock-data fallback here: weather genuinely can't be
guessed, and dates beyond the ~5-day horizon simply have no forecast available. Both
cases return fewer days than requested rather than inventing conditions.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import UTC, date, datetime

from travel_agent.config import settings
from travel_agent.models.core import WeatherForecast
from travel_agent.utils.cache import Cache
from travel_agent.utils.http import TransientError, get_json

logger = logging.getLogger(__name__)

GEO_URL = "http://api.openweathermap.org/geo/1.0/direct"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
CACHE_TTL_SECONDS = 3 * 3600  # forecasts change; keep this short-lived


class WeatherCheckerTool:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None) -> None:
        self._api_key = api_key or settings.openweathermap_api_key
        self._cache = cache or Cache()

    def get_forecast(
        self, location: str, start_date: date, end_date: date
    ) -> list[WeatherForecast]:
        """Return one WeatherForecast per day in [start_date, end_date] that's within
        the provider's forecast horizon (~5 days out). Days beyond that are simply
        omitted, not guessed.
        """
        cache_key = f"weather:{location}:{start_date}:{end_date}"
        if cached := self._cache.get(cache_key):
            return [WeatherForecast(**item) for item in cached]

        try:
            coords = self._geocode(location)
        except TransientError as exc:
            logger.warning("Geocoding failed for %s: %s", location, exc)
            return []
        if coords is None:
            logger.warning("No geocoding match for %s; cannot fetch weather", location)
            return []

        try:
            entries = self._fetch_forecast(*coords)
        except TransientError as exc:
            logger.warning("OpenWeatherMap forecast failed for %s: %s", location, exc)
            return []

        daily = self._aggregate_daily(entries)
        results = [d for d in daily if start_date <= d.day <= end_date]

        requested_days = (end_date - start_date).days + 1
        if len(results) < requested_days:
            logger.info(
                "Only %d of %d requested days have a forecast for %s (provider horizon ~5 days)",
                len(results),
                requested_days,
                location,
            )

        self._cache.set(cache_key, [r.model_dump(mode="json") for r in results], CACHE_TTL_SECONDS)
        return results

    def _geocode(self, location: str) -> tuple[float, float] | None:
        body = get_json(GEO_URL, {"q": location, "limit": 1, "appid": self._api_key})
        if not body:
            return None
        return body[0]["lat"], body[0]["lon"]

    def _fetch_forecast(self, lat: float, lon: float) -> list[dict]:
        body = get_json(
            FORECAST_URL,
            {"lat": lat, "lon": lon, "appid": self._api_key, "units": "metric"},
        )
        return body.get("list", [])

    @staticmethod
    def _aggregate_daily(entries: list[dict]) -> list[WeatherForecast]:
        by_day: dict[date, list[dict]] = defaultdict(list)
        for entry in entries:
            day = datetime.fromtimestamp(entry["dt"], tz=UTC).date()
            by_day[day].append(entry)

        forecasts = []
        for day, day_entries in sorted(by_day.items()):
            temp_high = max(e["main"]["temp_max"] for e in day_entries)
            temp_low = min(e["main"]["temp_min"] for e in day_entries)
            rain_probability = max(e.get("pop", 0.0) for e in day_entries)
            wind_kph = max(e["wind"]["speed"] for e in day_entries) * 3.6
            conditions = [e["weather"][0]["main"] for e in day_entries if e.get("weather")]
            condition = Counter(conditions).most_common(1)[0][0] if conditions else "Unknown"
            forecasts.append(
                WeatherForecast(
                    day=day,
                    condition=condition,
                    temp_high_c=temp_high,
                    temp_low_c=temp_low,
                    rain_probability=min(rain_probability, 1.0),
                    wind_speed_kph=wind_kph,
                    comfort_score=WeatherCheckerTool._comfort_score(
                        temp_high, rain_probability, wind_kph
                    ),
                )
            )
        return forecasts

    @staticmethod
    def _comfort_score(temp_high_c: float, rain_probability: float, wind_kph: float) -> float:
        """Higher is better for outdoor activities. Ideal range ~15-28C, low rain/wind."""
        score = 10.0
        if temp_high_c < 10 or temp_high_c > 33:
            score -= 4
        elif temp_high_c < 15 or temp_high_c > 28:
            score -= 2
        score -= rain_probability * 5
        if wind_kph > 40:
            score -= 3
        elif wind_kph > 25:
            score -= 1
        return max(0.0, min(10.0, round(score, 1)))
