from travel_agent.agents.state import PlanningStep, determine_valid_steps


def test_no_preferences_only_valid_step_is_parse():
    assert determine_valid_steps({}) == [PlanningStep.PARSE_PREFERENCES]


def test_failed_parse_terminates_to_done():
    state = {"preferences": None, "completed_steps": ["parse_preferences"]}
    assert determine_valid_steps(state) == [PlanningStep.DONE]


def test_all_steps_valid_once_preferences_present_with_origin_and_dates():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": ["parse_preferences"],
    }
    valid = determine_valid_steps(state)
    assert set(valid) == {
        PlanningStep.SEARCH_FLIGHTS,
        PlanningStep.SEARCH_HOTELS,
        PlanningStep.FIND_ATTRACTIONS,
        PlanningStep.FIND_RESTAURANTS,
        PlanningStep.CHECK_WEATHER,
    }


def test_flights_excluded_without_origin():
    state = {
        "preferences": {"origin": None, "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": ["parse_preferences"],
    }
    valid = determine_valid_steps(state)
    assert PlanningStep.SEARCH_FLIGHTS not in valid


def test_weather_excluded_without_start_date():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": None},
        "completed_steps": ["parse_preferences"],
    }
    valid = determine_valid_steps(state)
    assert PlanningStep.CHECK_WEATHER not in valid


def test_completed_steps_are_excluded_from_valid():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": ["parse_preferences", "search_flights", "search_hotels"],
    }
    valid = determine_valid_steps(state)
    assert PlanningStep.SEARCH_FLIGHTS not in valid
    assert PlanningStep.SEARCH_HOTELS not in valid
    assert PlanningStep.FIND_ATTRACTIONS in valid


def test_all_steps_completed_returns_done():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
        ],
    }
    assert determine_valid_steps(state) == [PlanningStep.DONE]


def test_all_steps_completed_without_origin_and_dates_returns_done():
    state = {
        "preferences": {"origin": None, "destination": "Paris", "start_date": None},
        "completed_steps": [
            "parse_preferences",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
        ],
    }
    assert determine_valid_steps(state) == [PlanningStep.DONE]


def test_all_search_steps_done_with_hotels_present_routes_to_build_itinerary():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
        ],
        "hotels": [{"name": "Test Hotel"}],
    }
    assert determine_valid_steps(state) == [PlanningStep.BUILD_ITINERARY]


def test_build_itinerary_completed_routes_to_enrich_attractions():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
        ],
        "hotels": [{"name": "Test Hotel"}],
    }
    assert determine_valid_steps(state) == [PlanningStep.ENRICH_ATTRACTIONS]


def test_enrich_attractions_completed_routes_to_check_conflicts():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
            "enrich_attractions",
        ],
        "hotels": [{"name": "Test Hotel"}],
    }
    assert determine_valid_steps(state) == [PlanningStep.CHECK_CONFLICTS]


def test_check_conflicts_completed_routes_to_optimize_budget():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
            "enrich_attractions",
            "check_conflicts",
        ],
        "hotels": [{"name": "Test Hotel"}],
        "unresolved_conflicts": [],
    }
    assert determine_valid_steps(state) == [PlanningStep.OPTIMIZE_BUDGET]


def test_optimize_budget_completed_routes_to_generate_map():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
            "enrich_attractions",
            "check_conflicts",
            "optimize_budget",
        ],
        "hotels": [{"name": "Test Hotel"}],
        "unresolved_conflicts": [],
    }
    assert determine_valid_steps(state) == [PlanningStep.GENERATE_MAP]


def test_generate_map_completed_routes_to_generate_pdf():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
            "enrich_attractions",
            "check_conflicts",
            "optimize_budget",
            "generate_map",
        ],
        "hotels": [{"name": "Test Hotel"}],
        "unresolved_conflicts": [],
    }
    assert determine_valid_steps(state) == [PlanningStep.GENERATE_PDF]


def test_generate_pdf_completed_with_no_unresolved_conflicts_returns_done():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
            "enrich_attractions",
            "check_conflicts",
            "optimize_budget",
            "generate_map",
            "generate_pdf",
        ],
        "hotels": [{"name": "Test Hotel"}],
        "unresolved_conflicts": [],
    }
    assert determine_valid_steps(state) == [PlanningStep.DONE]


def test_generate_pdf_completed_with_unresolved_conflicts_routes_to_human_review():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
            "enrich_attractions",
            "check_conflicts",
            "optimize_budget",
            "generate_map",
            "generate_pdf",
        ],
        "hotels": [{"name": "Test Hotel"}],
        "unresolved_conflicts": [{"conflict_type": "budget_overrun"}],
    }
    assert determine_valid_steps(state) == [PlanningStep.HUMAN_REVIEW]


def test_human_review_completed_returns_done_even_with_unresolved_conflicts():
    state = {
        "preferences": {"origin": "Boston", "destination": "Paris", "start_date": "2026-09-01"},
        "completed_steps": [
            "parse_preferences",
            "search_flights",
            "search_hotels",
            "find_attractions",
            "find_restaurants",
            "check_weather",
            "build_itinerary",
            "enrich_attractions",
            "check_conflicts",
            "optimize_budget",
            "generate_map",
            "generate_pdf",
            "human_review",
        ],
        "hotels": [{"name": "Test Hotel"}],
        "unresolved_conflicts": [{"conflict_type": "budget_overrun"}],
    }
    assert determine_valid_steps(state) == [PlanningStep.DONE]
