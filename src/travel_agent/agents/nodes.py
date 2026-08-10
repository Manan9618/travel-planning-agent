"""Node factories wrapping each tool for the planning StateGraph — Week 4 deliverable.

Every node catches exceptions from its tool call rather than letting them propagate
and crash the graph run: a failure is recorded in `errors` and the step is marked
`completed` regardless, so the supervisor doesn't retry it forever. The tools
themselves already retry transient failures and fall back to mock data internally
(Weeks 2-3); this is a second, coarser safety net at the orchestration layer.
"""

from __future__ import annotations

import contextlib
import logging
import tempfile
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from langgraph.types import interrupt

from travel_agent.agents.state import PlanningState, PlanningStep
from travel_agent.models.core import (
    Attraction,
    BudgetEvaluation,
    BudgetTier,
    FlightOption,
    HotelOption,
    Itinerary,
    Restaurant,
    TravelPreferences,
    WeatherForecast,
)
from travel_agent.tools.attraction_describer import AttractionDescriberTool
from travel_agent.tools.attraction_finder import AttractionFinderTool
from travel_agent.tools.budget_optimizer import BudgetOptimizer
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.conflict_resolver import ConflictResolver, detect_and_resolve
from travel_agent.tools.currency_converter import CurrencyConverter
from travel_agent.tools.flight_search import FlightSearchTool
from travel_agent.tools.hotel_search import HotelSearchTool
from travel_agent.tools.itinerary_builder import ItineraryBuilder
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer
from travel_agent.tools.pdf_generator import PDFGenerator
from travel_agent.tools.preference_parser import PreferenceParser
from travel_agent.tools.restaurant_finder import RestaurantFinderTool
from travel_agent.tools.travel_map_generator import TravelMapGenerator, render_thumbnail_png
from travel_agent.tools.unsplash_photo import UnsplashPhotoTool
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


def _all_destinations(prefs: dict) -> list[str]:
    """`destination` (primary) followed by `additional_destinations`, in
    visiting order — every attraction/restaurant/hotel search loops over
    this instead of just `prefs["destination"]`, so a single-destination
    trip (the overwhelming common case, `additional_destinations` empty)
    behaves exactly as before this list has just one entry."""
    return [prefs["destination"], *prefs.get("additional_destinations", [])]


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


