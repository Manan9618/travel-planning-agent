from datetime import date, datetime

from travel_agent.models.core import (
    Attraction,
    FlightOption,
    HotelOption,
    Restaurant,
    TravelPreferences,
)
from travel_agent.tools.itinerary_builder import (
    HOTEL_CHECKIN_TIME,
    HOTEL_CHECKOUT_TIME,
    ItineraryBuilder,
)


class FixedTravelTime:
    """Test double: always returns a fixed number of minutes, no network calls."""

    def __init__(self, minutes: int = 15):
        self.minutes = minutes
        self.calls = []

    def minutes_between(self, olat, olng, dlat, dlng, mode="driving"):
        self.calls.append((olat, olng, dlat, dlng))
        return self.minutes


def _prefs(destination="Paris", origin="Boston", start=date(2026, 9, 1), duration=5, **kw):
    return TravelPreferences(
        destination=destination,
        origin=origin,
        start_date=start,
        duration_days=duration,
        raw_text="test",
        **kw,
    )


def _hotel(lat=48.85, lng=2.35):
    return HotelOption(
        name="Test Hotel", address="Paris, France", lat=lat, lng=lng, price_per_night=100
    )


def _attraction(name, lat=48.86, lng=2.33):
    return Attraction(name=name, lat=lat, lng=lng, rating=4.5)


def _restaurant(name, lat=48.85, lng=2.35):
    return Restaurant(name=name, lat=lat, lng=lng, rating=4.5)


def _flight(arrival_time="2026-09-01T14:00:00"):
    return FlightOption(
        airline="AF",
        origin="BOS",
        destination="PAR",
        departure_time="2026-09-01T02:00:00",
        arrival_time=arrival_time,
        duration_minutes=420,
        price=650,
    )


def _builder(minutes=15):
    return ItineraryBuilder(travel_time_estimator=FixedTravelTime(minutes))


ATTRACTIONS = [_attraction(f"Attraction {i}") for i in range(6)]
RESTAURANTS = [_restaurant(f"Restaurant {i}") for i in range(6)]


# --- overall structure ---------------------------------------------------


def test_number_of_days_matches_duration():
    itinerary = _builder().build(_prefs(duration=5), _hotel(), ATTRACTIONS, RESTAURANTS)
    assert len(itinerary.days) == 5
    assert [d.day_number for d in itinerary.days] == [1, 2, 3, 4, 5]
    assert itinerary.days[0].date == date(2026, 9, 1)
    assert itinerary.days[-1].date == date(2026, 9, 5)


def test_flight_included_in_itinerary_when_provided():
    flight = _flight()
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=flight)
    assert itinerary.flights == [flight]


def test_no_flight_results_in_empty_flights_list():
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=None)
    assert itinerary.flights == []


# --- arrival day -----------------------------------------------------------


def test_arrival_day_anchors_flight_time_to_trip_start_date_not_flights_own_date():
    # flight's own date is wildly different (Sept 20) from the trip's actual start (Sept 1) —
    # this mirrors TravelPayouts returning "nearby" fares rather than exact-date results
    flight = _flight(arrival_time="2026-09-20T14:00:00")
    itinerary = _builder().build(
        _prefs(start=date(2026, 9, 1)), _hotel(), ATTRACTIONS, RESTAURANTS, flight=flight
    )
    flight_item = itinerary.days[0].items[0]
    assert flight_item.activity_type == "flight"
    assert flight_item.start_time.date() == date(2026, 9, 1)
    assert flight_item.start_time.time() == datetime(2026, 9, 20, 14, 0).time()


def test_arrival_day_order_flight_transfer_checkin():
    flight = _flight(arrival_time="2026-09-01T14:00:00")
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=flight)
    day1 = itinerary.days[0]
    types = [item.activity_type for item in day1.items]
    assert types[:3] == ["flight", "transfer", "hotel_checkin"]


def test_arrival_day_checkin_not_before_hotel_checkin_time():
    # flight arrives at 08:00, well before the 15:00 check-in floor
    flight = _flight(arrival_time="2026-09-01T08:00:00")
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=flight)
    checkin_item = next(i for i in itinerary.days[0].items if i.activity_type == "hotel_checkin")
    assert checkin_item.start_time.time() == HOTEL_CHECKIN_TIME


def test_arrival_day_checkin_delayed_by_late_flight_arrival():
    # arrival + 90min transfer pushes past the normal 15:00 floor
    flight = _flight(arrival_time="2026-09-01T22:00:00")
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=flight)
    checkin_item = next(i for i in itinerary.days[0].items if i.activity_type == "hotel_checkin")
    assert checkin_item.start_time.time() == datetime(2026, 9, 1, 23, 30).time()


