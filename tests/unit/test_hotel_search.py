from datetime import date

import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.models.core import BudgetTier
from travel_agent.tools.hotel_search import HotelSearchTool

DEST_URL = "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchDestination"
HOTELS_URL = "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchHotels"


def _dest_body(dest_id="-1456928", dest_type="city", city_name="Paris", country="France"):
    return {
        "status": True,
        "message": "Success",
        "data": [
            {
                "dest_id": dest_id,
                "search_type": "city",
                "country": country,
                "city_name": city_name,
                "dest_type": dest_type,
                "name": city_name,
            }
        ],
    }


def _hotel_entry(name, price, rating=8.4, lat=48.89, lng=2.32, currency="USD"):
    return {
        "hotel_id": 59015,
        "property": {
            "name": name,
            "latitude": lat,
            "longitude": lng,
            "reviewScore": rating,
            "reviewCount": 3226,
            "priceBreakdown": {"grossPrice": {"value": price, "currency": currency}},
            "checkinDate": "2026-09-10",
            "checkoutDate": "2026-09-12",
        },
    }


def _hotels_body(hotels):
    return {"status": True, "message": "Success", "data": {"hotels": hotels}}


def _tool(fake_cache):
    return HotelSearchTool(api_key="test-key", cache=fake_cache)


CHECK_IN = date(2026, 9, 10)
CHECK_OUT = date(2026, 9, 12)  # 2 nights


