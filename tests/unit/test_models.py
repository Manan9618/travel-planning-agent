from datetime import date

import pytest
from pydantic import ValidationError

from travel_agent.models.core import (
    Attraction,
    BudgetSummary,
    BudgetTier,
    FlightOption,
    HotelOption,
    TravelPreferences,
    TripStyle,
)


def test_travel_preferences_requires_destination():
    with pytest.raises(ValidationError):
        TravelPreferences(raw_text="somewhere nice")


def test_travel_preferences_minimal_valid():
    prefs = TravelPreferences(destination="Paris", raw_text="Paris please")
    assert prefs.destination == "Paris"
    assert prefs.travelers == 1
    assert prefs.pace.value == "moderate"


def test_travel_preferences_infers_duration_from_dates():
    prefs = TravelPreferences(
        destination="Tokyo",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        raw_text="tokyo trip",
    )
    assert prefs.duration_days == 5


def test_travel_preferences_explicit_duration_not_overridden():
    prefs = TravelPreferences(
        destination="Tokyo",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        duration_days=10,
        raw_text="tokyo trip",
    )
    assert prefs.duration_days == 10


def test_travel_preferences_rejects_end_before_start():
    with pytest.raises(ValidationError):
        TravelPreferences(
            destination="Tokyo",
            start_date=date(2026, 7, 5),
            end_date=date(2026, 7, 1),
            raw_text="tokyo trip",
        )


def test_travel_preferences_rejects_negative_budget():
    with pytest.raises(ValidationError):
        TravelPreferences(destination="Rome", budget_total=-100, raw_text="rome")


def test_travel_preferences_rejects_zero_travelers():
    with pytest.raises(ValidationError):
        TravelPreferences(destination="Rome", travelers=0, raw_text="rome")


def test_travel_preferences_rejects_too_many_travelers():
    with pytest.raises(ValidationError):
        TravelPreferences(destination="Rome", travelers=21, raw_text="rome")


def test_travel_preferences_accepts_trip_style_enum():
    prefs = TravelPreferences(destination="Bali", trip_style=TripStyle.BEACH, raw_text="bali")
    assert prefs.trip_style == TripStyle.BEACH


def test_travel_preferences_rejects_invalid_trip_style():
    with pytest.raises(ValidationError):
        TravelPreferences(destination="Bali", trip_style="volcano", raw_text="bali")


def test_travel_preferences_defaults_are_empty_lists():
    prefs = TravelPreferences(destination="Cairo", raw_text="cairo")
    assert prefs.interests == []
    assert prefs.must_see == []
    assert prefs.dietary_restrictions == []
    assert prefs.accessibility_needs == []


def test_travel_preferences_budget_tier_enum():
    prefs = TravelPreferences(
        destination="Reykjavik", budget_tier=BudgetTier.LUXURY, raw_text="iceland"
    )
    assert prefs.budget_tier == BudgetTier.LUXURY


def test_travel_preferences_duration_out_of_range():
    with pytest.raises(ValidationError):
        TravelPreferences(destination="Rome", duration_days=0, raw_text="rome")
    with pytest.raises(ValidationError):
        TravelPreferences(destination="Rome", duration_days=91, raw_text="rome")


def test_flight_option_valid():
    flight = FlightOption(
        airline="Delta",
        origin="JFK",
        destination="CDG",
        departure_time="2026-07-01T10:00:00",
        arrival_time="2026-07-01T22:00:00",
        duration_minutes=420,
        price=650.0,
    )
    assert flight.stops == 0
    assert flight.currency == "USD"


def test_flight_option_rejects_negative_price():
    with pytest.raises(ValidationError):
        FlightOption(
            airline="Delta",
            origin="JFK",
            destination="CDG",
            departure_time="2026-07-01T10:00:00",
            arrival_time="2026-07-01T22:00:00",
            duration_minutes=420,
            price=-1,
        )


def test_hotel_option_rating_bounds():
    with pytest.raises(ValidationError):
        HotelOption(
            name="Hotel X",
            address="123 Main St",
            lat=48.85,
            lng=2.35,
            rating=11,
            price_per_night=100,
        )


def test_hotel_option_valid():
    hotel = HotelOption(
        name="Hotel X", address="123 Main St", lat=48.85, lng=2.35, price_per_night=100
    )
    assert hotel.amenities == []


def test_attraction_default_visit_duration():
    attraction = Attraction(name="Louvre", lat=48.86, lng=2.33)
    assert attraction.estimated_visit_minutes == 90


def test_attraction_rejects_too_short_visit_duration():
    with pytest.raises(ValidationError):
        Attraction(name="Louvre", lat=48.86, lng=2.33, estimated_visit_minutes=5)


def test_budget_summary_remaining_and_spent():
    summary = BudgetSummary(total_budget=1000, spent_by_category={"flights": 400, "hotel": 300})
    assert summary.total_spent == 700
    assert summary.remaining == 300


def test_budget_summary_rejects_negative_total():
    with pytest.raises(ValidationError):
        BudgetSummary(total_budget=-1)
