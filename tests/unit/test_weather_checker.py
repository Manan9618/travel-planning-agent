from datetime import date

import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.tools.weather_checker import WeatherCheckerTool

GEO_URL = "http://api.openweathermap.org/geo/1.0/direct"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def _geo_body(lat=51.5074, lon=-0.1278):
    return [{"name": "London", "lat": lat, "lon": lon, "country": "GB"}]


def _entry(dt, temp_max, temp_min, pop=0.0, wind_speed=2.0, condition="Clear"):
    return {
        "dt": dt,
        "main": {"temp_max": temp_max, "temp_min": temp_min},
        "wind": {"speed": wind_speed},
        "weather": [{"main": condition}],
        "pop": pop,
    }


def _tool(fake_cache):
    return WeatherCheckerTool(api_key="test-key", cache=fake_cache)


# 2026-08-01 00:00 UTC and 12:00 UTC as two 3-hour entries for the same day
DAY1_MIDNIGHT = 1785542400  # 2026-08-01T00:00:00Z
DAY1_NOON = 1785585600  # 2026-08-01T12:00:00Z


@responses.activate
def test_happy_path_aggregates_day(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(
        responses.GET,
        FORECAST_URL,
        json={
            "list": [
                _entry(DAY1_MIDNIGHT, temp_max=18, temp_min=12, pop=0.1),
                _entry(DAY1_NOON, temp_max=24, temp_min=16, pop=0.3),
            ]
        },
        status=200,
    )
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert len(results) == 1
    day = results[0]
    assert day.day == date(2026, 8, 1)
    assert day.temp_high_c == 24
    assert day.temp_low_c == 12
    assert day.rain_probability == 0.3


@responses.activate
def test_wind_converted_from_ms_to_kph(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(
        responses.GET,
        FORECAST_URL,
        json={"list": [_entry(DAY1_NOON, temp_max=20, temp_min=15, wind_speed=10.0)]},
        status=200,
    )
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert results[0].wind_speed_kph == 36.0  # 10 m/s * 3.6


@responses.activate
def test_condition_is_majority_across_day(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(
        responses.GET,
        FORECAST_URL,
        json={
            "list": [
                _entry(DAY1_MIDNIGHT, 18, 12, condition="Rain"),
                _entry(DAY1_NOON, 20, 14, condition="Rain"),
                _entry(DAY1_NOON + 10800, 19, 13, condition="Clouds"),
            ]
        },
        status=200,
    )
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert results[0].condition == "Rain"


@responses.activate
def test_filters_to_requested_date_range(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    day2 = DAY1_NOON + 86400
    responses.add(
        responses.GET,
        FORECAST_URL,
        json={"list": [_entry(DAY1_NOON, 20, 14), _entry(day2, 22, 15)]},
        status=200,
    )
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert len(results) == 1
    assert results[0].day == date(2026, 8, 1)


@responses.activate
def test_comfort_score_penalizes_rain_and_extreme_heat(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(
        responses.GET,
        FORECAST_URL,
        json={"list": [_entry(DAY1_NOON, temp_max=38, temp_min=30, pop=0.9, wind_speed=15.0)]},
        status=200,
    )
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert results[0].comfort_score < 5.0


@responses.activate
def test_comfort_score_high_for_mild_dry_day(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(
        responses.GET,
        FORECAST_URL,
        json={"list": [_entry(DAY1_NOON, temp_max=22, temp_min=17, pop=0.0, wind_speed=2.0)]},
        status=200,
    )
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert results[0].comfort_score >= 9.0


@responses.activate
def test_geocode_not_found_returns_empty_list(fake_cache):
    responses.add(responses.GET, GEO_URL, json=[], status=200)
    results = _tool(fake_cache).get_forecast("Nowhereville", date(2026, 8, 1), date(2026, 8, 1))
    assert results == []


@responses.activate
def test_connection_error_on_geocode_returns_empty_not_mock(fake_cache):
    responses.add(responses.GET, GEO_URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, GEO_URL, body=RequestsConnectionError("down"))
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert results == []


@responses.activate
def test_connection_error_on_forecast_returns_empty_not_mock(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(responses.GET, FORECAST_URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, FORECAST_URL, body=RequestsConnectionError("down"))
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert results == []


@responses.activate
def test_dates_beyond_horizon_are_simply_omitted(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(
        responses.GET, FORECAST_URL, json={"list": [_entry(DAY1_NOON, 20, 14)]}, status=200
    )
    results = _tool(fake_cache).get_forecast("London", date(2026, 8, 1), date(2026, 8, 10))
    assert len(results) == 1  # only the one day the provider actually returned


@responses.activate
def test_cache_hit_avoids_refetch(fake_cache):
    responses.add(responses.GET, GEO_URL, json=_geo_body(), status=200)
    responses.add(
        responses.GET, FORECAST_URL, json={"list": [_entry(DAY1_NOON, 20, 14)]}, status=200
    )
    tool = _tool(fake_cache)
    first = tool.get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))

    responses.reset()
    second = tool.get_forecast("London", date(2026, 8, 1), date(2026, 8, 1))
    assert [f.day for f in second] == [f.day for f in first]
