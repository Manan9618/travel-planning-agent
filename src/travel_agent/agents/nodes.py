"""Node factories wrapping each tool for the planning StateGraph — Week 4 deliverable.

Every node catches exceptions from its tool call rather than letting them propagate
and crash the graph run: a failure is recorded in `errors` and the step is marked
`completed` regardless, so the supervisor doesn't retry it forever. The tools
themselves already retry transient failures and fall back to mock data internally
(Weeks 2-3); this is a second, coarser safety net at the orchestration layer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta

from langgraph.types import interrupt

from travel_agent.agents.state import PlanningState, PlanningStep
from travel_agent.models.core import (
    Attraction,
    FlightOption,
    HotelOption,
    Itinerary,
    Restaurant,
    TravelPreferences,
    WeatherForecast,
)
from travel_agent.tools.attraction_finder import AttractionFinderTool
from travel_agent.tools.budget_optimizer import BudgetOptimizer
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.conflict_resolver import ConflictResolver, detect_and_resolve
from travel_agent.tools.flight_search import FlightSearchTool
from travel_agent.tools.hotel_search import HotelSearchTool
from travel_agent.tools.itinerary_builder import ItineraryBuilder
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer
from travel_agent.tools.preference_parser import PreferenceParser
from travel_agent.tools.restaurant_finder import RestaurantFinderTool
from travel_agent.tools.travel_map_generator import TravelMapGenerator
from travel_agent.tools.weather_checker import WeatherCheckerTool
from travel_agent.utils.iata import city_to_iata

logger = logging.getLogger(__name__)

Node = Callable[[PlanningState], dict]

DEFAULT_TRIP_LEAD_DAYS = 30
DEFAULT_TRIP_LENGTH_DAYS = 4


def _trip_dates(prefs: dict) -> tuple[date, date]:
    start = date.fromisoformat(prefs["start_date"]) if prefs.get("start_date") else None
    end = date.fromisoformat(prefs["end_date"]) if prefs.get("end_date") else None
    if start is None:
        start = date.today() + timedelta(days=DEFAULT_TRIP_LEAD_DAYS)
    if end is None:
        duration = prefs.get("duration_days") or (DEFAULT_TRIP_LENGTH_DAYS + 1)
        end = start + timedelta(days=duration - 1)  # duration_days is inclusive of start day
    return start, end


def make_parse_preferences_node(parser: PreferenceParser) -> Node:
    def node(state: PlanningState) -> dict:
        try:
            prefs = parser.parse(state["raw_text"])
            return {
                "preferences": prefs.model_dump(mode="json"),
                "completed_steps": [PlanningStep.PARSE_PREFERENCES.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("parse_preferences failed: %s", exc)
            return {
                "preferences": None,
                "completed_steps": [PlanningStep.PARSE_PREFERENCES.value],
                "errors": [f"parse_preferences: {exc}"],
            }

    return node


def make_search_flights_node(tool: FlightSearchTool) -> Node:
    def node(state: PlanningState) -> dict:
        prefs = state["preferences"]
        try:
            origin_code = city_to_iata(prefs["origin"])
            dest_code = city_to_iata(prefs["destination"])
            if not origin_code or not dest_code:
                raise ValueError(
                    f"no IATA mapping for {prefs['origin']!r} or {prefs['destination']!r}"
                )
            depart, ret = _trip_dates(prefs)
            results = tool.search(
                origin_code,
                dest_code,
                depart,
                ret,
                max_results=5,
                max_price=prefs.get("budget_total"),
            )
            return {
                "flights": [f.model_dump(mode="json") for f in results],
                "completed_steps": [PlanningStep.SEARCH_FLIGHTS.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("search_flights failed: %s", exc)
            return {
                "flights": [],
                "completed_steps": [PlanningStep.SEARCH_FLIGHTS.value],
                "errors": [f"search_flights: {exc}"],
            }

    return node


def make_search_hotels_node(tool: HotelSearchTool) -> Node:
    def node(state: PlanningState) -> dict:
        prefs = state["preferences"]
        try:
            check_in, check_out = _trip_dates(prefs)
            results = tool.search(
                prefs["destination"], check_in, check_out, adults=prefs.get("travelers", 1)
            )
            return {
                "hotels": [h.model_dump(mode="json") for h in results],
                "completed_steps": [PlanningStep.SEARCH_HOTELS.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("search_hotels failed: %s", exc)
            return {
                "hotels": [],
                "completed_steps": [PlanningStep.SEARCH_HOTELS.value],
                "errors": [f"search_hotels: {exc}"],
            }

    return node


def make_find_attractions_node(tool: AttractionFinderTool) -> Node:
    def node(state: PlanningState) -> dict:
        prefs = state["preferences"]
        try:
            results = tool.search(prefs["destination"], interests=prefs.get("interests"))
            return {
                "attractions": [a.model_dump(mode="json") for a in results],
                "completed_steps": [PlanningStep.FIND_ATTRACTIONS.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("find_attractions failed: %s", exc)
            return {
                "attractions": [],
                "completed_steps": [PlanningStep.FIND_ATTRACTIONS.value],
                "errors": [f"find_attractions: {exc}"],
            }

    return node


def make_find_restaurants_node(tool: RestaurantFinderTool) -> Node:
    def node(state: PlanningState) -> dict:
        prefs = state["preferences"]
        try:
            results = tool.search(prefs["destination"])
            return {
                "restaurants": [r.model_dump(mode="json") for r in results],
                "completed_steps": [PlanningStep.FIND_RESTAURANTS.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("find_restaurants failed: %s", exc)
            return {
                "restaurants": [],
                "completed_steps": [PlanningStep.FIND_RESTAURANTS.value],
                "errors": [f"find_restaurants: {exc}"],
            }

    return node


def make_check_weather_node(tool: WeatherCheckerTool) -> Node:
    def node(state: PlanningState) -> dict:
        prefs = state["preferences"]
        try:
            start, end = _trip_dates(prefs)
            results = tool.get_forecast(prefs["destination"], start, end)
            return {
                "weather": [w.model_dump(mode="json") for w in results],
                "completed_steps": [PlanningStep.CHECK_WEATHER.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("check_weather failed: %s", exc)
            return {
                "weather": [],
                "completed_steps": [PlanningStep.CHECK_WEATHER.value],
                "errors": [f"check_weather: {exc}"],
            }

    return node


def make_build_itinerary_node(builder: ItineraryBuilder | MultiDayOptimizer) -> Node:
    def node(state: PlanningState) -> dict:
        try:
            hotels = state.get("hotels") or []
            if not hotels:
                raise ValueError("no hotel available to build an itinerary from")
            prefs = TravelPreferences(**state["preferences"])
            hotel = HotelOption(**hotels[0])
            attractions = [Attraction(**a) for a in state.get("attractions", [])]
            restaurants = [Restaurant(**r) for r in state.get("restaurants", [])]
            flights = state.get("flights") or []
            flight = FlightOption(**flights[0]) if flights else None
            weather = [WeatherForecast(**w) for w in state.get("weather", [])]

            itinerary = builder.build(
                prefs, hotel, attractions, restaurants, flight=flight, weather=weather
            )
            return {
                "itinerary": itinerary.model_dump(mode="json"),
                "completed_steps": [PlanningStep.BUILD_ITINERARY.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("build_itinerary failed: %s", exc)
            return {
                "itinerary": None,
                "completed_steps": [PlanningStep.BUILD_ITINERARY.value],
                "errors": [f"build_itinerary: {exc}"],
            }

    return node


def make_check_conflicts_node(detector: ConflictDetector, resolver: ConflictResolver) -> Node:
    def node(state: PlanningState) -> dict:
        try:
            itinerary_data = state.get("itinerary")
            if not itinerary_data:
                raise ValueError("no itinerary available to check for conflicts")
            itinerary = Itinerary(**itinerary_data)
            resolved_itinerary, log, unresolved = detect_and_resolve(itinerary, detector, resolver)
            return {
                "itinerary": resolved_itinerary.model_dump(mode="json"),
                "conflict_log": [entry.model_dump(mode="json") for entry in log],
                "unresolved_conflicts": [c.model_dump(mode="json") for c in unresolved],
                "completed_steps": [PlanningStep.CHECK_CONFLICTS.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("check_conflicts failed: %s", exc)
            return {
                "conflict_log": [],
                "unresolved_conflicts": [],
                "completed_steps": [PlanningStep.CHECK_CONFLICTS.value],
                "errors": [f"check_conflicts: {exc}"],
            }

    return node


def make_optimize_budget_node(optimizer: BudgetOptimizer) -> Node:
    def node(state: PlanningState) -> dict:
        try:
            itinerary_data = state.get("itinerary")
            if not itinerary_data:
                raise ValueError("no itinerary available to evaluate budget for")
            itinerary = Itinerary(**itinerary_data)
            evaluation = optimizer.evaluate(itinerary)
            return {
                "budget_evaluation": evaluation.model_dump(mode="json") if evaluation else None,
                "completed_steps": [PlanningStep.OPTIMIZE_BUDGET.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("optimize_budget failed: %s", exc)
            return {
                "budget_evaluation": None,
                "completed_steps": [PlanningStep.OPTIMIZE_BUDGET.value],
                "errors": [f"optimize_budget: {exc}"],
            }

    return node


def make_generate_map_node(generator: TravelMapGenerator) -> Node:
    def node(state: PlanningState) -> dict:
        try:
            itinerary_data = state.get("itinerary")
            if not itinerary_data:
                raise ValueError("no itinerary available to generate a map from")
            itinerary = Itinerary(**itinerary_data)
            map_html = generator.render_html(itinerary)
            return {
                "map_html": map_html,
                "completed_steps": [PlanningStep.GENERATE_MAP.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("generate_map failed: %s", exc)
            return {
                "map_html": None,
                "completed_steps": [PlanningStep.GENERATE_MAP.value],
                "errors": [f"generate_map: {exc}"],
            }

    return node


def make_human_review_node() -> Node:
    """Pauses the graph run (via LangGraph's interrupt()) whenever ConflictResolver
    couldn't fix every conflict on its own — e.g. a budget overrun that survives
    trimming every optional attraction/restaurant. Resuming requires a
    `Command(resume={"approved": bool})` call against the same thread_id; approving
    just accepts the itinerary as-is (the conflict stays logged, unresolved, for the
    record), since Week 6 doesn't yet have a mechanism for the user to specify a
    replacement action (e.g. "increase my budget instead") — that's a natural fit
    for the multi-turn refinement work in Week 21.
    """

    def node(state: PlanningState) -> dict:
        decision = interrupt(
            {
                "message": "Some conflicts couldn't be auto-resolved. Approve the itinerary?",
                "unresolved_conflicts": state.get("unresolved_conflicts", []),
            }
        )
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else False
        logger.info("Human review decision: approved=%s", approved)
        return {
            "completed_steps": [PlanningStep.HUMAN_REVIEW.value],
            "errors": [] if approved else ["human_review: user did not approve the itinerary"],
        }

    return node
