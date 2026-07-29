from datetime import date

import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.tools.flight_search import FlightSearchTool

CHEAP_URL = "https://api.travelpayouts.com/v1/prices/cheap"
LATEST_URL = "https://api.travelpayouts.com/v2/prices/latest"


def _cheap_body(price=72, stops_key="0", airline="VY", flight_number=8961):
    return {
        "data": {
            "PAR": {
                stops_key: {
                    "airline": airline,
                    "departure_at": "2026-09-12T15:00:00+01:00",
                    "return_at": "2026-09-19T13:45:00+02:00",
                    "expires_at": "2026-07-29T04:25:08Z",
                    "price": price,
                    "flight_number": flight_number,
                    "duration": 185,
                    "duration_to": 95,
                    "duration_back": 90,
                }
            }
        },
        "currency": "usd",
        "success": True,
    }


def _latest_body(entries):
    return {"currency": "usd", "error": "", "data": entries}


def _latest_entry(price, gate="EasyJet", depart_date="2026-08-07", changes=0, duration=150):
    return {
        "depart_date": depart_date,
        "origin": "LON",
        "destination": "PAR",
        "gate": gate,
        "return_date": depart_date,
        "found_at": "2026-07-22T16:12:42",
        "trip_class": 0,
        "value": price,
        "number_of_changes": changes,
        "duration": duration,
        "distance": 381,
        "show_to_affiliates": True,
        "actual": True,
    }


def _tool(fake_cache):
    return FlightSearchTool(api_key="test-token", cache=fake_cache)


@responses.activate
def test_merges_and_sorts_by_price(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(price=72), status=200)
    responses.add(
        responses.GET,
        LATEST_URL,
        json=_latest_body([_latest_entry(158), _latest_entry(199, depart_date="2026-08-15")]),
        status=200,
    )
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert [r.price for r in results] == [72, 158, 199]


@responses.activate
def test_exact_time_flag_set_correctly(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(price=72), status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([_latest_entry(158)]), status=200)
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    exact = {r.price: r.has_exact_time for r in results}
    assert exact[72] is True
    assert exact[158] is False


@responses.activate
def test_cheap_result_has_real_flight_number_and_airline(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(), status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([]), status=200)
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert results[0].airline == "VY"
    assert results[0].flight_number == "8961"


@responses.activate
def test_max_results_truncates(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(), status=200)
    entries = [_latest_entry(100 + i, depart_date=f"2026-08-{10 + i:02d}") for i in range(10)]
    responses.add(responses.GET, LATEST_URL, json=_latest_body(entries), status=200)
    results = _tool(fake_cache).search(
        "LON", "PAR", date(2026, 9, 12), date(2026, 9, 19), max_results=3
    )
    assert len(results) == 3


@responses.activate
def test_max_price_filters_out_expensive_options(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(price=500), status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([_latest_entry(100)]), status=200)
    results = _tool(fake_cache).search(
        "LON", "PAR", date(2026, 9, 12), date(2026, 9, 19), max_price=200
    )
    assert all(r.price <= 200 for r in results)
    assert 500 not in [r.price for r in results]


@responses.activate
def test_one_way_search_without_return_date(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(), status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([_latest_entry(158)]), status=200)
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), return_date=None)
    assert len(results) >= 1


@responses.activate
def test_falls_back_to_mock_when_both_endpoints_empty(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json={"success": False}, status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([]), status=200)
    results = _tool(fake_cache).search("XXX", "YYY", date(2026, 9, 12), date(2026, 9, 19))
    assert len(results) > 0
    assert all(r.is_mock_data for r in results)


@responses.activate
def test_falls_back_to_mock_on_connection_error(fake_cache):
    responses.add(responses.GET, CHEAP_URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, CHEAP_URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, LATEST_URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, LATEST_URL, body=RequestsConnectionError("down"))
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert all(r.is_mock_data for r in results)


@responses.activate
def test_retries_then_succeeds_after_transient_500(fake_cache):
    responses.add(responses.GET, CHEAP_URL, status=500)
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(), status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([]), status=200)
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert not results[0].is_mock_data
    assert results[0].price == 72


@responses.activate
def test_rate_limit_429_falls_back_after_retries_exhausted(fake_cache):
    responses.add(responses.GET, CHEAP_URL, status=429)
    responses.add(responses.GET, CHEAP_URL, status=429)
    responses.add(responses.GET, LATEST_URL, status=429)
    responses.add(responses.GET, LATEST_URL, status=429)
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert all(r.is_mock_data for r in results)


@responses.activate
def test_malformed_entry_is_skipped_not_fatal(fake_cache):
    body = _cheap_body()
    body["data"]["PAR"]["1"] = {"airline": "ZZ"}  # missing required fields
    responses.add(responses.GET, CHEAP_URL, json=body, status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([]), status=200)
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert len(results) == 1
    assert results[0].airline == "VY"


@responses.activate
def test_cache_hit_avoids_refetch(fake_cache):
    responses.add(responses.GET, CHEAP_URL, json=_cheap_body(), status=200)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([]), status=200)
    tool = _tool(fake_cache)
    first = tool.search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))

    responses.reset()  # any further HTTP call would now error with "no responses registered"
    second = tool.search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert [r.price for r in second] == [r.price for r in first]


@responses.activate
def test_not_found_status_treated_as_empty_not_raised(fake_cache):
    responses.add(responses.GET, CHEAP_URL, status=404)
    responses.add(responses.GET, LATEST_URL, json=_latest_body([_latest_entry(120)]), status=200)
    results = _tool(fake_cache).search("LON", "PAR", date(2026, 9, 12), date(2026, 9, 19))
    assert results[0].price == 120
    assert not results[0].is_mock_data
