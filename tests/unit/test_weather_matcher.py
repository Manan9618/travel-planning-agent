from datetime import date, datetime

from travel_agent.models.core import (
    Attraction,
    DayPlan,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
    WeatherForecast,
)
from travel_agent.tools.weather_matcher import (
    classify_attraction,
    classify_setting,
    is_bad_weather,
    weather_adaptation_rate,
)


def _forecast(rain=0.1, comfort=8.0, day_val=date(2026, 9, 1)):
    return WeatherForecast(
        day=day_val,
        condition="Clear",
        temp_high_c=22,
        temp_low_c=14,
        rain_probability=rain,
        wind_speed_kph=10,
        comfort_score=comfort,
    )


# --- classify_setting ---------------------------------------------------


def test_museum_classified_indoor():
    assert classify_setting("Art museum", "The National Gallery") == "indoor"


def test_park_classified_outdoor():
    assert classify_setting("Park", "Richmond Park") == "outdoor"


def test_generic_category_is_ambiguous():
    assert classify_setting("Tourist attraction", "Big Ben") == "ambiguous"


def test_name_alone_can_trigger_classification():
    assert classify_setting(None, "Botanical Garden") == "outdoor"
    assert classify_setting(None, "City Cathedral") == "indoor"


def test_classify_attraction_uses_category_and_name():
    attraction = Attraction(name="Beach Walk", category=None, lat=1.0, lng=1.0)
    assert classify_attraction(attraction) == "outdoor"


# --- is_bad_weather ---------------------------------------------------


def test_high_rain_probability_is_bad_weather():
    assert is_bad_weather(_forecast(rain=0.8, comfort=8.0)) is True


def test_low_comfort_score_is_bad_weather():
    assert is_bad_weather(_forecast(rain=0.1, comfort=3.0)) is True


def test_good_weather_is_not_bad():
    assert is_bad_weather(_forecast(rain=0.1, comfort=9.0)) is False


def test_boundary_rain_probability_counts_as_bad():
    assert is_bad_weather(_forecast(rain=0.5, comfort=9.0)) is True


# --- weather_adaptation_rate ---------------------------------------------------


def _prefs():
    return TravelPreferences(destination="Paris", raw_text="test")


def _hotel():
    return HotelOption(name="H", address="Paris", lat=48.85, lng=2.35, price_per_night=100)


def _attraction_item(title, category, day_date=date(2026, 9, 1)):
    dt = datetime.combine(day_date, datetime.min.time())
    return ItineraryItem(
        time_slot="morning",
        start_time=dt,
        end_time=dt,
        activity_type="attraction",
        title=title,
        category=category,
    )


def test_adaptation_rate_none_when_no_weather_data():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[], weather=None)
    itinerary = Itinerary(preferences=_prefs(), days=[day], hotel=_hotel())
    assert weather_adaptation_rate(itinerary) is None


def test_adaptation_rate_perfect_match():
    good_day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_attraction_item("Park", "Park")],
        weather=_forecast(rain=0.1, comfort=9.0),
    )
    bad_day = DayPlan(
        day_number=2,
        date=date(2026, 9, 2),
        items=[_attraction_item("Gallery", "Art museum")],
        weather=_forecast(rain=0.9, comfort=2.0),
    )
    itinerary = Itinerary(preferences=_prefs(), days=[good_day, bad_day], hotel=_hotel())
    assert weather_adaptation_rate(itinerary) == 1.0


def test_adaptation_rate_zero_when_mismatched():
    bad_day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_attraction_item("Park", "Park")],  # outdoor on a rainy day
        weather=_forecast(rain=0.9, comfort=2.0),
    )
    itinerary = Itinerary(preferences=_prefs(), days=[bad_day], hotel=_hotel())
    assert weather_adaptation_rate(itinerary) == 0.0


def test_adaptation_rate_ignores_ambiguous_attractions():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_attraction_item("Big Ben", "Tourist attraction")],
        weather=_forecast(rain=0.9, comfort=2.0),
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day], hotel=_hotel())
    assert weather_adaptation_rate(itinerary) is None  # nothing scoreable


def test_adaptation_rate_ignores_non_attraction_items():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[
            ItineraryItem(
                time_slot="evening",
                start_time=datetime(2026, 9, 1),
                end_time=datetime(2026, 9, 1),
                activity_type="restaurant",
                title="Park Cafe",
                category="Park",
            )
        ],
        weather=_forecast(rain=0.9, comfort=2.0),
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day], hotel=_hotel())
    assert weather_adaptation_rate(itinerary) is None


def test_adaptation_rate_partial_match():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[
            _attraction_item("Gallery", "Art museum"),  # indoor, correct for bad weather
            _attraction_item("Park", "Park"),  # outdoor, wrong for bad weather
        ],
        weather=_forecast(rain=0.9, comfort=2.0),
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day], hotel=_hotel())
    assert weather_adaptation_rate(itinerary) == 0.5
