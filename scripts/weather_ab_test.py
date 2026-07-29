#!/usr/bin/env python3
"""Week 7 deliverable: A/B test comparing itinerary quality with vs without
weather-aware scheduling, across 10 diverse destinations.

Attraction data is real (via AttractionFinderTool/Serper). Weather is a
synthesized, controlled good/bad/good/bad pattern rather than the live forecast:
the free-tier forecast horizon is only ~5 days and today's real conditions might
happen to be uniformly good everywhere, which wouldn't meaningfully exercise the
indoor/outdoor swap logic. The point here is to evaluate the SCHEDULING
algorithm against known conditions, not to re-validate WeatherCheckerTool itself
(already covered by Week 3's tests).

For each destination, the same attraction pool and weather pattern are used to
build two itineraries: one blind to weather, one weather-aware. Both are then
scored with the same `weather_adaptation_rate` metric — the baseline's days are
retroactively tagged with the same forecasts purely for scoring, since it never
saw them during construction.

Usage:
    poetry run python scripts/weather_ab_test.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, "src")

from travel_agent.models.core import (
    HotelOption,
    Itinerary,
    TravelPreferences,
    WeatherForecast,
)  # noqa: E402
from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.itinerary_builder import ItineraryBuilder  # noqa: E402
from travel_agent.tools.restaurant_finder import RestaurantFinderTool  # noqa: E402
from travel_agent.tools.weather_matcher import weather_adaptation_rate  # noqa: E402

DESTINATIONS = [
    "Paris",
    "London",
    "Tokyo",
    "Rome",
    "Barcelona",
    "Amsterdam",
    "Berlin",
    "Vienna",
    "Prague",
    "Dublin",
]

TRIP_START = date.today() + timedelta(days=60)
TRIP_LENGTH_DAYS = 6  # -> 4 full days in the middle, where attractions get scheduled


def _mock_hotel(destination: str) -> HotelOption:
    return HotelOption(
        name=f"{destination} Hotel", address=destination, lat=0.0, lng=0.0, price_per_night=100
    )


def _weather_pattern(start: date, num_days: int) -> list[WeatherForecast]:
    """Alternating good/bad days, so the swap logic has real work to do."""
    forecasts = []
    for i in range(num_days):
        bad = i % 2 == 1
        forecasts.append(
            WeatherForecast(
                day=start + timedelta(days=i),
                condition="Rain" if bad else "Clear",
                temp_high_c=15 if bad else 24,
                temp_low_c=10 if bad else 16,
                rain_probability=0.85 if bad else 0.05,
                wind_speed_kph=25 if bad else 8,
                comfort_score=3.0 if bad else 9.5,
            )
        )
    return forecasts


def _tag_with_weather_for_scoring(itinerary: Itinerary, weather: list[WeatherForecast]) -> None:
    """Attach forecasts to a baseline itinerary purely so it can be scored against
    the same conditions the weather-aware version saw during construction."""
    by_date = {w.day: w for w in weather}
    for day in itinerary.days:
        day.weather = by_date.get(day.date)


def run_scenario(destination: str) -> tuple[float | None, float | None]:
    prefs = TravelPreferences(
        destination=destination,
        start_date=TRIP_START,
        duration_days=TRIP_LENGTH_DAYS,
        raw_text=f"trip to {destination}",
    )
    attractions = AttractionFinderTool().search(destination, max_results=10)
    restaurants = RestaurantFinderTool().search(destination, max_results=10)
    hotel = _mock_hotel(destination)
    weather = _weather_pattern(TRIP_START, TRIP_LENGTH_DAYS)

    builder = ItineraryBuilder()
    baseline = builder.build(prefs, hotel, attractions, restaurants, weather=None)
    _tag_with_weather_for_scoring(baseline, weather)
    treatment = builder.build(prefs, hotel, attractions, restaurants, weather=weather)

    return weather_adaptation_rate(baseline), weather_adaptation_rate(treatment)


def main() -> int:
    print(f"{'Destination':<15} {'Baseline':>10} {'Weather-Aware':>15} {'Improvement':>13}")
    print("-" * 56)

    baseline_rates: list[float] = []
    treatment_rates: list[float] = []

    for destination in DESTINATIONS:
        baseline_rate, treatment_rate = run_scenario(destination)
        b_display = f"{baseline_rate:.0%}" if baseline_rate is not None else "n/a"
        t_display = f"{treatment_rate:.0%}" if treatment_rate is not None else "n/a"
        if baseline_rate is not None:
            baseline_rates.append(baseline_rate)
        if treatment_rate is not None:
            treatment_rates.append(treatment_rate)
        improvement = (
            f"{(treatment_rate - baseline_rate):+.0%}"
            if baseline_rate is not None and treatment_rate is not None
            else "n/a"
        )
        print(f"{destination:<15} {b_display:>10} {t_display:>15} {improvement:>13}")

    print("-" * 56)
    if baseline_rates and treatment_rates:
        avg_baseline = sum(baseline_rates) / len(baseline_rates)
        avg_treatment = sum(treatment_rates) / len(treatment_rates)
        print(
            f"{'AVERAGE':<15} {avg_baseline:>10.0%} {avg_treatment:>15.0%} "
            f"{avg_treatment - avg_baseline:>+13.0%}"
        )
    else:
        print("No scenarios produced scoreable data (no non-ambiguous attractions found).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