def make_search_flights_node(
    tool: FlightSearchTool, currency_converter: CurrencyConverter | None = None
) -> Node:
    currency_converter = currency_converter or CurrencyConverter()

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
            budget_total = prefs.get("budget_total")
            # FlightSearchTool's own prices are always USD; a non-USD
            # budget_total (e.g. a "€1500" trip) needs converting before it
            # can act as a real price ceiling here — otherwise the raw
            # number gets compared against USD prices under the wrong
            # currency, either filtering out every valid flight or letting
            # through ones the traveler's real budget can't cover.
            max_price = (
                currency_converter.to_usd(budget_total, prefs.get("budget_currency") or "USD")
                if budget_total
                else None
            )
            results = tool.search(
                origin_code,
                dest_code,
                depart,
                ret,
                max_results=5,
                max_price=max_price,
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
        check_in, check_out = _trip_dates(prefs)
        budget_tier = BudgetTier(prefs["budget_tier"]) if prefs.get("budget_tier") else None
        found: list[dict] = []
        errors: list[str] = []
        # Each destination's hotel(s) searched against the same overall
        # trip window — HotelSearchTool returns price_per_night, not a
        # fixed total for the window, so this is a fine stand-in for not
        # yet knowing (at this point in the graph) how many nights
        # build_itinerary will actually allocate to each city.
        for destination in _all_destinations(prefs):
            try:
                results = tool.search(
                    destination,
                    check_in,
                    check_out,
                    adults=prefs.get("travelers", 1),
                    budget_tier=budget_tier,
                )
                found.extend(
                    {**h.model_dump(mode="json"), "destination": destination} for h in results
                )
            except Exception as exc:
                logger.warning("search_hotels failed for %s: %s", destination, exc)
                errors.append(f"search_hotels ({destination}): {exc}")
        return {
            "hotels": found,
            "completed_steps": [PlanningStep.SEARCH_HOTELS.value],
            "errors": errors,
        }

    return node


def make_find_attractions_node(tool: AttractionFinderTool) -> Node:
    def node(state: PlanningState) -> dict:
        prefs = state["preferences"]
        found: list[dict] = []
        errors: list[str] = []
        # Each destination searched independently, and one's failure
        # doesn't discard results already found for the others - the same
        # "one tool failing doesn't halt the graph" principle this module's
        # docstring states, just applied within a multi-destination step
        # instead of only across steps.
        for destination in _all_destinations(prefs):
            try:
                results = tool.search(destination, interests=prefs.get("interests"))
                found.extend(
                    {**a.model_dump(mode="json"), "destination": destination} for a in results
                )
            except Exception as exc:
                logger.warning("find_attractions failed for %s: %s", destination, exc)
                errors.append(f"find_attractions ({destination}): {exc}")
        return {
            "attractions": found,
            "completed_steps": [PlanningStep.FIND_ATTRACTIONS.value],
            "errors": errors,
        }

    return node


def make_find_restaurants_node(tool: RestaurantFinderTool) -> Node:
    def node(state: PlanningState) -> dict:
        prefs = state["preferences"]
        found: list[dict] = []
        errors: list[str] = []
        for destination in _all_destinations(prefs):
            try:
                results = tool.search(destination)
                found.extend(
                    {**r.model_dump(mode="json"), "destination": destination} for r in results
                )
            except Exception as exc:
                logger.warning("find_restaurants failed for %s: %s", destination, exc)
                errors.append(f"find_restaurants ({destination}): {exc}")
        return {
            "restaurants": found,
            "completed_steps": [PlanningStep.FIND_RESTAURANTS.value],
            "errors": errors,
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
            raw_hotels = state.get("hotels") or []
            if not raw_hotels:
                raise ValueError("no hotel available to build an itinerary from")
            prefs = TravelPreferences(**state["preferences"])
            hotels = [HotelOption(**h) for h in raw_hotels]
            hotel = hotels[0]
            attractions = [Attraction(**a) for a in state.get("attractions", [])]
            restaurants = [Restaurant(**r) for r in state.get("restaurants", [])]
            flights = state.get("flights") or []
            flight = FlightOption(**flights[0]) if flights else None
            weather = [WeatherForecast(**w) for w in state.get("weather", [])]

            # `hotels` (plural, every city's search results) is only
            # meaningful to MultiDayOptimizer's multi-destination path -
            # the plain ItineraryBuilder never gained multi-destination
            # support (it predates even Week 9's clustering), so it isn't
            # offered a parameter it has no use for.
            build_kwargs: dict = {"flight": flight, "weather": weather}
            if isinstance(builder, MultiDayOptimizer):
                build_kwargs["hotels"] = hotels

            itinerary = builder.build(prefs, hotel, attractions, restaurants, **build_kwargs)
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


def make_enrich_attractions_node(
    photo_tool: UnsplashPhotoTool, description_tool: AttractionDescriberTool
) -> Node:
    def node(state: PlanningState) -> dict:
        try:
            itinerary_data = state.get("itinerary")
            if not itinerary_data:
                raise ValueError("no itinerary available to enrich")
            itinerary = Itinerary(**itinerary_data)
            destination = itinerary.preferences.destination

            attraction_items = [
                item
                for day in itinerary.days
                for item in day.items
                if item.activity_type == "attraction"
            ]
            descriptions = description_tool.describe(
                [item.title for item in attraction_items], destination
            )
            for item in attraction_items:
                photo = photo_tool.get_photo(f"{item.title} {destination}", thumbnail=True)
                if photo:
                    item.photo_url = photo.url
                if item.title in descriptions:
                    item.description = descriptions[item.title]

            return {
                "itinerary": itinerary.model_dump(mode="json"),
                "completed_steps": [PlanningStep.ENRICH_ATTRACTIONS.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("enrich_attractions failed: %s", exc)
            return {
                "completed_steps": [PlanningStep.ENRICH_ATTRACTIONS.value],
                "errors": [f"enrich_attractions: {exc}"],
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


def make_generate_pdf_node(
    pdf_generator: PDFGenerator,
    map_generator: TravelMapGenerator,
    output_dir: str = "output/pdfs",
    render_map_thumbnail: bool = True,
) -> Node:
    """Renders the professional PDF itinerary (Week 14). A map thumbnail is
    rasterized fresh from the itinerary (Week 13's TravelMapGenerator +
    render_thumbnail_png) and embedded; if that rasterization fails for any
    reason (e.g. no headless browser installed), the PDF still generates,
    just without the embedded map image — the same graceful-degradation
    pattern used throughout this project rather than blocking the whole step
    on a non-essential piece. `render_map_thumbnail=False` skips it entirely
    (used by fast offline tests to avoid a real browser launch per run).
    """

    def node(state: PlanningState) -> dict:
        try:
            itinerary_data = state.get("itinerary")
            if not itinerary_data:
                raise ValueError("no itinerary available to generate a PDF from")
            itinerary = Itinerary(**itinerary_data)
            budget_data = state.get("budget_evaluation")
            budget_evaluation = BudgetEvaluation(**budget_data) if budget_data else None

            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            slug = itinerary.preferences.destination.lower().replace(" ", "_")
            output_path = out_dir / f"{slug}_{uuid.uuid4().hex[:8]}.pdf"

            with (
                tempfile.TemporaryDirectory() if render_map_thumbnail else contextlib.nullcontext()
            ) as tmp_dir:
                map_thumbnail_path = None
                if render_map_thumbnail:
                    try:
                        tmp_html = Path(tmp_dir) / "map.html"
                        tmp_png = Path(tmp_dir) / "map.png"
                        map_generator.save(itinerary, tmp_html)
                        render_thumbnail_png(tmp_html, tmp_png)
                        map_thumbnail_path = tmp_png
                    except Exception as exc:
                        logger.warning("map thumbnail rasterization failed for PDF: %s", exc)

                pdf_generator.generate(
                    itinerary,
                    output_path,
                    budget_evaluation=budget_evaluation,
                    map_thumbnail_path=map_thumbnail_path,
                )

            return {
                "pdf_path": str(output_path),
                "completed_steps": [PlanningStep.GENERATE_PDF.value],
                "errors": [],
            }
        except Exception as exc:
            logger.warning("generate_pdf failed: %s", exc)
            return {
                "pdf_path": None,
                "completed_steps": [PlanningStep.GENERATE_PDF.value],
                "errors": [f"generate_pdf: {exc}"],
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
