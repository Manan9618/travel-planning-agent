import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.tools.restaurant_finder import RestaurantFinderTool, _parse_price_level

PLACES_URL = "https://google.serper.dev/places"


def _place(title, lat=51.5, lng=-0.1, rating=4.5, category="Indian", price_level="€20-40"):
    return {
        "title": title,
        "address": f"{title} St",
        "latitude": lat,
        "longitude": lng,
        "rating": rating,
        "ratingCount": 500,
        "priceLevel": price_level,
        "category": category,
    }


def _tool(fake_cache):
    return RestaurantFinderTool(api_key="test-key", cache=fake_cache)


# --- price level parsing -------------------------------------------------


def test_parse_price_level_symbol_style():
    assert _parse_price_level("$$") == 2
    assert _parse_price_level("€€€€") == 4


def test_parse_price_level_numeric_range_buckets():
    assert _parse_price_level("€10-14") == 1  # avg 12
    assert _parse_price_level("€18-22") == 2  # avg 20
    assert _parse_price_level("€40-60") == 3  # avg 50
    assert _parse_price_level("€100-150") == 4  # avg 125


def test_parse_price_level_missing_defaults_mid():
    assert _parse_price_level(None) == 2
    assert _parse_price_level("") == 2


# --- tool behavior --------------------------------------------------------


@responses.activate
def test_happy_path_parses_fields(fake_cache):
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place("Dishoom", rating=4.8, price_level="£40-60")]},
        status=200,
    )
    results = _tool(fake_cache).search("London", cuisine="indian")
    r = results[0]
    assert r.name == "Dishoom"
    assert r.cuisine == "Indian"
    assert r.rating == 4.8
    assert r.price_level == 3
    assert not r.is_mock_data


@responses.activate
def test_query_includes_cuisine_when_given(fake_cache):
    responses.add(responses.POST, PLACES_URL, json={"places": [_place("Any")]}, status=200)
    _tool(fake_cache).search("London", cuisine="thai")
    sent_body = responses.calls[0].request.body
    assert b"thai" in sent_body


@responses.activate
def test_sorted_by_rating_descending(fake_cache):
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place("Low", rating=4.0), _place("High", rating=4.9)]},
        status=200,
    )
    results = _tool(fake_cache).search("London")
    assert [r.name for r in results] == ["High", "Low"]


@responses.activate
def test_max_results_truncates(fake_cache):
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place(f"R{i}") for i in range(15)]},
        status=200,
    )
    results = _tool(fake_cache).search("London", max_results=4)
    assert len(results) == 4


@responses.activate
def test_falls_back_to_mock_on_empty_results(fake_cache):
    responses.add(responses.POST, PLACES_URL, json={"places": []}, status=200)
    results = _tool(fake_cache).search("Nowhereville")
    assert len(results) > 0
    assert all(r.is_mock_data for r in results)


@responses.activate
def test_falls_back_to_mock_on_connection_error(fake_cache):
    responses.add(responses.POST, PLACES_URL, body=RequestsConnectionError("down"))
    responses.add(responses.POST, PLACES_URL, body=RequestsConnectionError("down"))
    results = _tool(fake_cache).search("London")
    assert all(r.is_mock_data for r in results)


@responses.activate
def test_malformed_entry_skipped_not_fatal(fake_cache):
    broken = {"title": "Broken"}
    responses.add(responses.POST, PLACES_URL, json={"places": [broken, _place("Good")]}, status=200)
    results = _tool(fake_cache).search("London")
    assert len(results) == 1
    assert results[0].name == "Good"


@responses.activate
def test_cache_hit_avoids_refetch(fake_cache):
    responses.add(responses.POST, PLACES_URL, json={"places": [_place("Dishoom")]}, status=200)
    tool = _tool(fake_cache)
    first = tool.search("London", cuisine="indian")

    responses.reset()
    second = tool.search("London", cuisine="indian")
    assert [r.name for r in second] == [r.name for r in first]


@responses.activate
def test_cache_key_distinguishes_cuisine(fake_cache):
    responses.add(responses.POST, PLACES_URL, json={"places": [_place("Indian Place")]}, status=200)
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place("Thai Place", category="Thai")]},
        status=200,
    )
    tool = _tool(fake_cache)
    indian = tool.search("London", cuisine="indian")
    thai = tool.search("London", cuisine="thai")
    assert indian[0].name != thai[0].name