def test_arrival_day_without_flight_checks_in_at_default_time():
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=None)
    day1 = itinerary.days[0]
    assert day1.items[0].activity_type == "hotel_checkin"
    assert day1.items[0].start_time.time() == HOTEL_CHECKIN_TIME


def test_arrival_day_gets_dinner_when_time_allows():
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=None)
    day1 = itinerary.days[0]
    assert any(i.activity_type == "restaurant" for i in day1.items)


def test_arrival_day_skips_dinner_when_arrival_too_late():
    flight = _flight(arrival_time="2026-09-01T23:00:00")  # transfer pushes check-in past dinner
    itinerary = _builder().build(_prefs(), _hotel(), ATTRACTIONS, RESTAURANTS, flight=flight)
    day1 = itinerary.days[0]
    assert not any(i.activity_type == "restaurant" for i in day1.items)


# --- full days -----------------------------------------------------------


def test_full_day_has_all_four_slots():
    itinerary = _builder().build(_prefs(duration=4), _hotel(), ATTRACTIONS, RESTAURANTS)
    full_day = itinerary.days[1]  # day 2 of a 4-day trip is a full day
    types = [item.activity_type for item in full_day.items]
    assert types == ["attraction", "restaurant", "attraction", "restaurant"]
    slots = [item.time_slot for item in full_day.items]
    assert slots == ["morning", "afternoon", "afternoon", "evening"]


def test_full_day_items_are_chronologically_ordered():
    itinerary = _builder().build(_prefs(duration=4), _hotel(), ATTRACTIONS, RESTAURANTS)
    full_day = itinerary.days[1]
    times = [item.start_time for item in full_day.items]
    assert times == sorted(times)


def test_full_day_with_no_attractions_or_restaurants_produces_no_items():
    itinerary = _builder().build(_prefs(duration=4), _hotel(), [], [])
    full_day = itinerary.days[1]
    assert full_day.items == []


def test_full_day_activities_dont_repeat_across_consecutive_days_when_enough_supply():
    itinerary = _builder().build(_prefs(duration=4), _hotel(), ATTRACTIONS, RESTAURANTS)
    day2_titles = {i.title for i in itinerary.days[1].items if i.activity_type == "attraction"}
    day3_titles = {i.title for i in itinerary.days[2].items if i.activity_type == "attraction"}
    assert day2_titles.isdisjoint(day3_titles)


def test_huge_travel_time_can_skip_every_slot():
    # 800 minutes (~13h) from the 8am hotel start reaches past every fixed window,
    # including dinner (19:00-20:30), since prev_end only advances on a successful
    # booking — a skipped morning slot doesn't poison later slots' travel baseline.
    itinerary = ItineraryBuilder(travel_time_estimator=FixedTravelTime(800)).build(
        _prefs(duration=4), _hotel(), ATTRACTIONS, RESTAURANTS
    )
    full_day = itinerary.days[1]
    assert full_day.items == []


# --- departure day -----------------------------------------------------------


def test_departure_day_has_checkout_and_transfer():
    itinerary = _builder().build(_prefs(duration=5), _hotel(), ATTRACTIONS, RESTAURANTS)
    last_day = itinerary.days[-1]
    types = [item.activity_type for item in last_day.items]
    assert types == ["hotel_checkout", "transfer"]
    assert last_day.items[0].start_time.time() == HOTEL_CHECKOUT_TIME


def test_departure_transfer_ends_after_checkout():
    itinerary = _builder().build(_prefs(duration=5), _hotel(), ATTRACTIONS, RESTAURANTS)
    last_day = itinerary.days[-1]
    checkout, transfer = last_day.items
    assert transfer.start_time == checkout.start_time
    assert transfer.end_time > transfer.start_time


# --- edge cases -----------------------------------------------------------


def test_single_day_trip_does_not_crash():
    itinerary = _builder().build(_prefs(duration=1), _hotel(), ATTRACTIONS, RESTAURANTS)
    assert len(itinerary.days) == 1


def test_end_date_takes_precedence_over_duration_days():
    prefs = _prefs(start=date(2026, 9, 1), duration=10)
    prefs.end_date = date(2026, 9, 3)  # explicit end_date should win over duration=10
    itinerary = _builder().build(prefs, _hotel(), ATTRACTIONS, RESTAURANTS)
    assert len(itinerary.days) == 3
