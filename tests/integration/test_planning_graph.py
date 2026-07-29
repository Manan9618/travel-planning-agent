"""Week 4 deliverable: end-to-end test of the compiled planning graph.

All tool calls and the supervisor's LLM are stubbed out (deterministic, no network),
so this verifies the graph's wiring, routing, and checkpoint persistence rather than
re-testing individual tools (see the Week 2/3 unit suites) or the real SupervisorAgent
(see test_supervisor.py).
"""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from travel_agent.agents.graph import build_planning_graph
from travel_agent.agents.state import PlanningState, determine_valid_steps
from travel_agent.models.core import (
    Attraction,
    FlightOption,
    HotelOption,
    Restaurant,
    TravelPreferences,
    WeatherForecast,
)


class DeterministicSupervisor:
    """Always picks the first structurally-valid step; no LLM involved."""

    def decide_next(self, state: PlanningState):
        return determine_valid_steps(state)[0]


class StubParser:
    def parse(self, text, reference_date=None):
        return TravelPreferences(
            origin="Boston",
            destination="Paris",
            start_date="2026-09-01",
            end_date="2026-09-05",
            budget_total=2000,
            interests=["art"],
            raw_text=text,
        )


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
                name="Hotel Paris",
                address="Paris, France",
                lat=48.85,
                lng=2.35,
                price_per_night=120,
            )
        ]


class StubAttractionTool:
    def search(self, *args, **kwargs):
        return [Attraction(name="Louvre", lat=48.86, lng=2.33, rating=4.8)]


class StubRestaurantTool:
    def search(self, *args, **kwargs):
        return [Restaurant(name="Le Cafe", lat=48.85, lng=2.35, rating=4.5)]


class StubWeatherTool:
    def get_forecast(self, *args, **kwargs):
        return [
            WeatherForecast(
                day="2026-09-01",
                condition="Clear",
                temp_high_c=22,
                temp_low_c=14,
                rain_probability=0.1,
                wind_speed_kph=10,
                comfort_score=9.0,
            )
        ]


class FailingFlightTool:
    def search(self, *args, **kwargs):
        raise RuntimeError("provider unreachable")


def _build_test_graph(checkpointer, flight_tool=None):
    return build_planning_graph(
        parser=StubParser(),
        flight_tool=flight_tool or StubFlightTool(),
        hotel_tool=StubHotelTool(),
        attraction_tool=StubAttractionTool(),
        restaurant_tool=StubRestaurantTool(),
        weather_tool=StubWeatherTool(),
        supervisor=DeterministicSupervisor(),
        checkpointer=checkpointer,
    )


def _memory_checkpointer():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return checkpointer, conn


def test_full_graph_run_populates_every_field():
    checkpointer, _ = _memory_checkpointer()
    graph = _build_test_graph(checkpointer)
    config = {"configurable": {"thread_id": "t1"}}

    result = graph.invoke(
        {"raw_text": "5 days in Paris from Boston", "errors": [], "completed_steps": []},
        config=config,
    )

    assert result["preferences"]["destination"] == "Paris"
    assert len(result["flights"]) == 1
    assert len(result["hotels"]) == 1
    assert len(result["attractions"]) == 1
    assert len(result["restaurants"]) == 1
    assert len(result["weather"]) == 1
    assert result["errors"] == []
    assert set(result["completed_steps"]) == {
        "parse_preferences",
        "search_flights",
        "search_hotels",
        "find_attractions",
        "find_restaurants",
        "check_weather",
    }


def test_graph_terminates_and_does_not_loop_forever():
    checkpointer, _ = _memory_checkpointer()
    graph = _build_test_graph(checkpointer)
    config = {"configurable": {"thread_id": "t2"}}
    # if routing were broken this would hang or exceed the recursion limit
    result = graph.invoke({"raw_text": "trip", "errors": [], "completed_steps": []}, config=config)
    assert result["completed_steps"].count("parse_preferences") == 1


def test_tool_failure_is_captured_without_halting_the_graph():
    checkpointer, _ = _memory_checkpointer()
    graph = _build_test_graph(checkpointer, flight_tool=FailingFlightTool())
    config = {"configurable": {"thread_id": "t3"}}

    result = graph.invoke(
        {"raw_text": "5 days in Paris from Boston", "errors": [], "completed_steps": []},
        config=config,
    )

    assert result["flights"] == []
    assert any("search_flights" in e for e in result["errors"])
    # every other step still completed despite the flight failure
    assert "search_hotels" in result["completed_steps"]
    assert "find_attractions" in result["completed_steps"]


def test_state_persists_across_fresh_connections():
    db_path = "/tmp/test_planning_graph_persistence.sqlite"
    conn1 = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer1 = SqliteSaver(conn1)
    checkpointer1.setup()
    graph1 = _build_test_graph(checkpointer1)
    config = {"configurable": {"thread_id": "persist-1"}}
    graph1.invoke(
        {"raw_text": "5 days in Paris from Boston", "errors": [], "completed_steps": []},
        config=config,
    )
    conn1.close()

    conn2 = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer2 = SqliteSaver(conn2)
    graph2 = _build_test_graph(checkpointer2)
    state = graph2.get_state(config)
    conn2.close()

    import os

    os.remove(db_path)

    assert state.values["preferences"]["destination"] == "Paris"
    assert len(state.values["flights"]) == 1


def test_no_origin_skips_flights_but_completes_everything_else():
    checkpointer, _ = _memory_checkpointer()

    class NoOriginParser:
        def parse(self, text, reference_date=None):
            return TravelPreferences(
                destination="Paris", start_date="2026-09-01", end_date="2026-09-05", raw_text=text
            )

    graph = build_planning_graph(
        parser=NoOriginParser(),
        flight_tool=StubFlightTool(),
        hotel_tool=StubHotelTool(),
        attraction_tool=StubAttractionTool(),
        restaurant_tool=StubRestaurantTool(),
        weather_tool=StubWeatherTool(),
        supervisor=DeterministicSupervisor(),
        checkpointer=checkpointer,
    )
    config = {"configurable": {"thread_id": "t4"}}
    result = graph.invoke(
        {"raw_text": "5 days in Paris", "errors": [], "completed_steps": []}, config=config
    )

    assert "search_flights" not in result["completed_steps"]
    assert result.get("flights", []) == []
    assert "search_hotels" in result["completed_steps"]
    assert "check_weather" in result["completed_steps"]
