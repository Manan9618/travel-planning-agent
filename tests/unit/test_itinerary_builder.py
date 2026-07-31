from datetime import date, datetime

from travel_agent.models.core import (
    Attraction,
    FlightOption,
    HotelOption,
    Restaurant,
    TravelPreferences,
    WeatherForecast,
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


def _attraction(name, lat=48.86, lng=2.33, category=None):
    return Attraction(name=name, lat=lat, lng=lng, rating=4.5, category=category)


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


# --- weather-awareness (Week 7) --------------------------------------------


def _weather(day_val, rain=0.1, comfort=9.0):
    return WeatherForecast(
        day=day_val,
        condition="Clear" if comfort >= 5 else "Rain",
        temp_high_c=22,
        temp_low_c=14,
        rain_probability=rain,
        wind_speed_kph=10,
        comfort_score=comfort,
    )


MIXED_ATTRACTIONS = [
    _attraction("City Museum", category="Museum"),
    _attraction("Art Gallery", category="Art gallery"),
    _attraction("Central Park", category="Park"),
    _attraction("Botanical Garden", category="Garden"),
]


def test_day_weather_field_populated_when_forecast_provided():
    weather = [_weather(date(2026, 9, 2))]
    itinerary = _builder().build(
        _prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    assert itinerary.days[1].weather is not None
    assert itinerary.days[1].weather.condition == "Clear"
    assert itinerary.days[0].weather is None  # no forecast supplied for day 1


def test_no_weather_argument_leaves_weather_field_none():
    itinerary = _builder().build(_prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS)
    assert all(day.weather is None for day in itinerary.days)


def test_good_weather_day_prefers_outdoor_attractions():
    weather = [_weather(date(2026, 9, 2), rain=0.05, comfort=9.5)]
    itinerary = _builder().build(
        _prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    full_day = itinerary.days[1]
    attraction_titles = [i.title for i in full_day.items if i.activity_type == "attraction"]
    assert set(attraction_titles) == {"Central Park", "Botanical Garden"}


def test_bad_weather_day_prefers_indoor_attractions():
    weather = [_weather(date(2026, 9, 2), rain=0.9, comfort=2.0)]
    itinerary = _builder().build(
        _prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    full_day = itinerary.days[1]
    attraction_titles = [i.title for i in full_day.items if i.activity_type == "attraction"]
    assert set(attraction_titles) == {"City Museum", "Art Gallery"}


def test_rainy_day_produces_pack_rain_gear_warning():
    weather = [_weather(date(2026, 9, 2), rain=0.9, comfort=2.0)]
    itinerary = _builder().build(
        _prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    assert any("rain gear" in w for w in itinerary.days[1].warnings)


def test_good_weather_day_has_no_warnings():
    weather = [_weather(date(2026, 9, 2), rain=0.05, comfort=9.5)]
    itinerary = _builder().build(
        _prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    assert itinerary.days[1].warnings == []


def test_extreme_heat_produces_warning():
    weather = [
        WeatherForecast(
            day=date(2026, 9, 2),
            condition="Clear",
            temp_high_c=38,
            temp_low_c=28,
            rain_probability=0.0,
            wind_speed_kph=10,
            comfort_score=6.0,
        )
    ]
    itinerary = _builder().build(
        _prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    assert any("hot" in w.lower() for w in itinerary.days[1].warnings)


def test_attraction_item_carries_category_for_later_analysis():
    weather = [_weather(date(2026, 9, 2))]
    itinerary = _builder().build(
        _prefs(duration=4), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    attraction_items = [i for i in itinerary.days[1].items if i.activity_type == "attraction"]
    assert all(i.category is not None for i in attraction_items)


def test_switching_weather_across_two_days_swaps_selection_for_each():
    weather = [
        _weather(date(2026, 9, 2), rain=0.05, comfort=9.5),  # good
        _weather(date(2026, 9, 3), rain=0.9, comfort=2.0),  # bad
    ]
    itinerary = _builder().build(
        _prefs(duration=5), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    good_day_titles = {i.title for i in itinerary.days[1].items if i.activity_type == "attraction"}
    bad_day_titles = {i.title for i in itinerary.days[2].items if i.activity_type == "attraction"}
    assert good_day_titles == {"Central Park", "Botanical Garden"}
    assert bad_day_titles == {"City Museum", "Art Gallery"}
    assert good_day_titles.isdisjoint(bad_day_titles)


def test_no_forecast_for_a_day_falls_back_to_original_order():
    # weather only covers day 2; day 3 has none and should just use original order
    weather = [_weather(date(2026, 9, 2), rain=0.9, comfort=2.0)]
    itinerary = _builder().build(
        _prefs(duration=5), _hotel(), MIXED_ATTRACTIONS, RESTAURANTS, weather=weather
    )
    day3_titles = [i.title for i in itinerary.days[2].items if i.activity_type == "attraction"]
    assert day3_titles == ["Central Park", "Botanical Garden"]  # the two remaining, in order


# --- build_day() public entry point (Week 11 integration point) ------------


def test_build_day_full_scopes_pick_attraction_to_just_the_given_list():
    # MultiDayOptimizer calls build_day() with exactly the 2 attractions it has
    # already decided belong on this day, and a fresh (default) used-indices
    # set — both should be scheduled, not just the first one
    day_plan = _builder().build_day(
        2,
        date(2026, 9, 2),
        "full",
        _hotel(),
        RESTAURANTS,
        attractions=[_attraction("Only A"), _attraction("Only B")],
    )
    titles = {i.title for i in day_plan.items if i.activity_type == "attraction"}
    assert titles == {"Only A", "Only B"}


def test_build_day_full_sets_weather_and_warnings():
    forecast = WeatherForecast(
        day=date(2026, 9, 2),
        condition="Rain",
        temp_high_c=18,
        temp_low_c=12,
        rain_probability=0.9,
        wind_speed_kph=10,
        comfort_score=3.0,
    )
    day_plan = _builder().build_day(
        2,
        date(2026, 9, 2),
        "full",
        _hotel(),
        RESTAURANTS,
        attractions=[_attraction("A"), _attraction("B")],
        forecast=forecast,
    )
    assert day_plan.weather == forecast
    assert any("rain gear" in w for w in day_plan.warnings)


def test_build_day_arrival_matches_build_arrival_day_behavior():
    flight = _flight(arrival_time="2026-09-01T14:00:00")
    day_plan = _builder().build_day(
        1, date(2026, 9, 1), "arrival", _hotel(), RESTAURANTS, flight=flight, destination="Paris"
    )
    types = [item.activity_type for item in day_plan.items]
    assert types[:3] == ["flight", "transfer", "hotel_checkin"]


def test_build_day_departure_matches_build_departure_day_behavior():
    day_plan = _builder().build_day(5, date(2026, 9, 5), "departure", _hotel(), RESTAURANTS)
    types = [item.activity_type for item in day_plan.items]
    assert types == ["hotel_checkout", "transfer"]


def test_first_full_day_uses_top_rated_attractions_not_skipped():
    # regression check: previously the first two attractions (highest-rated, since
    # AttractionFinderTool sorts by rating) were silently never scheduled because
    # the day-index arithmetic for the first full day started at 1, not 0
    itinerary = _builder().build(_prefs(duration=4), _hotel(), ATTRACTIONS, RESTAURANTS)
    first_full_day_titles = {
        i.title for i in itinerary.days[1].items if i.activity_type == "attraction"
    }
    assert first_full_day_titles == {"Attraction 0", "Attraction 1"}
