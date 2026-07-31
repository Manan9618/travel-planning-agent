from datetime import date
from unittest.mock import MagicMock

from travel_agent.agents.nodes import (
    make_build_itinerary_node,
    make_check_conflicts_node,
    make_check_weather_node,
    make_find_attractions_node,
    make_find_restaurants_node,
    make_generate_map_node,
    make_optimize_budget_node,
    make_parse_preferences_node,
    make_search_flights_node,
    make_search_hotels_node,
)
from travel_agent.models.core import (
    Attraction,
    Conflict,
    FlightOption,
    HotelOption,
    Itinerary,
    ResolutionLogEntry,
    Restaurant,
    TravelPreferences,
    WeatherForecast,
)

BASE_PREFS = {
    "origin": "Boston",
    "destination": "Paris",
    "start_date": "2026-09-01",
    "end_date": "2026-09-05",
    "duration_days": 5,
    "travelers": 2,
    "budget_total": 2000,
    "raw_text": "5 days in Paris from Boston",
}


# --- parse_preferences ----------------------------------------------------


def test_parse_preferences_node_success():
    parser = MagicMock()
    parser.parse.return_value = TravelPreferences(destination="Paris", raw_text="paris trip")
    node = make_parse_preferences_node(parser)
    result = node({"raw_text": "paris trip"})
    assert result["preferences"]["destination"] == "Paris"
    assert result["completed_steps"] == ["parse_preferences"]
    assert result["errors"] == []


def test_parse_preferences_node_failure():
    parser = MagicMock()
    parser.parse.side_effect = ValueError("bad input")
    node = make_parse_preferences_node(parser)
    result = node({"raw_text": ""})
    assert result["preferences"] is None
    assert result["completed_steps"] == ["parse_preferences"]
    assert "bad input" in result["errors"][0]


# --- search_flights ---------------------------------------------------


