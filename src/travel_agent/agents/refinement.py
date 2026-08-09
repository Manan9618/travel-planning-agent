"""Incremental refinement — Week 21 deliverable.

`/refine` (Week 15) always re-ran every search tool under a fresh
`session_id`/thread_id — a full re-plan, not an in-place edit. That was a
deliberate choice to sidestep a real LangGraph gotcha:
`PlanningState.completed_steps` uses an additive (`operator.add`) reducer,
so feeding a shorter `completed_steps` list into an *existing* thread_id
would concatenate rather than reset it, silently making the supervisor
think old steps are still done. It was honest, correct infrastructure to
build on, but it meant a refinement chip like "more outdoor activities"
re-hit every external API (flights, hotels, weather - all rate-limited or
quota-constrained) even though none of them depend on what changed.

This keeps the "always start a fresh thread_id" choice (still the right
way to avoid the reducer problem) but makes the SEED state for that fresh
thread selective: only the search steps whose actual inputs changed are
left un-completed, so the graph calls their tool for real; every other
already-completed search step is pre-seeded as completed with its
PREVIOUS result copied over, so the graph skips straight past it.
Itinerary assembly onward (`build_itinerary` -> `generate_pdf`) always
reruns regardless of what changed — it's fast, local computation (plus one
small enrich/narration LLM call), never an external rate-limited API, and
unlike the 5 independent search tools there's no similarly clean per-field
answer for "did this step's input actually change" once you're past the
search phase (see `agents/state.py::determine_valid_steps` — every step
after `build_itinerary` is a single linear dependency on the combined
search-phase output plus the full preference set).
"""

from __future__ import annotations

from travel_agent.agents.state import PlanningState, PlanningStep

# Which search-phase step(s) a changed preference FIELD invalidates, i.e.
# which tool call was actually parameterized by that field (see each
# make_search_*_node in agents/nodes.py). A field not listed here (e.g.
# must_see, dietary_restrictions, trip_style, pace, priority_weights,
# budget_currency) only affects itinerary ASSEMBLY, which always reruns
# anyway — it never needs to invalidate a search result.
_FIELD_TO_INVALIDATED_STEPS: dict[str, frozenset[PlanningStep]] = {
    "destination": frozenset(
        {
            PlanningStep.SEARCH_FLIGHTS,
            PlanningStep.SEARCH_HOTELS,
            PlanningStep.FIND_ATTRACTIONS,
            PlanningStep.FIND_RESTAURANTS,
            PlanningStep.CHECK_WEATHER,
        }
    ),
    "origin": frozenset({PlanningStep.SEARCH_FLIGHTS}),
    "start_date": frozenset(
        {PlanningStep.SEARCH_FLIGHTS, PlanningStep.SEARCH_HOTELS, PlanningStep.CHECK_WEATHER}
    ),
    "end_date": frozenset(
        {PlanningStep.SEARCH_FLIGHTS, PlanningStep.SEARCH_HOTELS, PlanningStep.CHECK_WEATHER}
    ),
    "duration_days": frozenset(
        {PlanningStep.SEARCH_FLIGHTS, PlanningStep.SEARCH_HOTELS, PlanningStep.CHECK_WEATHER}
    ),
    "travelers": frozenset({PlanningStep.SEARCH_HOTELS}),  # HotelSearchTool.search(adults=...)
    "budget_total": frozenset(
        {PlanningStep.SEARCH_FLIGHTS}
    ),  # FlightSearchTool.search(max_price=...)
    "budget_tier": frozenset({PlanningStep.SEARCH_FLIGHTS}),
    "interests": frozenset(
        {PlanningStep.FIND_ATTRACTIONS}
    ),  # AttractionFinderTool.search(interests=...)
}

SEARCH_STEP_STATE_FIELD: dict[PlanningStep, str] = {
    PlanningStep.SEARCH_FLIGHTS: "flights",
    PlanningStep.SEARCH_HOTELS: "hotels",
    PlanningStep.FIND_ATTRACTIONS: "attractions",
    PlanningStep.FIND_RESTAURANTS: "restaurants",
    PlanningStep.CHECK_WEATHER: "weather",
}


def invalidated_search_steps(updates: dict) -> frozenset[PlanningStep]:
    """Which search-phase steps must actually re-run, given only the
    preference FIELDS this refinement changed (`updates` - the raw
    LLM-extracted fields from `PreferenceParser.parse_partial`, already
    filtered to non-empty values by the caller)."""
    invalidated: set[PlanningStep] = set()
    for field in updates:
        invalidated |= _FIELD_TO_INVALIDATED_STEPS.get(field, frozenset())
    return frozenset(invalidated)


def build_refinement_seed(
    raw_text: str,
    merged_preferences: dict,
    previous_state: PlanningState,
    updates: dict,
) -> dict:
    """The initial state for a refinement's fresh thread_id.

    `parse_preferences` plus every search step that (a) actually completed
    in `previous_state` and (b) isn't invalidated by what changed this time
    are pre-seeded as already-completed, with their previous result copied
    over — `determine_valid_steps` will see them as done and the graph
    skips straight past them, calling the tool only for whatever's left.
    A step that never completed last time (e.g. `search_flights` because
    no origin was known yet) is never seeded as complete regardless of
    `updates`, so a refinement that newly supplies the missing input (“I’m
    flying from Boston”) still runs it for real.
    """
    invalidated = invalidated_search_steps(updates)
    old_completed = set(previous_state.get("completed_steps", []))

    seed: dict = {
        "raw_text": raw_text,
        "preferences": merged_preferences,
        "errors": [],
        "completed_steps": [PlanningStep.PARSE_PREFERENCES.value],
    }
    for step, field in SEARCH_STEP_STATE_FIELD.items():
        if step.value in old_completed and step not in invalidated:
            seed["completed_steps"].append(step.value)
            seed[field] = previous_state.get(field, [])
    return seed
