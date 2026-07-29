"""Typed state for the LangGraph planning StateGraph — Week 4 deliverable.

State values are kept as plain dicts (via `model_dump(mode="json")`), not Pydantic
model instances, so the SQLite checkpointer can serialize/deserialize them reliably
across LangGraph versions without depending on custom type support.
"""

from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, TypedDict


class PlanningStep(str, Enum):
    PARSE_PREFERENCES = "parse_preferences"
    SEARCH_FLIGHTS = "search_flights"
    SEARCH_HOTELS = "search_hotels"
    FIND_ATTRACTIONS = "find_attractions"
    FIND_RESTAURANTS = "find_restaurants"
    CHECK_WEATHER = "check_weather"
    BUILD_ITINERARY = "build_itinerary"
    DONE = "done"


class PlanningState(TypedDict, total=False):
    raw_text: str
    preferences: dict | None
    flights: list[dict]
    hotels: list[dict]
    attractions: list[dict]
    restaurants: list[dict]
    weather: list[dict]
    itinerary: dict | None
    next_step: str
    completed_steps: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]


def determine_valid_steps(state: PlanningState) -> list[PlanningStep]:
    """Which steps the supervisor may legally choose next, given the current state.

    Encodes the hard dependency (preferences must exist before any search can run)
    and per-tool prerequisites (flights need an origin; weather needs a start date)
    as code rather than trusting the LLM to infer them, so the graph can't get stuck
    offering a step that would immediately fail for a structural reason.
    """
    completed = set(state.get("completed_steps", []))

    if not state.get("preferences"):
        if PlanningStep.PARSE_PREFERENCES.value in completed:
            return [PlanningStep.DONE]  # parsing already attempted and failed
        return [PlanningStep.PARSE_PREFERENCES]

    prefs = state["preferences"]
    remaining = []
    if PlanningStep.SEARCH_FLIGHTS.value not in completed and prefs.get("origin"):
        remaining.append(PlanningStep.SEARCH_FLIGHTS)
    if PlanningStep.SEARCH_HOTELS.value not in completed:
        remaining.append(PlanningStep.SEARCH_HOTELS)
    if PlanningStep.FIND_ATTRACTIONS.value not in completed:
        remaining.append(PlanningStep.FIND_ATTRACTIONS)
    if PlanningStep.FIND_RESTAURANTS.value not in completed:
        remaining.append(PlanningStep.FIND_RESTAURANTS)
    if PlanningStep.CHECK_WEATHER.value not in completed and prefs.get("start_date"):
        remaining.append(PlanningStep.CHECK_WEATHER)
    if remaining:
        return remaining

    if PlanningStep.BUILD_ITINERARY.value not in completed and state.get("hotels"):
        return [PlanningStep.BUILD_ITINERARY]
    return [PlanningStep.DONE]
