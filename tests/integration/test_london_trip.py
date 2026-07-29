"""Week 3 deliverable: simulate a 5-day London trip using all four tools together.

Attraction/restaurant/weather HTTP calls are mocked (same as the unit suites) so this
runs offline and deterministically; BudgetTrackerTool is exercised for real since it's
pure computation. The point is to verify the tools compose into one coherent plan, not
to re-test each tool's internals (that's what the unit suites are for).
"""

from datetime import UTC, date, datetime, timedelta

import responses

from travel_agent.tools.attraction_finder import AttractionFinderTool
from travel_agent.tools.budget_tracker import BudgetTrackerTool
from travel_agent.tools.restaurant_finder import RestaurantFinderTool
from travel_agent.tools.weather_checker import WeatherCheckerTool

PLACES_URL = "https://google.serper.dev/places"
GEO_URL = "http://api.openweathermap.org/geo/1.0/direct"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

TRIP_START = date.today() + timedelta(days=10)
TRIP_END = TRIP_START + timedelta(days=4)  # 5-day trip


def _attraction(title, rating=4.5):
    return {
        "title": title,
        "address": f"{title}, London",
        "latitude": 51.5,
        "longitude": -0.1,
        "rating": rating,
        "category": "Tourist attraction",
        "cid": title,
    }


def _restaurant(title, price_level="£20-30", rating=4.5):
    return {
        "title": title,
        "address": f"{title} St, London",
        "latitude": 51.5,
        "longitude": -0.1,
        "rating": rating,
        "priceLevel": price_level,
        "category": "British",
    }


def _weather_entry(day_offset, temp_max=22, temp_min=14, pop=0.1):
    dt = (
        int((datetime.combine(TRIP_START, datetime.min.time(), tzinfo=UTC)).timestamp())
        + day_offset * 86400
    )
    return {
        "dt": dt,
        "main": {"temp_max": temp_max, "temp_min": temp_min},
        "wind": {"speed": 3.0},
        "weather": [{"main": "Clouds"}],
        "pop": pop,
    }


@responses.activate
def test_full_london_trip_planning_flow(fake_cache):
    # attractions: general query + one interest-based query
    responses.add(
        responses.POST,
        PLACES_URL,
        json={
            "places": [
                _attraction("Tower of London", 4.7),
                _attraction("British Museum", 4.8),
                _attraction("London Eye", 4.5),
            ]
        },
        status=200,
    )
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_attraction("National Gallery", 4.8)]},
        status=200,
    )
    # restaurants
    responses.add(
        responses.POST,
        PLACES_URL,
        json={
            "places": [
                _restaurant("Dishoom", "£25-35", 4.8),
                _restaurant("The Ledbury", "£80-120", 4.9),
                _restaurant("Pret A Manger", "£5-10", 4.0),
            ]
        },
        status=200,
    )
    # weather: one entry per day for the 5-day trip
    responses.add(responses.GET, GEO_URL, json=[{"lat": 51.5074, "lon": -0.1278}], status=200)
    responses.add(
        responses.GET,
        FORECAST_URL,
        json={"list": [_weather_entry(i) for i in range(5)]},
        status=200,
    )

    attractions = AttractionFinderTool(api_key="k", cache=fake_cache).search(
        "London", interests=["art"], max_results=10
    )
    restaurants = RestaurantFinderTool(api_key="k", cache=fake_cache).search(
        "London", max_results=10
    )
    forecasts = WeatherCheckerTool(api_key="k", cache=fake_cache).get_forecast(
        "London", TRIP_START, TRIP_END
    )

    # --- all three tools produced usable, non-mock data ---
    assert len(attractions) == 4  # 3 general + 1 from the interest query, none duplicated
    assert all(not a.is_mock_data for a in attractions)
    assert len(restaurants) == 3
    assert all(not r.is_mock_data for r in restaurants)
    assert len(forecasts) == 5
    assert all(f.day >= TRIP_START and f.day <= TRIP_END for f in forecasts)

    # --- budget accumulation across every category the trip touches ---
    tracker = BudgetTrackerTool(total_budget=2500, currency="GBP")
    tracker.add_cost("flights", 350)
    tracker.add_cost("hotel", 4 * 180)  # 4 nights
    # crude per-meal estimate from price_level (avoids needing real prices per dish)
    meal_estimate = sum(r.price_level * 15 for r in restaurants)
    tracker.add_cost("food", meal_estimate)
    # free walk-up attractions assumed; only ticketed ones would add a cost here
    tracker.add_cost("activities", 0)

    summary = tracker.summary
    assert summary.total_budget == 2500
    assert set(tracker.breakdown()) == {"flights", "hotel", "food", "activities"}
    assert tracker.total_spent == 350 + 720 + meal_estimate + 0
    assert tracker.remaining == 2500 - tracker.total_spent

    # a well-formed itinerary needs weather for every day and at least a few
    # attractions/restaurants per day to build from in later weeks
    assert len(forecasts) >= (TRIP_END - TRIP_START).days + 1 - 0  # got all 5 requested days
    assert len(attractions) >= 3
    assert len(restaurants) >= 3
