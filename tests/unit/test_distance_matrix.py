import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.tools.distance_matrix import DEFAULT_FALLBACK_MINUTES, TravelTimeEstimator

URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def _body(status="OK", duration_seconds=3030):
    return {
        "rows": [{"elements": [{"status": status, "duration": {"value": duration_seconds}}]}],
        "status": "OK",
    }


def _tool(fake_cache):
    return TravelTimeEstimator(api_key="test-key", cache=fake_cache)


@responses.activate
def test_happy_path_converts_seconds_to_minutes(fake_cache):
    responses.add(responses.GET, URL, json=_body(duration_seconds=3000), status=200)
    minutes = _tool(fake_cache).minutes_between(48.86, 2.33, 48.85, 2.29)
    assert minutes == 50  # 3000s / 60


@responses.activate
def test_element_status_not_ok_falls_back(fake_cache):
    responses.add(responses.GET, URL, json=_body(status="ZERO_RESULTS"), status=200)
    minutes = _tool(fake_cache).minutes_between(48.86, 2.33, 48.85, 2.29)
    assert minutes == DEFAULT_FALLBACK_MINUTES


@responses.activate
def test_connection_error_falls_back(fake_cache):
    responses.add(responses.GET, URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, URL, body=RequestsConnectionError("down"))
    minutes = _tool(fake_cache).minutes_between(48.86, 2.33, 48.85, 2.29)
    assert minutes == DEFAULT_FALLBACK_MINUTES


@responses.activate
def test_malformed_response_falls_back(fake_cache):
    responses.add(responses.GET, URL, json={"rows": []}, status=200)
    minutes = _tool(fake_cache).minutes_between(48.86, 2.33, 48.85, 2.29)
    assert minutes == DEFAULT_FALLBACK_MINUTES


@responses.activate
def test_cache_hit_avoids_refetch(fake_cache):
    responses.add(responses.GET, URL, json=_body(duration_seconds=1200), status=200)
    tool = _tool(fake_cache)
    first = tool.minutes_between(48.86, 2.33, 48.85, 2.29)

    responses.reset()
    second = tool.minutes_between(48.86, 2.33, 48.85, 2.29)
    assert first == second == 20


@responses.activate
def test_different_coordinates_use_different_cache_entries(fake_cache):
    responses.add(responses.GET, URL, json=_body(duration_seconds=600), status=200)
    responses.add(responses.GET, URL, json=_body(duration_seconds=1800), status=200)
    tool = _tool(fake_cache)
    a = tool.minutes_between(48.86, 2.33, 48.85, 2.29)
    b = tool.minutes_between(1.0, 1.0, 2.0, 2.0)
    assert a == 10
    assert b == 30
