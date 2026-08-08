"""Planning StateGraph — Week 4 deliverable.

Wires a supervisor loop: supervisor picks a step -> the corresponding tool node runs
-> control returns to supervisor -> repeat until every valid step is exhausted, then
END. See `travel_agent.agents.state.determine_valid_steps` for the routing rules and
`travel_agent.agents.supervisor.SupervisorAgent` for how ties between independent,
simultaneously-valid steps are broken.
"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from travel_agent.agents.nodes import (
    make_build_itinerary_node,
    make_check_conflicts_node,
    make_check_weather_node,
    make_enrich_attractions_node,
    make_find_attractions_node,
    make_find_restaurants_node,
    make_generate_map_node,
    make_generate_pdf_node,
    make_human_review_node,
    make_optimize_budget_node,
    make_parse_preferences_node,
    make_search_flights_node,
    make_search_hotels_node,
)
from travel_agent.agents.state import PlanningState, PlanningStep
from travel_agent.agents.supervisor import SupervisorAgent
from travel_agent.tools.attraction_describer import AttractionDescriberTool
from travel_agent.tools.attraction_finder import AttractionFinderTool
from travel_agent.tools.budget_optimizer import BudgetOptimizer
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.conflict_resolver import ConflictResolver
from travel_agent.tools.flight_search import FlightSearchTool
from travel_agent.tools.hotel_search import HotelSearchTool
from travel_agent.tools.itinerary_builder import ItineraryBuilder
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer
from travel_agent.tools.pdf_generator import PDFGenerator
from travel_agent.tools.preference_parser import PreferenceParser
from travel_agent.tools.restaurant_finder import RestaurantFinderTool
from travel_agent.tools.travel_map_generator import TravelMapGenerator
from travel_agent.tools.unsplash_photo import UnsplashPhotoTool
from travel_agent.tools.weather_checker import WeatherCheckerTool

_WORKER_STEPS = [
    PlanningStep.PARSE_PREFERENCES,
    PlanningStep.SEARCH_FLIGHTS,
    PlanningStep.SEARCH_HOTELS,
    PlanningStep.FIND_ATTRACTIONS,
    PlanningStep.FIND_RESTAURANTS,
    PlanningStep.CHECK_WEATHER,
    PlanningStep.BUILD_ITINERARY,
    PlanningStep.ENRICH_ATTRACTIONS,
    PlanningStep.CHECK_CONFLICTS,
    PlanningStep.OPTIMIZE_BUDGET,
    PlanningStep.GENERATE_MAP,
    PlanningStep.GENERATE_PDF,
    PlanningStep.HUMAN_REVIEW,
]


def build_sqlite_checkpointer(db_path: str = "checkpoints.sqlite") -> SqliteSaver:
    """A checkpointer backed by a real file, for session persistence across runs.

    For tests / one-off runs, pass `sqlite3.connect(":memory:", check_same_thread=False)`
    directly to SqliteSaver instead of using this helper.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return checkpointer


def make_supervisor_node(supervisor: SupervisorAgent):
    def node(state: PlanningState) -> dict:
        next_step = supervisor.decide_next(state)
        return {"next_step": next_step.value}

    return node


def _route_from_supervisor(state: PlanningState) -> str:
    step = state["next_step"]
    return END if step == PlanningStep.DONE.value else step


def build_planning_graph(
    *,
    parser: PreferenceParser | None = None,
    flight_tool: FlightSearchTool | None = None,
    hotel_tool: HotelSearchTool | None = None,
    attraction_tool: AttractionFinderTool | None = None,
    restaurant_tool: RestaurantFinderTool | None = None,
    weather_tool: WeatherCheckerTool | None = None,
    itinerary_builder: ItineraryBuilder | MultiDayOptimizer | None = None,
    photo_tool: UnsplashPhotoTool | None = None,
    description_tool: AttractionDescriberTool | None = None,
    conflict_detector: ConflictDetector | None = None,
    conflict_resolver: ConflictResolver | None = None,
    budget_optimizer: BudgetOptimizer | None = None,
    map_generator: TravelMapGenerator | None = None,
    pdf_generator: PDFGenerator | None = None,
    pdf_output_dir: str = "output/pdfs",
    render_pdf_map_thumbnail: bool = True,
    supervisor: SupervisorAgent | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    parser = parser or PreferenceParser()
    flight_tool = flight_tool or FlightSearchTool()
    hotel_tool = hotel_tool or HotelSearchTool()
    attraction_tool = attraction_tool or AttractionFinderTool()
    restaurant_tool = restaurant_tool or RestaurantFinderTool()
    weather_tool = weather_tool or WeatherCheckerTool()
    # MultiDayOptimizer (Week 11) wraps ItineraryBuilder (Week 5/7) with
    # clustering/priority/budget-aware day-assignment, route-optimized visit
    # order, and cross-day balancing — same `.build()` signature, so it's a
    # drop-in default. Pass an explicit ItineraryBuilder() to opt out.
    itinerary_builder = itinerary_builder or MultiDayOptimizer()
    photo_tool = photo_tool or UnsplashPhotoTool()
    description_tool = description_tool or AttractionDescriberTool()
    conflict_detector = conflict_detector or ConflictDetector()
    conflict_resolver = conflict_resolver or ConflictResolver()
    budget_optimizer = budget_optimizer or BudgetOptimizer()
    map_generator = map_generator or TravelMapGenerator()
    pdf_generator = pdf_generator or PDFGenerator()
    supervisor = supervisor or SupervisorAgent()

    graph = StateGraph(PlanningState)
    graph.add_node("supervisor", make_supervisor_node(supervisor))
    graph.add_node(PlanningStep.PARSE_PREFERENCES.value, make_parse_preferences_node(parser))
    graph.add_node(PlanningStep.SEARCH_FLIGHTS.value, make_search_flights_node(flight_tool))
    graph.add_node(PlanningStep.SEARCH_HOTELS.value, make_search_hotels_node(hotel_tool))
    graph.add_node(PlanningStep.FIND_ATTRACTIONS.value, make_find_attractions_node(attraction_tool))
    graph.add_node(PlanningStep.FIND_RESTAURANTS.value, make_find_restaurants_node(restaurant_tool))
    graph.add_node(PlanningStep.CHECK_WEATHER.value, make_check_weather_node(weather_tool))
    graph.add_node(PlanningStep.BUILD_ITINERARY.value, make_build_itinerary_node(itinerary_builder))
    graph.add_node(
        PlanningStep.ENRICH_ATTRACTIONS.value,
        make_enrich_attractions_node(photo_tool, description_tool),
    )
    graph.add_node(
        PlanningStep.CHECK_CONFLICTS.value,
        make_check_conflicts_node(conflict_detector, conflict_resolver),
    )
    graph.add_node(PlanningStep.OPTIMIZE_BUDGET.value, make_optimize_budget_node(budget_optimizer))
    graph.add_node(PlanningStep.GENERATE_MAP.value, make_generate_map_node(map_generator))
    graph.add_node(
        PlanningStep.GENERATE_PDF.value,
        make_generate_pdf_node(
            pdf_generator,
            map_generator,
            output_dir=pdf_output_dir,
            render_map_thumbnail=render_pdf_map_thumbnail,
        ),
    )
    graph.add_node(PlanningStep.HUMAN_REVIEW.value, make_human_review_node())

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {**{step.value: step.value for step in _WORKER_STEPS}, END: END},
    )
    for step in _WORKER_STEPS:
        graph.add_edge(step.value, "supervisor")

    return graph.compile(checkpointer=checkpointer)
