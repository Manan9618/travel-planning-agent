import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

import travel_agent.tools.distance_matrix as dm_module
from travel_agent.tools.distance_matrix import (
    DEFAULT_FALLBACK_MINUTES,
    DistanceMatrixTool,
    TravelTimeEstimator,
)

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


# --- DistanceMatrixTool (Week 9) ---------------------------------------------------


def _row_body(durations_seconds, statuses=None):
    statuses = statuses or ["OK"] * len(durations_seconds)
    return {
        "rows": [
            {
                "elements": [
                    {"status": s, "duration": {"value": d}}
                    for s, d in zip(statuses, durations_seconds, strict=True)
                ]
            }
        ],
        "status": "OK",
    }


def _matrix_tool(fake_cache):
    return DistanceMatrixTool(api_key="test-key", cache=fake_cache)


def test_empty_points_returns_empty_matrix(fake_cache):
    assert _matrix_tool(fake_cache).compute_matrix([]) == []


def test_single_point_returns_zero_matrix(fake_cache):
    assert _matrix_tool(fake_cache).compute_matrix([(1.0, 1.0)]) == [[0]]


@responses.activate
def test_two_points_computes_both_directions(fake_cache):
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)  # 0 -> 1
    responses.add(responses.GET, URL, json=_row_body([1200]), status=200)  # 1 -> 0
    matrix = _matrix_tool(fake_cache).compute_matrix([(1.0, 1.0), (2.0, 2.0)])
    assert matrix == [[0, 10], [20, 0]]


@responses.activate
def test_three_points_issues_one_request_per_origin(fake_cache):
    responses.add(responses.GET, URL, json=_row_body([600, 1200]), status=200)
    responses.add(responses.GET, URL, json=_row_body([600, 1800]), status=200)
    responses.add(responses.GET, URL, json=_row_body([1200, 1800]), status=200)
    points = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
    matrix = _matrix_tool(fake_cache).compute_matrix(points)
    assert len(responses.calls) == 3  # one request per origin, not 6 pairwise calls
    assert matrix[0][0] == 0
    assert matrix[1][1] == 0
    assert matrix[2][2] == 0


@responses.activate
def test_status_not_ok_falls_back_for_that_pair_only(fake_cache):
    responses.add(
        responses.GET, URL, json=_row_body([600, 0], statuses=["OK", "ZERO_RESULTS"]), status=200
    )
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    points = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
    matrix = _matrix_tool(fake_cache).compute_matrix(points)
    assert matrix[0][1] == 10
    assert matrix[0][2] == DEFAULT_FALLBACK_MINUTES


@responses.activate
def test_connection_error_falls_back_for_whole_row(fake_cache):
    responses.add(responses.GET, URL, body=RequestsConnectionError("down"))
    matrix = _matrix_tool(fake_cache).compute_matrix([(1.0, 1.0), (2.0, 2.0)])
    assert matrix[0][1] == DEFAULT_FALLBACK_MINUTES


@responses.activate
def test_cache_hit_skips_request_for_that_pair(fake_cache):
    tool = _matrix_tool(fake_cache)
    points = [(1.0, 1.0), (2.0, 2.0)]
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    responses.add(responses.GET, URL, json=_row_body([1200]), status=200)
    tool.compute_matrix(points)  # populates cache for both directions

    responses.reset()  # any further HTTP call now errors with "no responses registered"
    matrix2 = tool.compute_matrix(points)
    assert matrix2 == [[0, 10], [20, 0]]


@responses.activate
def test_shares_cache_with_travel_time_estimator(fake_cache):
    responses.add(responses.GET, URL, json=_body(duration_seconds=600), status=200)
    TravelTimeEstimator(api_key="test-key", cache=fake_cache).minutes_between(1.0, 1.0, 2.0, 2.0)

    responses.reset()
    responses.add(responses.GET, URL, json=_row_body([1200]), status=200)  # only 1->0 needed
    matrix = _matrix_tool(fake_cache).compute_matrix([(1.0, 1.0), (2.0, 2.0)])
    assert matrix == [[0, 10], [20, 0]]
    assert len(responses.calls) == 1  # 0->1 came from the shared cache


@responses.activate
def test_batching_respects_max_elements_per_request(fake_cache, monkeypatch):
    monkeypatch.setattr(dm_module, "MAX_ELEMENTS_PER_REQUEST", 1)
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    responses.add(responses.GET, URL, json=_row_body([600]), status=200)
    points = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
    _matrix_tool(fake_cache).compute_matrix(points)
    # 3 origins x 2 destinations each, chunked to 1 destination per request = 6 requests
    assert len(responses.calls) == 6
