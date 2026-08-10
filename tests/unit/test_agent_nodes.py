from datetime import date
from unittest.mock import MagicMock

from travel_agent.agents.nodes import (
    make_build_itinerary_node,
    make_check_conflicts_node,
    make_check_weather_node,
    make_enrich_attractions_node,
    make_find_attractions_node,
    make_find_restaurants_node,
    make_generate_map_node,
    make_generate_pdf_node,
    make_optimize_budget_node,
    make_parse_preferences_node,
    make_search_flights_node,
    make_search_hotels_node,
)
from travel_agent.models.core import (
    Attraction,
    BudgetTier,
    Conflict,
    DayPlan,
    FlightOption,
    HotelOption,
    Itinerary,
    ItineraryItem,
    ResolutionLogEntry,
    Restaurant,
    TravelPreferences,
    WeatherForecast,
)
from travel_agent.tools.itinerary_builder import ItineraryBuilder
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer
from travel_agent.tools.unsplash_photo import CoverPhoto

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


def test_search_flights_node_converts_non_usd_budget_to_usd_max_price():
    tool = MagicMock()
    tool.search.return_value = []

    class FakeConverter:
        def to_usd(self, amount, currency):
            assert currency == "EUR"
            return amount * 2  # arbitrary, deterministic fake rate

    node = make_search_flights_node(tool, currency_converter=FakeConverter())
    prefs = {**BASE_PREFS, "budget_total": 1000, "budget_currency": "EUR"}
    node({"preferences": prefs})
    assert tool.search.call_args.kwargs["max_price"] == 2000


def test_search_flights_node_defaults_to_usd_when_no_currency_given():
    tool = MagicMock()
    tool.search.return_value = []
    node = make_search_flights_node(tool)
    node({"preferences": BASE_PREFS})
    assert tool.search.call_args.kwargs["max_price"] == BASE_PREFS["budget_total"]


def test_search_flights_node_max_price_is_none_without_a_budget():
    tool = MagicMock()
    tool.search.return_value = []
    node = make_search_flights_node(tool)
    prefs = {**BASE_PREFS, "budget_total": None}
    node({"preferences": prefs})
    assert tool.search.call_args.kwargs["max_price"] is None


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


def test_search_hotels_node_passes_budget_tier_through():
    tool = MagicMock()
    tool.search.return_value = []
    node = make_search_hotels_node(tool)
    node({"preferences": {**BASE_PREFS, "budget_tier": "luxury"}})
    assert tool.search.call_args.kwargs["budget_tier"] == BudgetTier.LUXURY


def test_search_hotels_node_no_budget_tier_passes_none():
    tool = MagicMock()
    tool.search.return_value = []
    node = make_search_hotels_node(tool)
    node({"preferences": BASE_PREFS})  # BASE_PREFS has no budget_tier key
    assert tool.search.call_args.kwargs["budget_tier"] is None


def test_search_hotels_node_searches_every_destination():
    tool = MagicMock()
    tool.search.side_effect = lambda dest, *a, **kw: [
        HotelOption(name=f"{dest} Hotel", address=dest, lat=1, lng=1, price_per_night=100)
    ]
    node = make_search_hotels_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert tool.search.call_count == 2
    assert {h["name"] for h in result["hotels"]} == {"Paris Hotel", "Rome Hotel"}


def test_search_hotels_node_tags_each_result_with_its_destination():
    tool = MagicMock()
    tool.search.side_effect = lambda dest, *a, **kw: [
        HotelOption(name="X", address=dest, lat=1, lng=1, price_per_night=100)
    ]
    node = make_search_hotels_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert {h["destination"] for h in result["hotels"]} == {"Paris", "Rome"}


def test_search_hotels_node_one_destination_failing_does_not_lose_the_others():
    tool = MagicMock()

    def side_effect(dest, *a, **kw):
        if dest == "Rome":
            raise RuntimeError("rome api down")
        return [HotelOption(name="Hotel X", address="Paris", lat=1, lng=1, price_per_night=100)]

    tool.search.side_effect = side_effect
    node = make_search_hotels_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert len(result["hotels"]) == 1
    assert result["hotels"][0]["name"] == "Hotel X"
    assert "rome api down" in result["errors"][0]


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


def test_find_attractions_node_searches_every_destination():
    tool = MagicMock()
    tool.search.side_effect = lambda dest, **kw: [Attraction(name=f"{dest} spot", lat=1, lng=1)]
    node = make_find_attractions_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert tool.search.call_count == 2
    assert {a["name"] for a in result["attractions"]} == {"Paris spot", "Rome spot"}


def test_find_attractions_node_tags_each_result_with_its_destination():
    tool = MagicMock()
    tool.search.side_effect = lambda dest, **kw: [Attraction(name="X", lat=1, lng=1)]
    node = make_find_attractions_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert {a["destination"] for a in result["attractions"]} == {"Paris", "Rome"}


