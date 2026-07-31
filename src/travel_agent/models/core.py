"""Core Pydantic data models shared across all agent tools (Week 1 foundation)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class TripStyle(str, Enum):
    CITY = "city"
    BEACH = "beach"
    ADVENTURE = "adventure"
    FAMILY = "family"
    SOLO = "solo"
    HONEYMOON = "honeymoon"
    BUSINESS = "business"
    ROAD_TRIP = "road_trip"


class BudgetTier(str, Enum):
    BACKPACKER = "backpacker"
    MID_RANGE = "mid_range"
    LUXURY = "luxury"


class Pace(str, Enum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    PACKED = "packed"


class TravelPreferences(BaseModel):
    """Structured output of PreferenceParser: the agent's understanding of what the user wants."""

    origin: str | None = Field(default=None, description="Departure city or airport")
    destination: str = Field(description="Primary destination city or region")
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    duration_days: int | None = Field(default=None, ge=1, le=90)
    travelers: int = Field(default=1, ge=1, le=20)
    budget_total: float | None = Field(default=None, ge=0)
    budget_currency: str = Field(default="USD")
    budget_tier: BudgetTier | None = Field(default=None)
    trip_style: TripStyle | None = Field(default=None)
    pace: Pace = Field(default=Pace.MODERATE)
    interests: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    accessibility_needs: list[str] = Field(default_factory=list)
    priority_weights: dict[str, float] = Field(
        default_factory=dict,
        description="e.g. {'accommodation': 0.5, 'dining': 0.2, 'activities': 0.3}",
    )
    raw_text: str = Field(description="Original natural language request, kept for traceability")

    @model_validator(mode="after")
    def _check_dates_and_duration(self) -> TravelPreferences:
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
            inferred = (self.end_date - self.start_date).days + 1
            if self.duration_days is None:
                self.duration_days = inferred
        return self


class FlightOption(BaseModel):
    airline: str = Field(description="IATA carrier code, or the OTA/gate name when unavailable")
    flight_number: str | None = None
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int = Field(ge=0)
    stops: int = Field(default=0, ge=0)
    price: float = Field(ge=0)
    currency: str = "USD"
    booking_link: str | None = None
    has_exact_time: bool = Field(
        default=True,
        description="False when only a date (no time-of-day) was available from the provider",
    )
    is_mock_data: bool = Field(
        default=False, description="True when the provider failed and this is a fallback"
    )


class HotelOption(BaseModel):
    name: str
    address: str
    lat: float
    lng: float
    rating: float | None = Field(
        default=None, ge=0, le=10, description="Guest review score, 0-10 scale (Booking.com)"
    )
    price_per_night: float = Field(ge=0)
    currency: str = "USD"
    amenities: list[str] = Field(default_factory=list)
    booking_link: str | None = None
    is_mock_data: bool = Field(
        default=False, description="True when the provider failed and this is a fallback"
    )


class Attraction(BaseModel):
    name: str
    category: str | None = None
    lat: float
    lng: float
    rating: float | None = Field(default=None, ge=0, le=5)
    opening_hours: str | None = None
    estimated_visit_minutes: int = Field(default=90, ge=15)
    price: float | None = Field(default=None, ge=0)
    description: str | None = None
    is_mock_data: bool = Field(
        default=False, description="True when the provider failed and this is a fallback"
    )


class Restaurant(BaseModel):
    name: str
    cuisine: str | None = None
    lat: float
    lng: float
    rating: float | None = Field(default=None, ge=0, le=5)
    price_level: int = Field(default=2, ge=1, le=4)
    opening_hours: str | None = None
    is_mock_data: bool = Field(
        default=False, description="True when the provider failed and this is a fallback"
    )


class WeatherForecast(BaseModel):
    day: date
    condition: str
    temp_high_c: float
    temp_low_c: float
    rain_probability: float = Field(ge=0, le=1)
    wind_speed_kph: float = Field(ge=0)
    comfort_score: float = Field(ge=0, le=10, description="Higher = better for outdoor activities")


class ItineraryItem(BaseModel):
    time_slot: str = Field(description="morning | afternoon | evening")
    start_time: datetime
    end_time: datetime
    activity_type: str = Field(
        description="flight | hotel_checkin | attraction | restaurant | transfer"
    )
    title: str
    category: str | None = Field(
        default=None,
        description="source category, e.g. Attraction.category; used for weather matching",
    )
    location: str | None = None
    lat: float | None = None
    lng: float | None = None
    cost: float | None = Field(default=None, ge=0)
    notes: str | None = None


class DayPlan(BaseModel):
    day_number: int = Field(ge=1)
    date: date
    items: list[ItineraryItem] = Field(default_factory=list)
    weather: WeatherForecast | None = None
    warnings: list[str] = Field(default_factory=list)


class BudgetSummary(BaseModel):
    total_budget: float = Field(ge=0)
    currency: str = "USD"
    spent_by_category: dict[str, float] = Field(default_factory=dict)

    @property
    def total_spent(self) -> float:
        return sum(self.spent_by_category.values())

    @property
    def remaining(self) -> float:
        return self.total_budget - self.total_spent


class Itinerary(BaseModel):
    preferences: TravelPreferences
    days: list[DayPlan] = Field(default_factory=list)
    flights: list[FlightOption] = Field(default_factory=list)
    hotel: HotelOption | None = None
    budget_summary: BudgetSummary | None = None


class Conflict(BaseModel):
    day_number: int = Field(ge=0, description="0 means a whole-trip-level conflict")
    conflict_type: str = Field(
        description="overlap | impossible_travel | budget_overrun | "
        "max_activities_exceeded | meal_time_violation"
    )
    description: str
    auto_resolvable: bool = True


class ResolutionLogEntry(BaseModel):
    day_number: int
    conflict_type: str
    action: str
    resolved: bool


class BudgetAllocation(BaseModel):
    flights: float = Field(ge=0)
    hotel: float = Field(ge=0)
    food: float = Field(ge=0)
    activities: float = Field(ge=0)


class CategoryEvaluation(BaseModel):
    category: str
    allocated: float
    actual: float
    difference: float = Field(description="actual - allocated; positive means over allocation")
    status: str = Field(description="under | on_target | over")


class BudgetEvaluation(BaseModel):
    allocation: BudgetAllocation
    categories: list[CategoryEvaluation]
    total_allocated: float
    total_actual: float
    adherence_score: float | None
    suggestions: list[str] = Field(default_factory=list)