@responses.activate
def test_happy_path_parses_all_fields(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(
        responses.GET, HOTELS_URL, json=_hotels_body([_hotel_entry("Ibis Styles", 418)]), status=200
    )
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    hotel = results[0]
    assert hotel.name == "Ibis Styles"
    assert hotel.rating == 8.4
    assert hotel.lat == 48.89
    assert hotel.lng == 2.32
    assert hotel.address == "Paris, France"
    assert not hotel.is_mock_data


@responses.activate
def test_price_per_night_divided_by_nights(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(
        responses.GET, HOTELS_URL, json=_hotels_body([_hotel_entry("Ibis Styles", 418)]), status=200
    )
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)  # 2 nights
    assert results[0].price_per_night == 209.0


@responses.activate
def test_sorted_by_price_ascending(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(
        responses.GET,
        HOTELS_URL,
        json=_hotels_body(
            [_hotel_entry("Expensive", 800), _hotel_entry("Cheap", 200), _hotel_entry("Mid", 400)]
        ),
        status=200,
    )
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    assert [h.name for h in results] == ["Cheap", "Mid", "Expensive"]


@responses.activate
def test_max_results_truncates(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    hotels = [_hotel_entry(f"Hotel {i}", 100 + i * 10) for i in range(15)]
    responses.add(responses.GET, HOTELS_URL, json=_hotels_body(hotels), status=200)
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT, max_results=5)
    assert len(results) == 5


@responses.activate
def test_max_price_per_night_filters(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(
        responses.GET,
        HOTELS_URL,
        json=_hotels_body([_hotel_entry("Cheap", 200), _hotel_entry("Pricey", 1000)]),
        status=200,
    )
    # 2-night stay: "Cheap" -> 100/night, "Pricey" -> 500/night
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT, max_price_per_night=150)
    assert [h.name for h in results] == ["Cheap"]
    assert not results[0].is_mock_data


@responses.activate
def test_max_price_per_night_below_all_options_falls_back_to_mock(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(
        responses.GET,
        HOTELS_URL,
        json=_hotels_body([_hotel_entry("Cheap", 200), _hotel_entry("Pricey", 1000)]),
        status=200,
    )
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT, max_price_per_night=10)
    assert all(h.is_mock_data for h in results)


@responses.activate
def test_destination_not_found_falls_back_to_mock(fake_cache):
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    results = _tool(fake_cache).search("Nowhereville", CHECK_IN, CHECK_OUT)
    assert len(results) > 0
    assert all(h.is_mock_data for h in results)


GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


@responses.activate
def test_mock_hotel_uses_geocoded_coordinates_when_available(fake_cache):
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    responses.add(
        responses.GET,
        GEOCODE_URL,
        json={"results": [{"geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}}]},
        status=200,
    )
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    assert all(h.is_mock_data for h in results)
    assert all(h.lat == 48.8566 and h.lng == 2.3522 for h in results)


@responses.activate
def test_mock_hotel_falls_back_to_null_island_when_geocoding_also_fails(fake_cache):
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    responses.add(responses.GET, GEOCODE_URL, json={"results": []}, status=200)
    results = _tool(fake_cache).search("Nowhereville", CHECK_IN, CHECK_OUT)
    assert all(h.is_mock_data for h in results)
    assert all(h.lat == 0.0 and h.lng == 0.0 for h in results)


@responses.activate
def test_geocode_fallback_is_cached_across_searches(fake_cache):
    """Week 20: a second mock-hotel fallback for the same city, even with
    different stay dates (so `search`'s own cache key misses), must not
    re-hit the Geocoding API - only the hotel search itself varies by date,
    the city's coordinates don't."""
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    responses.add(
        responses.GET,
        GEOCODE_URL,
        json={"results": [{"geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}}]},
        status=200,
    )
    tool = _tool(fake_cache)
    first = tool.search("Paris", CHECK_IN, CHECK_OUT)
    second = tool.search("Paris", date(2026, 10, 1), date(2026, 10, 3))
    assert all(h.lat == 48.8566 and h.lng == 2.3522 for h in first + second)
    geocode_calls = [c for c in responses.calls if c.request.url.startswith(GEOCODE_URL)]
    assert len(geocode_calls) == 1


@responses.activate
def test_geocode_fallback_failure_is_not_cached(fake_cache):
    """A transient geocoding failure shouldn't poison the cache for 24h -
    only a successful lookup is worth remembering."""
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    responses.add(responses.GET, GEOCODE_URL, json={"results": []}, status=200)
    responses.add(
        responses.GET,
        GEOCODE_URL,
        json={"results": [{"geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}}]},
        status=200,
    )
    tool = _tool(fake_cache)
    first = tool.search("Paris", CHECK_IN, CHECK_OUT)
    second = tool.search("Paris", date(2026, 10, 1), date(2026, 10, 3))
    assert all(h.lat == 0.0 and h.lng == 0.0 for h in first)
    assert all(h.lat == 48.8566 and h.lng == 2.3522 for h in second)


@responses.activate
def test_no_hotels_in_results_falls_back_to_mock(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(responses.GET, HOTELS_URL, json=_hotels_body([]), status=200)
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    assert all(h.is_mock_data for h in results)


@responses.activate
def test_connection_error_on_destination_falls_back_to_mock(fake_cache):
    responses.add(responses.GET, DEST_URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, DEST_URL, body=RequestsConnectionError("down"))
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    assert all(h.is_mock_data for h in results)


@responses.activate
def test_connection_error_on_hotel_search_falls_back_to_mock(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(responses.GET, HOTELS_URL, body=RequestsConnectionError("down"))
    responses.add(responses.GET, HOTELS_URL, body=RequestsConnectionError("down"))
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    assert all(h.is_mock_data for h in results)


@responses.activate
def test_malformed_hotel_entry_skipped_not_fatal(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    broken = {"hotel_id": 1, "property": {"name": "Broken"}}  # missing lat/lng/price
    responses.add(
        responses.GET,
        HOTELS_URL,
        json=_hotels_body([broken, _hotel_entry("Good Hotel", 300)]),
        status=200,
    )
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    assert len(results) == 1
    assert results[0].name == "Good Hotel"


@responses.activate
def test_cache_hit_avoids_refetch(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(
        responses.GET, HOTELS_URL, json=_hotels_body([_hotel_entry("Ibis Styles", 418)]), status=200
    )
    tool = _tool(fake_cache)
    first = tool.search("Paris", CHECK_IN, CHECK_OUT)

    responses.reset()
    second = tool.search("Paris", CHECK_IN, CHECK_OUT)
    assert [h.name for h in second] == [h.name for h in first]


@responses.activate
def test_rating_within_booking_com_0_to_10_scale(fake_cache):
    responses.add(responses.GET, DEST_URL, json=_dest_body(), status=200)
    responses.add(
        responses.GET,
        HOTELS_URL,
        json=_hotels_body([_hotel_entry("Great Place", 300, rating=9.6)]),
        status=200,
    )
    results = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    assert results[0].rating == 9.6


# --- mock-hotel pricing scaled by budget tier (Week 22) --------------------


@responses.activate
def test_mock_hotel_price_scales_up_for_luxury_tier(fake_cache):
    # Real bug this guards against, found evaluating Week 12's baseline: a
    # flat mock price regardless of tier massively underspent luxury
    # budgets (the 3 worst budget_accuracy scores were all luxury
    # honeymoons), since the mock-hotel fallback fires whenever Booking.com's
    # RapidAPI quota is exhausted - a frequent, documented occurrence.
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    backpacker = _tool(fake_cache).search(
        "Paris", CHECK_IN, CHECK_OUT, budget_tier=BudgetTier.BACKPACKER
    )
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    luxury = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT, budget_tier=BudgetTier.LUXURY)

    assert all(h.is_mock_data for h in backpacker)
    assert all(h.is_mock_data for h in luxury)
    assert min(h.price_per_night for h in luxury) > min(h.price_per_night for h in backpacker)


@responses.activate
def test_mock_hotel_price_unspecified_tier_matches_mid_range(fake_cache):
    # No budget_tier passed at all must behave exactly as before this week's
    # change (mid-range's base price is unchanged) - a real behavioral
    # backward-compatibility guarantee, not just a coincidence of numbers.
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    unspecified = _tool(fake_cache).search("Paris", CHECK_IN, CHECK_OUT)
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    mid_range = _tool(fake_cache).search(
        "Paris", CHECK_IN, CHECK_OUT, budget_tier=BudgetTier.MID_RANGE
    )

    assert [h.price_per_night for h in unspecified] == [h.price_per_night for h in mid_range]


@responses.activate
def test_different_tiers_at_the_same_destination_are_cached_separately(fake_cache):
    tool = _tool(fake_cache)
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    backpacker_first = tool.search("Paris", CHECK_IN, CHECK_OUT, budget_tier=BudgetTier.BACKPACKER)

    # Same tier again: must be served from cache, not a second real call -
    # nothing re-stubbed, so this would raise if it weren't a cache hit.
    backpacker_second = tool.search("Paris", CHECK_IN, CHECK_OUT, budget_tier=BudgetTier.BACKPACKER)
    assert [h.price_per_night for h in backpacker_second] == [
        h.price_per_night for h in backpacker_first
    ]

    # A different tier at the same destination/dates must NOT reuse the
    # backpacker cache entry - it needs (and gets) its own real call.
    responses.add(responses.GET, DEST_URL, json={"status": False, "data": []}, status=200)
    luxury = tool.search("Paris", CHECK_IN, CHECK_OUT, budget_tier=BudgetTier.LUXURY)
    assert min(h.price_per_night for h in luxury) > min(h.price_per_night for h in backpacker_first)