def test_find_attractions_node_one_destination_failing_does_not_lose_the_others():
    tool = MagicMock()

    def side_effect(dest, **kw):
        if dest == "Rome":
            raise RuntimeError("rome api down")
        return [Attraction(name="Louvre", lat=48.86, lng=2.33)]

    tool.search.side_effect = side_effect
    node = make_find_attractions_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert len(result["attractions"]) == 1
    assert result["attractions"][0]["name"] == "Louvre"
    assert "rome api down" in result["errors"][0]


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


def test_find_restaurants_node_searches_every_destination():
    tool = MagicMock()
    tool.search.side_effect = lambda dest: [Restaurant(name=f"{dest} cafe", lat=1, lng=1)]
    node = make_find_restaurants_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert tool.search.call_count == 2
    assert {r["name"] for r in result["restaurants"]} == {"Paris cafe", "Rome cafe"}


def test_find_restaurants_node_tags_each_result_with_its_destination():
    tool = MagicMock()
    tool.search.side_effect = lambda dest: [Restaurant(name="X", lat=1, lng=1)]
    node = make_find_restaurants_node(tool)
    prefs = {**BASE_PREFS, "additional_destinations": ["Rome"]}
    result = node({"preferences": prefs})
    assert {r["destination"] for r in result["restaurants"]} == {"Paris", "Rome"}


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


def test_build_itinerary_node_passes_all_hotels_to_a_multi_day_optimizer():
    builder = MagicMock(spec=MultiDayOptimizer)
    fake_itinerary = MagicMock()
    fake_itinerary.model_dump.return_value = {"days": []}
    builder.build.return_value = fake_itinerary

    state = _state_with_full_search_results()
    state["hotels"] = [
        HotelOption(
            name="Paris Hotel", address="Paris", lat=48.85, lng=2.35, price_per_night=100
        ).model_dump(mode="json"),
        HotelOption(
            name="Rome Hotel", address="Rome", lat=41.9, lng=12.5, price_per_night=120
        ).model_dump(mode="json"),
    ]
    node = make_build_itinerary_node(builder)
    node(state)

    call_kwargs = builder.build.call_args.kwargs
    assert [h.name for h in call_kwargs["hotels"]] == ["Paris Hotel", "Rome Hotel"]


def test_build_itinerary_node_does_not_pass_hotels_to_a_plain_itinerary_builder():
    builder = MagicMock(spec=ItineraryBuilder)
    fake_itinerary = MagicMock()
    fake_itinerary.model_dump.return_value = {"days": []}
    builder.build.return_value = fake_itinerary

    node = make_build_itinerary_node(builder)
    node(_state_with_full_search_results())

    assert "hotels" not in builder.build.call_args.kwargs


# --- check_conflicts ---------------------------------------------------


def _minimal_itinerary_dict():
    prefs = TravelPreferences(destination="Paris", raw_text="test")
    return Itinerary(preferences=prefs, days=[]).model_dump(mode="json")


def _itinerary_dict_with_items(items):
    prefs = TravelPreferences(destination="Paris", raw_text="test")
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=items)
    return Itinerary(preferences=prefs, days=[day]).model_dump(mode="json")


def _attraction_item(title="Eiffel Tower"):
    return ItineraryItem(
        time_slot="morning",
        start_time="2026-09-01T09:00:00",
        end_time="2026-09-01T11:00:00",
        activity_type="attraction",
        title=title,
    )


# --- enrich_attractions -------------------------------------------------


def test_enrich_attractions_node_sets_photo_and_description():
    photo_tool = MagicMock()
    photo_tool.get_photo.return_value = CoverPhoto(
        url="https://images.unsplash.com/eiffel",
        photographer_name="Jane",
        photographer_url="https://x",
    )
    description_tool = MagicMock()
    description_tool.describe.return_value = {"Eiffel Tower": "An iconic iron lattice tower."}

    node = make_enrich_attractions_node(photo_tool, description_tool)
    state = {"itinerary": _itinerary_dict_with_items([_attraction_item()])}
    result = node(state)

    item = result["itinerary"]["days"][0]["items"][0]
    assert item["photo_url"] == "https://images.unsplash.com/eiffel"
    assert item["description"] == "An iconic iron lattice tower."
    assert result["completed_steps"] == ["enrich_attractions"]
    assert result["errors"] == []


def test_enrich_attractions_node_queries_title_and_destination():
    photo_tool = MagicMock()
    photo_tool.get_photo.return_value = None
    description_tool = MagicMock()
    description_tool.describe.return_value = {}

    node = make_enrich_attractions_node(photo_tool, description_tool)
    node({"itinerary": _itinerary_dict_with_items([_attraction_item("Louvre Museum")])})

    photo_tool.get_photo.assert_called_once_with("Louvre Museum Paris", thumbnail=True)
    description_tool.describe.assert_called_once_with(["Louvre Museum"], "Paris")