def test_search_flights_node_success():
    tool = MagicMock()
    tool.search.return_value = [
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
    node = make_search_flights_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert len(result["flights"]) == 1
    assert result["completed_steps"] == ["search_flights"]
    assert result["errors"] == []
    tool.search.assert_called_once()
    call_args = tool.search.call_args[0]
    assert call_args[0] == "BOS"
    assert call_args[1] == "PAR"


def test_search_flights_node_unmapped_city_records_error():
    tool = MagicMock()
    node = make_search_flights_node(tool)
    prefs = {**BASE_PREFS, "origin": "Nowhereville"}
    result = node({"preferences": prefs})
    assert result["flights"] == []
    assert result["completed_steps"] == ["search_flights"]
    assert "no IATA mapping" in result["errors"][0]
    tool.search.assert_not_called()


def test_search_flights_node_tool_exception_records_error():
    tool = MagicMock()
    tool.search.side_effect = RuntimeError("api down")
    node = make_search_flights_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert result["flights"] == []
    assert "api down" in result["errors"][0]


# --- search_hotels ---------------------------------------------------


def test_search_hotels_node_success():
    tool = MagicMock()
    tool.search.return_value = [
        HotelOption(
            name="Hotel X", address="Paris, France", lat=48.85, lng=2.35, price_per_night=100
        )
    ]
    node = make_search_hotels_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert len(result["hotels"]) == 1
    assert result["completed_steps"] == ["search_hotels"]
    check_in, check_out = tool.search.call_args[0][1], tool.search.call_args[0][2]
    assert check_in == date(2026, 9, 1)
    assert check_out == date(2026, 9, 5)


def test_search_hotels_node_exception_records_error():
    tool = MagicMock()
    tool.search.side_effect = RuntimeError("down")
    node = make_search_hotels_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert result["hotels"] == []
    assert "down" in result["errors"][0]


# --- find_attractions ---------------------------------------------------


def test_find_attractions_node_success():
    tool = MagicMock()
    tool.search.return_value = [Attraction(name="Louvre", lat=48.86, lng=2.33)]
    node = make_find_attractions_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert len(result["attractions"]) == 1
    assert result["completed_steps"] == ["find_attractions"]


def test_find_attractions_node_exception_records_error():
    tool = MagicMock()
    tool.search.side_effect = RuntimeError("down")
    node = make_find_attractions_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert result["attractions"] == []
    assert "down" in result["errors"][0]


# --- find_restaurants ---------------------------------------------------


def test_find_restaurants_node_success():
    tool = MagicMock()
    tool.search.return_value = [Restaurant(name="Le Cafe", lat=48.85, lng=2.35)]
    node = make_find_restaurants_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert len(result["restaurants"]) == 1
    assert result["completed_steps"] == ["find_restaurants"]


def test_find_restaurants_node_exception_records_error():
    tool = MagicMock()
    tool.search.side_effect = RuntimeError("down")
    node = make_find_restaurants_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert result["restaurants"] == []
    assert "down" in result["errors"][0]


# --- check_weather ---------------------------------------------------


def test_check_weather_node_success():
    tool = MagicMock()
    tool.get_forecast.return_value = [
        WeatherForecast(
            day=date(2026, 9, 1),
            condition="Clear",
            temp_high_c=22,
            temp_low_c=14,
            rain_probability=0.1,
            wind_speed_kph=10,
            comfort_score=9.0,
        )
    ]
    node = make_check_weather_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert len(result["weather"]) == 1
    assert result["completed_steps"] == ["check_weather"]


def test_check_weather_node_exception_records_error():
    tool = MagicMock()
    tool.get_forecast.side_effect = RuntimeError("down")
    node = make_check_weather_node(tool)
    result = node({"preferences": BASE_PREFS})
    assert result["weather"] == []
    assert "down" in result["errors"][0]


def test_check_weather_node_uses_duration_days_when_end_date_missing():
    tool = MagicMock()
    tool.get_forecast.return_value = []
    node = make_check_weather_node(tool)
    prefs = {**BASE_PREFS, "end_date": None, "duration_days": 5}
    node({"preferences": prefs})
    start, end = tool.get_forecast.call_args[0][1], tool.get_forecast.call_args[0][2]
    assert (end - start).days == 4  # 5-day trip inclusive of start day


# --- build_itinerary ---------------------------------------------------


def _state_with_full_search_results():
    return {
        "preferences": BASE_PREFS,
        "hotels": [
            HotelOption(
                name="Hotel X", address="Paris, France", lat=48.85, lng=2.35, price_per_night=100
            ).model_dump(mode="json")
        ],
        "flights": [
            FlightOption(
                airline="AF",
                origin="BOS",
                destination="PAR",
                departure_time="2026-09-01T02:00:00",
                arrival_time="2026-09-01T14:00:00",
                duration_minutes=420,
                price=650,
            ).model_dump(mode="json")
        ],
        "attractions": [Attraction(name="Louvre", lat=48.86, lng=2.33).model_dump(mode="json")],
        "restaurants": [Restaurant(name="Le Cafe", lat=48.85, lng=2.35).model_dump(mode="json")],
        "weather": [
            WeatherForecast(
                day="2026-09-01",
                condition="Clear",
                temp_high_c=22,
                temp_low_c=14,
                rain_probability=0.1,
                wind_speed_kph=10,
                comfort_score=9.0,
            ).model_dump(mode="json")
        ],
    }


def test_build_itinerary_node_success():
    builder = MagicMock()
    fake_itinerary = MagicMock()
    fake_itinerary.model_dump.return_value = {"days": []}
    builder.build.return_value = fake_itinerary

    node = make_build_itinerary_node(builder)
    result = node(_state_with_full_search_results())

    assert result["itinerary"] == {"days": []}
    assert result["completed_steps"] == ["build_itinerary"]
    assert result["errors"] == []
    builder.build.assert_called_once()


def test_build_itinerary_node_passes_weather_forecasts_to_builder():
    builder = MagicMock()
    fake_itinerary = MagicMock()
    fake_itinerary.model_dump.return_value = {"days": []}
    builder.build.return_value = fake_itinerary

    node = make_build_itinerary_node(builder)
    node(_state_with_full_search_results())

    call_kwargs = builder.build.call_args.kwargs
    assert len(call_kwargs["weather"]) == 1
    assert call_kwargs["weather"][0].condition == "Clear"


def test_build_itinerary_node_no_hotel_records_error():
    builder = MagicMock()
    state = _state_with_full_search_results()
    state["hotels"] = []
    node = make_build_itinerary_node(builder)
    result = node(state)

    assert result["itinerary"] is None
    assert result["completed_steps"] == ["build_itinerary"]
    assert "no hotel available" in result["errors"][0]
    builder.build.assert_not_called()


def test_build_itinerary_node_no_flight_still_succeeds():
    builder = MagicMock()
    fake_itinerary = MagicMock()
    fake_itinerary.model_dump.return_value = {"days": []}
    builder.build.return_value = fake_itinerary

    state = _state_with_full_search_results()
    state["flights"] = []
    node = make_build_itinerary_node(builder)
    result = node(state)

    assert result["errors"] == []
    call_kwargs = builder.build.call_args.kwargs
    assert call_kwargs["flight"] is None


def test_build_itinerary_node_builder_exception_records_error():
    builder = MagicMock()
    builder.build.side_effect = RuntimeError("scheduling failed")
    node = make_build_itinerary_node(builder)
    result = node(_state_with_full_search_results())

    assert result["itinerary"] is None
    assert "scheduling failed" in result["errors"][0]


# --- check_conflicts ---------------------------------------------------


def _minimal_itinerary_dict():
    prefs = TravelPreferences(destination="Paris", raw_text="test")
    return Itinerary(preferences=prefs, days=[]).model_dump(mode="json")


def test_check_conflicts_node_no_unresolved_conflicts():
    detector = MagicMock()
    resolver = MagicMock()
    detector.detect.return_value = []  # detect_and_resolve calls detector.detect internally

    node = make_check_conflicts_node(detector, resolver)
    result = node({"itinerary": _minimal_itinerary_dict()})

    assert result["completed_steps"] == ["check_conflicts"]
    assert result["conflict_log"] == []
    assert result["unresolved_conflicts"] == []
    assert result["errors"] == []


def test_check_conflicts_node_reports_unresolved_conflicts():
    detector = MagicMock()
    resolver = MagicMock()
    conflict = Conflict(day_number=0, conflict_type="budget_overrun", description="too expensive")
    entry = ResolutionLogEntry(
        day_number=0, conflict_type="budget_overrun", action="tried and failed", resolved=False
    )
    itinerary = Itinerary(preferences=TravelPreferences(destination="Paris", raw_text="t"), days=[])

    detector.detect.return_value = [conflict]  # same unresolved conflict every pass
    resolver.resolve.return_value = (itinerary, [entry], [conflict])

    node = make_check_conflicts_node(detector, resolver)
    result = node({"itinerary": _minimal_itinerary_dict()})

    assert result["completed_steps"] == ["check_conflicts"]
    assert len(result["unresolved_conflicts"]) == 1
    assert result["unresolved_conflicts"][0]["conflict_type"] == "budget_overrun"
    assert result["conflict_log"][0]["resolved"] is False


def test_check_conflicts_node_no_itinerary_records_error():
    node = make_check_conflicts_node(MagicMock(), MagicMock())
    result = node({"itinerary": None})
    assert result["completed_steps"] == ["check_conflicts"]
    assert "no itinerary available" in result["errors"][0]


# --- optimize_budget ---------------------------------------------------


def test_optimize_budget_node_success():
    optimizer = MagicMock()
    fake_evaluation = MagicMock()
    fake_evaluation.model_dump.return_value = {"adherence_score": 0.9}
    optimizer.evaluate.return_value = fake_evaluation

    node = make_optimize_budget_node(optimizer)
    result = node({"itinerary": _minimal_itinerary_dict()})

    assert result["budget_evaluation"] == {"adherence_score": 0.9}
    assert result["completed_steps"] == ["optimize_budget"]
    assert result["errors"] == []
    optimizer.evaluate.assert_called_once()


def test_optimize_budget_node_no_budget_set_returns_none_without_error():
    optimizer = MagicMock()
    optimizer.evaluate.return_value = None

    node = make_optimize_budget_node(optimizer)
    result = node({"itinerary": _minimal_itinerary_dict()})

    assert result["budget_evaluation"] is None
    assert result["completed_steps"] == ["optimize_budget"]
    assert result["errors"] == []


def test_optimize_budget_node_no_itinerary_records_error():
    node = make_optimize_budget_node(MagicMock())
    result = node({"itinerary": None})
    assert result["completed_steps"] == ["optimize_budget"]
    assert "no itinerary available" in result["errors"][0]


def test_optimize_budget_node_optimizer_exception_records_error():
    optimizer = MagicMock()
    optimizer.evaluate.side_effect = RuntimeError("boom")
    node = make_optimize_budget_node(optimizer)
    result = node({"itinerary": _minimal_itinerary_dict()})
    assert result["budget_evaluation"] is None
    assert "boom" in result["errors"][0]


# --- generate_map ---------------------------------------------------


def test_generate_map_node_success():
    generator = MagicMock()
    generator.render_html.return_value = "<html>map</html>"

    node = make_generate_map_node(generator)
    result = node({"itinerary": _minimal_itinerary_dict()})

    assert result["map_html"] == "<html>map</html>"
    assert result["completed_steps"] == ["generate_map"]
    assert result["errors"] == []
    generator.render_html.assert_called_once()


def test_generate_map_node_no_itinerary_records_error():
    node = make_generate_map_node(MagicMock())
    result = node({"itinerary": None})
    assert result["completed_steps"] == ["generate_map"]
    assert result["map_html"] is None
    assert "no itinerary available" in result["errors"][0]


def test_generate_map_node_generator_exception_records_error():
    generator = MagicMock()
    generator.render_html.side_effect = RuntimeError("boom")
    node = make_generate_map_node(generator)
    result = node({"itinerary": _minimal_itinerary_dict()})
    assert result["map_html"] is None
    assert "boom" in result["errors"][0]
