from travel_agent.agents.refinement import (
    SEARCH_STEP_STATE_FIELD,
    build_refinement_seed,
    invalidated_search_steps,
)
from travel_agent.agents.state import PlanningStep

ALL_SEARCH_STEPS = frozenset(SEARCH_STEP_STATE_FIELD)


# --- invalidated_search_steps ------------------------------------------


def test_no_updates_invalidates_nothing():
    assert invalidated_search_steps({}) == frozenset()


def test_unmapped_field_invalidates_nothing():
    # must_see/dietary_restrictions/trip_style/pace/priority_weights/
    # budget_currency only affect itinerary assembly, which always reruns -
    # they should never force a search tool to re-fire.
    assert invalidated_search_steps({"must_see": ["Eiffel Tower"]}) == frozenset()
    assert invalidated_search_steps({"dietary_restrictions": ["vegetarian"]}) == frozenset()
    assert invalidated_search_steps({"pace": "relaxed"}) == frozenset()


def test_destination_change_invalidates_every_search_step():
    assert invalidated_search_steps({"destination": "Tokyo"}) == ALL_SEARCH_STEPS


def test_origin_change_invalidates_only_flights():
    assert invalidated_search_steps({"origin": "NYC"}) == frozenset({PlanningStep.SEARCH_FLIGHTS})


def test_date_change_invalidates_flights_hotels_and_weather_not_attractions_or_restaurants():
    invalidated = invalidated_search_steps({"start_date": "2026-10-01"})
    assert invalidated == frozenset(
        {PlanningStep.SEARCH_FLIGHTS, PlanningStep.SEARCH_HOTELS, PlanningStep.CHECK_WEATHER}
    )


def test_travelers_change_invalidates_only_hotels():
    assert invalidated_search_steps({"travelers": 3}) == frozenset({PlanningStep.SEARCH_HOTELS})


def test_budget_change_invalidates_only_flights():
    assert invalidated_search_steps({"budget_total": 5000}) == frozenset(
        {PlanningStep.SEARCH_FLIGHTS}
    )


def test_interests_change_invalidates_only_attractions():
    assert invalidated_search_steps({"interests": ["hiking"]}) == frozenset(
        {PlanningStep.FIND_ATTRACTIONS}
    )


def test_multiple_fields_union_their_invalidated_steps():
    invalidated = invalidated_search_steps({"origin": "NYC", "interests": ["hiking"]})
    assert invalidated == frozenset({PlanningStep.SEARCH_FLIGHTS, PlanningStep.FIND_ATTRACTIONS})


# --- build_refinement_seed ----------------------------------------------


def _completed_state(**overrides) -> dict:
    state = {
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
        ],
        "flights": [{"airline": "AF"}],
        "hotels": [{"name": "Hotel Paris"}],
        "attractions": [{"name": "Louvre"}],
        "restaurants": [{"name": "Cafe"}],
        "weather": [{"day": "2026-09-01"}],
    }
    state.update(overrides)
    return state


def test_seed_always_marks_parse_preferences_complete():
    seed = build_refinement_seed("less walking", {}, {}, {})
    assert seed["completed_steps"] == ["parse_preferences"]


def test_seed_carries_over_every_search_result_when_nothing_relevant_changed():
    previous = _completed_state()
    seed = build_refinement_seed("more museums please", {"destination": "Paris"}, previous, {})

    for step, field in SEARCH_STEP_STATE_FIELD.items():
        assert step.value in seed["completed_steps"]
        assert seed[field] == previous[field]


def test_seed_omits_an_invalidated_step_and_its_stale_data():
    previous = _completed_state()
    updates = {"origin": "New York"}
    seed = build_refinement_seed("actually I'm flying from NYC", {}, previous, updates)

    assert "search_flights" not in seed["completed_steps"]
    assert "flights" not in seed
    # unaffected steps are still carried over
    assert "search_hotels" in seed["completed_steps"]
    assert seed["hotels"] == previous["hotels"]


def test_seed_never_marks_a_step_complete_that_never_completed_before():
    # search_flights never ran last time (no origin was known) - a
    # refinement that doesn't mention flights at all must not fabricate a
    # "complete" flights result out of nothing.
    previous = _completed_state(
        completed_steps=[
            "parse_preferences",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
        ]
    )
    del previous["flights"]
    seed = build_refinement_seed("more museums", {}, previous, {})

    assert "search_flights" not in seed["completed_steps"]
    assert "flights" not in seed


def test_seed_reruns_flights_once_a_missing_origin_is_finally_supplied():
    previous = _completed_state(
        completed_steps=[
            "parse_preferences",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
        ]
    )
    del previous["flights"]
    updates = {"origin": "Boston"}
    seed = build_refinement_seed("flying from Boston", {}, previous, updates)

    assert "search_flights" not in seed["completed_steps"]


def test_seed_destination_change_invalidates_all_search_results():
    previous = _completed_state()
    updates = {"destination": "Tokyo"}
    seed = build_refinement_seed("actually let's go to Tokyo", {}, previous, updates)

    for step, field in SEARCH_STEP_STATE_FIELD.items():
        assert step.value not in seed["completed_steps"]
        assert field not in seed


def test_seed_preserves_raw_text_and_merged_preferences():
    merged = {"destination": "Paris", "interests": ["art", "hiking"]}
    seed = build_refinement_seed("add hiking", merged, _completed_state(), {"interests": ["h"]})
    assert seed["raw_text"] == "add hiking"
    assert seed["preferences"] == merged


def test_seed_resets_errors():
    previous = _completed_state(errors=["search_flights: boom"])
    seed = build_refinement_seed("more museums", {}, previous, {})
    assert seed["errors"] == []