def test_enrich_attractions_node_skips_non_attraction_items():
    restaurant_item = ItineraryItem(
        time_slot="evening",
        start_time="2026-09-01T19:00:00",
        end_time="2026-09-01T20:00:00",
        activity_type="restaurant",
        title="Le Comptoir",
    )
    photo_tool = MagicMock()
    description_tool = MagicMock()
    description_tool.describe.return_value = {}

    node = make_enrich_attractions_node(photo_tool, description_tool)
    result = node({"itinerary": _itinerary_dict_with_items([restaurant_item])})

    photo_tool.get_photo.assert_not_called()
    description_tool.describe.assert_called_once_with([], "Paris")
    assert result["itinerary"]["days"][0]["items"][0]["photo_url"] is None


def test_enrich_attractions_node_no_itinerary_records_error():
    node = make_enrich_attractions_node(MagicMock(), MagicMock())
    result = node({"itinerary": None})

    assert result["completed_steps"] == ["enrich_attractions"]
    assert "no itinerary available" in result["errors"][0]
    assert "itinerary" not in result


def test_enrich_attractions_node_tool_exception_records_error_without_wiping_itinerary():
    photo_tool = MagicMock()
    photo_tool.get_photo.side_effect = RuntimeError("rate limited")
    description_tool = MagicMock()
    description_tool.describe.return_value = {}

    node = make_enrich_attractions_node(photo_tool, description_tool)
    result = node({"itinerary": _itinerary_dict_with_items([_attraction_item()])})

    assert result["completed_steps"] == ["enrich_attractions"]
    assert "rate limited" in result["errors"][0]
    assert "itinerary" not in result


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


# --- generate_pdf ---------------------------------------------------
# render_map_thumbnail=False in every test here: thumbnail rasterization uses
# a real headless browser (Week 13), which is covered by its own dedicated
# test and the live-test script — node-level tests just verify wiring.


def test_generate_pdf_node_success(tmp_path):
    pdf_generator = MagicMock()
    map_generator = MagicMock()
    node = make_generate_pdf_node(
        pdf_generator, map_generator, output_dir=str(tmp_path), render_map_thumbnail=False
    )
    result = node({"itinerary": _minimal_itinerary_dict()})

    assert result["completed_steps"] == ["generate_pdf"]
    assert result["errors"] == []
    assert result["pdf_path"].startswith(str(tmp_path))
    assert "paris" in result["pdf_path"].lower()
    pdf_generator.generate.assert_called_once()
    _, kwargs = pdf_generator.generate.call_args
    assert kwargs["map_thumbnail_path"] is None
    map_generator.save.assert_not_called()  # skipped since render_map_thumbnail=False


def test_generate_pdf_node_passes_budget_evaluation_through(tmp_path):
    pdf_generator = MagicMock()
    node = make_generate_pdf_node(
        pdf_generator, MagicMock(), output_dir=str(tmp_path), render_map_thumbnail=False
    )
    budget_data = {
        "allocation": {"flights": 0, "hotel": 100, "food": 50, "activities": 50},
        "categories": [],
        "total_allocated": 200,
        "total_actual": 150,
        "adherence_score": 0.9,
        "suggestions": [],
    }
    node({"itinerary": _minimal_itinerary_dict(), "budget_evaluation": budget_data})
    _, kwargs = pdf_generator.generate.call_args
    assert kwargs["budget_evaluation"].adherence_score == 0.9


def test_generate_pdf_node_no_itinerary_records_error(tmp_path):
    node = make_generate_pdf_node(
        MagicMock(), MagicMock(), output_dir=str(tmp_path), render_map_thumbnail=False
    )
    result = node({"itinerary": None})
    assert result["completed_steps"] == ["generate_pdf"]
    assert result["pdf_path"] is None
    assert "no itinerary available" in result["errors"][0]


def test_generate_pdf_node_generator_exception_records_error(tmp_path):
    pdf_generator = MagicMock()
    pdf_generator.generate.side_effect = RuntimeError("boom")
    node = make_generate_pdf_node(
        pdf_generator, MagicMock(), output_dir=str(tmp_path), render_map_thumbnail=False
    )
    result = node({"itinerary": _minimal_itinerary_dict()})
    assert result["pdf_path"] is None
    assert "boom" in result["errors"][0]


def test_generate_pdf_node_thumbnail_failure_is_non_fatal(tmp_path):
    pdf_generator = MagicMock()
    map_generator = MagicMock()
    map_generator.save.side_effect = RuntimeError("browser unavailable")
    node = make_generate_pdf_node(
        pdf_generator, map_generator, output_dir=str(tmp_path), render_map_thumbnail=True
    )
    result = node({"itinerary": _minimal_itinerary_dict()})

    assert result["errors"] == []  # thumbnail failure doesn't fail the whole step
    assert result["completed_steps"] == ["generate_pdf"]
    _, kwargs = pdf_generator.generate.call_args
    assert kwargs["map_thumbnail_path"] is None
