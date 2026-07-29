import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.tools.attraction_finder import AttractionFinderTool

PLACES_URL = "https://google.serper.dev/places"


def _place(title, lat=51.5, lng=-0.1, rating=4.5, category="Tourist attraction", cid=None):
    return {
        "title": title,
        "address": f"{title} Address",
        "latitude": lat,
        "longitude": lng,
        "rating": rating,
        "ratingCount": 1000,
        "category": category,
        "cid": cid or title,
    }


def _tool(fake_cache):
    return AttractionFinderTool(api_key="test-key", cache=fake_cache)


@responses.activate
def test_happy_path_parses_fields(fake_cache):
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place("Tower Bridge", rating=4.8)]},
        status=200,
    )
    results = _tool(fake_cache).search("London")
    assert results[0].name == "Tower Bridge"
    assert results[0].category == "Tourist attraction"
    assert results[0].rating == 4.8
    assert results[0].lat == 51.5
    assert not results[0].is_mock_data


@responses.activate
def test_sorted_by_rating_descending(fake_cache):
    responses.add(
        responses.POST,
        PLACES_URL,
        json={
            "places": [
                _place("Low", rating=4.0),
                _place("High", rating=4.9),
                _place("Mid", rating=4.5),
            ]
        },
        status=200,
    )
    results = _tool(fake_cache).search("London")
    assert [a.name for a in results] == ["High", "Mid", "Low"]


@responses.activate
def test_interests_add_extra_queries_and_dedupe(fake_cache):
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place("National Gallery", cid="ng")]},
        status=200,
    )
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place("National Gallery", cid="ng")]},
        status=200,
    )
    results = _tool(fake_cache).search("London", interests=["art"])
    assert len(results) == 1  # deduped by cid even though it appeared in both queries
    assert len(responses.calls) == 2  # one query for "top attractions", one for "art"


@responses.activate
def test_max_results_truncates(fake_cache):
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [_place(f"Place {i}", cid=str(i)) for i in range(20)]},
        status=200,
    )
    results = _tool(fake_cache).search("London", max_results=5)
    assert len(results) == 5


@responses.activate
def test_falls_back_to_mock_on_empty_results(fake_cache):
    responses.add(responses.POST, PLACES_URL, json={"places": []}, status=200)
    results = _tool(fake_cache).search("Nowhereville")
    assert len(results) > 0
    assert all(a.is_mock_data for a in results)


@responses.activate
def test_falls_back_to_mock_on_connection_error(fake_cache):
    responses.add(responses.POST, PLACES_URL, body=RequestsConnectionError("down"))
    responses.add(responses.POST, PLACES_URL, body=RequestsConnectionError("down"))
    results = _tool(fake_cache).search("London")
    assert all(a.is_mock_data for a in results)


@responses.activate
def test_malformed_entry_skipped_not_fatal(fake_cache):
    broken = {"title": "Broken"}  # missing lat/lng
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [broken, _place("Good Place", cid="good")]},
        status=200,
    )
    results = _tool(fake_cache).search("London")
    assert len(results) == 1
    assert results[0].name == "Good Place"


@responses.activate
def test_cache_hit_avoids_refetch(fake_cache):
    responses.add(responses.POST, PLACES_URL, json={"places": [_place("Tower Bridge")]}, status=200)
    tool = _tool(fake_cache)
    first = tool.search("London")

    responses.reset()
    second = tool.search("London")
    assert [a.name for a in second] == [a.name for a in first]


@responses.activate
def test_missing_rating_defaults_to_none_and_sorts_last(fake_cache):
    place_no_rating = _place("No Rating", cid="nr")
    del place_no_rating["rating"]
    responses.add(
        responses.POST,
        PLACES_URL,
        json={"places": [place_no_rating, _place("Rated", rating=4.5, cid="r")]},
        status=200,
    )
    results = _tool(fake_cache).search("London")
    assert results[0].name == "Rated"
    assert results[1].rating is None


@responses.activate
def test_rate_limit_429_falls_back_after_retries_exhausted(fake_cache):
    responses.add(responses.POST, PLACES_URL, status=429)
    responses.add(responses.POST, PLACES_URL, status=429)
    results = _tool(fake_cache).search("London")
    assert all(a.is_mock_data for a in results)
