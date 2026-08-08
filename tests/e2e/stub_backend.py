"""Stub-tool-backed FastAPI app for the Week 17 E2E test suite.

A real browser drives the real React frontend over a real HTTP/WebSocket wire
protocol against a real running `uvicorn` process — but every external API tool
is replaced with a deterministic in-memory stub, the same pattern
`tests/api/conftest.py` and `tests/integration/test_planning_graph.py` already
use, so these tests are fast, free, and don't depend on live third-party
services, their rate limits, or their cost. Only this project's own code (the
LangGraph wiring, the FastAPI layer, and the entire React app) is exercised
for real.

Run standalone for manual poking:
    poetry run uvicorn tests.e2e.stub_backend:app --port 8811 --app-dir .
The E2E test fixtures (`tests/e2e/conftest.py`) launch this the same way.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from travel_agent.agents.graph import build_planning_graph
from travel_agent.agents.state import determine_valid_steps
from travel_agent.api.app import create_app
from travel_agent.api.sessions import SessionStore
from travel_agent.models.core import (
    Attraction,
    FlightOption,
    HotelOption,
    Restaurant,
    TravelPreferences,
)
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.conflict_resolver import ConflictResolver
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer
from travel_agent.tools.pdf_generator import PDFGenerator


class FixedTravelTime:
    def minutes_between(self, olat, olng, dlat, dlng, mode="driving"):
        return 15


class FixedDistanceMatrix:
    def compute_matrix(self, points, mode="driving"):
        n = len(points)
        return [[0 if i == j else 15 for j in range(n)] for i in range(n)]


class DeterministicSupervisor:
    def decide_next(self, state):
        return determine_valid_steps(state)[0]


class StubParser:
    def __init__(self, **overrides):
        self._overrides = overrides

    def parse(self, text, reference_date=None):
        defaults = dict(
            origin="Boston",
            destination="Paris",
            start_date="2026-09-01",
            end_date="2026-09-05",
            budget_total=2000,
            interests=["art", "museums"],
            raw_text=text,
        )
        defaults.update(self._overrides)
        return TravelPreferences(**defaults)

    def parse_partial(self, text, reference_date=None):
        if "outdoor" in text.lower():
            return {"interests": ["outdoor activities"]}
        if "3 day" in text.lower() or "three day" in text.lower():
            return {"duration_days": 3}
        return {}


class StubFlightTool:
    def search(self, *args, **kwargs):
        return [
            FlightOption(
                airline="AF",
                origin="BOS",
                destination="PAR",
                departure_time="2026-09-01T10:00:00",
                arrival_time="2026-09-01T22:00:00",
                duration_minutes=420,
                price=650,
            )
        ]


class StubHotelTool:
    def search(self, *args, **kwargs):
        return [
            HotelOption(
                name="Hotel Le Marais",
                address="Paris, France",
                lat=48.85,
                lng=2.35,
                price_per_night=120,
            )
        ]


class StubAttractionTool:
    def search(self, *args, **kwargs):
        return [
            Attraction(
                name="Louvre Museum", category="Museum", lat=48.8606, lng=2.3376, rating=4.8
            ),
            Attraction(
                name="Eiffel Tower", category="Landmark", lat=48.8584, lng=2.2945, rating=4.7
            ),
            Attraction(
                name="Notre-Dame Cathedral",
                category="Landmark",
                lat=48.8530,
                lng=2.3499,
                rating=4.6,
            ),
        ]


class StubRestaurantTool:
    def search(self, *args, **kwargs):
        return [Restaurant(name="Le Cafe", lat=48.85, lng=2.35, rating=4.0)]


class StubWeatherTool:
    def get_forecast(self, *args, **kwargs):
        return []


class StubPhotoTool:
    def get_cover_photo(self, destination):
        return None

    def get_photo(self, query, thumbnail=False):
        return None


class StubDescriptionTool:
    def describe(self, titles, destination):
        return {title: f"A well-known landmark in {destination}." for title in titles}


class FakeNarrator:
    async def narrate(self, itinerary):
        for token in ("Here's ", "your ", "trip", "!"):
            yield token


def build_stub_graph():
    return build_planning_graph(
        parser=StubParser(),
        flight_tool=StubFlightTool(),
        hotel_tool=StubHotelTool(),
        attraction_tool=StubAttractionTool(),
        restaurant_tool=StubRestaurantTool(),
        weather_tool=StubWeatherTool(),
        itinerary_builder=MultiDayOptimizer(
            travel_time_estimator=FixedTravelTime(), distance_matrix_tool=FixedDistanceMatrix()
        ),
        photo_tool=StubPhotoTool(),
        description_tool=StubDescriptionTool(),
        conflict_detector=ConflictDetector(travel_time_estimator=FixedTravelTime()),
        conflict_resolver=ConflictResolver(travel_time_estimator=FixedTravelTime()),
        pdf_generator=PDFGenerator(photo_tool=StubPhotoTool()),
        render_pdf_map_thumbnail=False,
        supervisor=DeterministicSupervisor(),
        checkpointer=MemorySaver(),
    )


app = create_app(
    graph=build_stub_graph(),
    session_store=SessionStore(":memory:"),
    narrator=FakeNarrator(),
    parser=StubParser(),
)
