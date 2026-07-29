"""Weather-aware scheduling support — Week 7 deliverable.

Classifies attractions as indoor/outdoor/ambiguous from their category and name
(a keyword heuristic — neither Serper nor any other data source we use tags this
explicitly), decides whether a day counts as "bad weather" for scheduling purposes,
and measures how well a built itinerary matched activities to conditions.
"""

from __future__ import annotations

from typing import Literal

from travel_agent.models.core import Attraction, Itinerary, WeatherForecast

RAIN_PROBABILITY_THRESHOLD = 0.5
LOW_COMFORT_THRESHOLD = 5.0

Setting = Literal["indoor", "outdoor", "ambiguous"]

_INDOOR_KEYWORDS = [
    "museum",
    "gallery",
    "aquarium",
    "cathedral",
    "church",
    "basilica",
    "theatre",
    "theater",
    "opera",
    "planetarium",
    "mall",
    "shopping",
    "casino",
    "chapel",
    "synagogue",
    "mosque",
    "exhibition",
    "art center",
    "arena",
    "indoor",
]

_OUTDOOR_KEYWORDS = [
    "park",
    "garden",
    "beach",
    "trail",
    "mountain",
    "viewpoint",
    "square",
    "bridge",
    "zoo",
    "botanical",
    "waterfall",
    "hike",
    "hiking",
    "lake",
    "river",
    "cliff",
    "canyon",
    "forest",
    "vista",
    "overlook",
    "plaza",
    "harbor",
    "pier",
    "island",
    "outdoor",
]


def classify_setting(category: str | None, name: str) -> Setting:
    text = f"{category or ''} {name}".lower()
    if any(keyword in text for keyword in _INDOOR_KEYWORDS):
        return "indoor"
    if any(keyword in text for keyword in _OUTDOOR_KEYWORDS):
        return "outdoor"
    return "ambiguous"


def classify_attraction(attraction: Attraction) -> Setting:
    return classify_setting(attraction.category, attraction.name)


def is_bad_weather(forecast: WeatherForecast) -> bool:
    return (
        forecast.rain_probability >= RAIN_PROBABILITY_THRESHOLD
        or forecast.comfort_score < LOW_COMFORT_THRESHOLD
    )


def weather_adaptation_rate(itinerary: Itinerary) -> float | None:
    """% of non-ambiguous attractions scheduled on a day with weather data that
    were matched to the right setting (indoor on bad-weather days, outdoor on
    good-weather days). None if there's nothing to score (no weather data at all).
    """
    total = 0
    matched = 0
    for day in itinerary.days:
        if day.weather is None:
            continue
        wanted: Setting = "indoor" if is_bad_weather(day.weather) else "outdoor"
        for item in day.items:
            if item.activity_type != "attraction":
                continue
            setting = classify_setting(item.category, item.title)
            if setting == "ambiguous":
                continue
            total += 1
            if setting == wanted:
                matched += 1
    return matched / total if total else None
