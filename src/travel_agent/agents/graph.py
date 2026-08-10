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
from langgraph.checkpoint.postgres import PostgresSaver
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
from travel_agent.agents.state import PlanningState, PlanningStep, determine_valid_steps
from travel_agent.agents.supervisor import SupervisorAgent
from travel_agent.observability.metrics import instrument_node
from travel_agent.tools.attraction_describer import AttractionDescriberTool
from travel_agent.tools.attraction_finder import AttractionFinderTool
from travel_agent.tools.budget_optimizer import BudgetOptimizer
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.conflict_resolver import ConflictResolver
from travel_agent.tools.currency_converter import CurrencyConverter
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


def build_postgres_checkpointer(database_url: str) -> PostgresSaver:
    """A Postgres-backed checkpointer (Week 18), used instead of
    `build_sqlite_checkpointer` when `DATABASE_URL` is set (Docker Compose)
    - see `travel_agent.api.sessions.build_session_store` for the matching
    swap on the session-metadata side.

    `PostgresSaver.from_conn_string` is a `@contextmanager`-decorated
    generator (`with Connection.connect(...) as conn: yield cls(conn)`), not
    a plain factory. Entering it manually without keeping the context
    manager object itself alive is a real bug found live-testing this: with
    no reference left to it, Python's GC finalizes the generator, which
    throws `GeneratorExit` at the `yield` and runs the inner `with` block's
    `__exit__` - silently closing the connection out from under the
    returned checkpointer (surfaced as `psycopg.OperationalError: the
    connection is closed` on first real use, not at construction time).
    Stashing the context manager on the checkpointer keeps it referenced for
    the process's lifetime, the same "never explicitly closed, this outlives
    the request" choice `build_sqlite_checkpointer` already makes with its
    raw `sqlite3.connect()`.
    """
    context = PostgresSaver.from_conn_string(database_url)
    checkpointer = context.__enter__()
    checkpointer.setup()
    checkpointer._connection_context = context
    return checkpointer


def make_supervisor_node(supervisor: SupervisorAgent):
    def node(state: PlanningState) -> dict:
        # `determine_valid_steps` only ever returns more than one step for
        # the search phase (flights/hotels/attractions/restaurants/weather -
        # every other phase in state.py has exactly one legal next step).
        # Those five tools don't depend on each other or on one another's
        # results, so there's nothing for the supervisor's LLM tie-break to
        # add: fan all of them out to run in the same LangGraph superstep
        # (Week 20) instead of paying an LLM call just to pick an order that
        # doesn't affect correctness. See `_route_from_supervisor` below for
        # the list-return conditional-edge fan-out itself.
        valid = determine_valid_steps(state)
        if len(valid) > 1:
            return {"next_step": [step.value for step in valid]}
        next_step = supervisor.decide_next(state)
        return {"next_step": next_step.value}

    return node


def _route_from_supervisor(state: PlanningState) -> str | list[str]:
    step = state["next_step"]
    if isinstance(step, list):
        return step
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
    currency_converter: CurrencyConverter | None = None,
) -> CompiledStateGraph:
    parser = parser or PreferenceParser()
    flight_tool = flight_tool or FlightSearchTool()
    # Shared across every step that needs to compare a stated budget
    # (possibly non-USD) against real provider prices (always USD) — one
    # instance so its Redis-backed rate cache (see CurrencyConverter) is
    # actually shared across a run, not rebuilt per step.
    currency_converter = currency_converter or CurrencyConverter()
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
    budget_optimizer = budget_optimizer or BudgetOptimizer(currency_converter=currency_converter)
    map_generator = map_generator or TravelMapGenerator()
    pdf_generator = pdf_generator or PDFGenerator()
    supervisor = supervisor or SupervisorAgent()

    graph = StateGraph(PlanningState)

    # Every worker-step node (not "supervisor", a fast decision function
    # rather than a tool) is wrapped with Prometheus call-count/duration
    # tracking (Week 19) at registration time here, not inside each node
    # factory in nodes.py - instrumenting a new step never means touching
    # its own function.
    def add_instrumented_node(step: PlanningStep, node) -> None:
        graph.add_node(step.value, instrument_node(step.value, node))

    graph.add_node("supervisor", make_supervisor_node(supervisor))
    add_instrumented_node(PlanningStep.PARSE_PREFERENCES, make_parse_preferences_node(parser))
    add_instrumented_node(
        PlanningStep.SEARCH_FLIGHTS, make_search_flights_node(flight_tool, currency_converter)
    )
    add_instrumented_node(PlanningStep.SEARCH_HOTELS, make_search_hotels_node(hotel_tool))
    add_instrumented_node(
        PlanningStep.FIND_ATTRACTIONS, make_find_attractions_node(attraction_tool)
    )
    add_instrumented_node(
        PlanningStep.FIND_RESTAURANTS, make_find_restaurants_node(restaurant_tool)
    )
    add_instrumented_node(PlanningStep.CHECK_WEATHER, make_check_weather_node(weather_tool))
    add_instrumented_node(
        PlanningStep.BUILD_ITINERARY, make_build_itinerary_node(itinerary_builder)
    )
    add_instrumented_node(
        PlanningStep.ENRICH_ATTRACTIONS,
        make_enrich_attractions_node(photo_tool, description_tool),
    )
    add_instrumented_node(
        PlanningStep.CHECK_CONFLICTS,
        make_check_conflicts_node(conflict_detector, conflict_resolver),
    )
    add_instrumented_node(PlanningStep.OPTIMIZE_BUDGET, make_optimize_budget_node(budget_optimizer))
    add_instrumented_node(PlanningStep.GENERATE_MAP, make_generate_map_node(map_generator))
    add_instrumented_node(
        PlanningStep.GENERATE_PDF,
        make_generate_pdf_node(
            pdf_generator,
            map_generator,
            output_dir=pdf_output_dir,
            render_map_thumbnail=render_pdf_map_thumbnail,
        ),
    )
    add_instrumented_node(PlanningStep.HUMAN_REVIEW, make_human_review_node())

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {**{step.value: step.value for step in _WORKER_STEPS}, END: END},
    )
    for step in _WORKER_STEPS:
        graph.add_edge(step.value, "supervisor")

    return graph.compile(checkpointer=checkpointer)
