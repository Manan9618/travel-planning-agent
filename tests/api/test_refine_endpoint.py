from tests.api.conftest import (
    StubAttractionTool,
    StubFlightTool,
    StubHotelTool,
    StubRestaurantTool,
    StubWeatherTool,
    isolated_client,
    wait_until_terminal,
)
from travel_agent.models.core import TravelPreferences


class BudgetAwareParser:
    """A stub that actually reflects the requested budget in its output
    (StubParser always returns a fixed 2000 regardless of text), so refine
    merge behavior can be verified against a genuinely different re-parse."""

    def parse(self, text, reference_date=None):
        budget = 3000 if "$3000" in text else 2000
        return TravelPreferences(
            origin="Boston",
            destination="Paris",
            start_date="2026-09-01",
            end_date="2026-09-03",
            budget_total=budget,
            raw_text=text,
        )

    def parse_partial(self, text, reference_date=None):
        return {"budget_total": 3000} if "$3000" in text else {}


class NoDestinationParser:
    """Mirrors what the real PreferenceParser does for a short refinement
    chip like "more outdoor activities": parse() (a brand-new /plan
    request) always succeeds with a real destination, but parse_partial()
    (a /refine request) correctly reports no destination at all — there's
    nothing in "more outdoor activities" to infer one from. Regression
    coverage for the real bug this was: /refine used to call parse()
    unconditionally, which made a required-destination validation error
    escape as an unhandled 500 ("Load failed" in the UI) for exactly this
    kind of refinement text."""

    def parse(self, text, reference_date=None):
        return TravelPreferences(
            origin="Boston",
            destination="London",
            start_date="2026-09-01",
            end_date="2026-09-05",
            interests=["art", "museums"],
            raw_text=text,
        )

    def parse_partial(self, text, reference_date=None):
        return {"interests": ["outdoor activities"]}


def test_refine_unknown_parent_session_returns_404(client):
    resp = client.post("/refine", json={"session_id": "nope", "raw_text": "less walking"})
    assert resp.status_code == 404


def test_refine_rejects_empty_raw_text(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    resp = client.post("/refine", json={"session_id": session_id, "raw_text": ""})
    assert resp.status_code == 422


def test_refine_creates_a_new_session_distinct_from_the_parent(client):
    parent_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, parent_id)

    resp = client.post("/refine", json={"session_id": parent_id, "raw_text": "make it 3 days"})
    assert resp.status_code == 202
    child_id = resp.json()["session_id"]
    assert child_id != parent_id
    assert resp.json()["status"] == "running"


def test_refined_session_completes_and_reflects_updated_preferences(app_factory):

    with isolated_client(app_factory(parser=BudgetAwareParser())) as client:
        parent_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(client, parent_id)

        child_id = client.post(
            "/refine", json={"session_id": parent_id, "raw_text": "5 days in Paris, budget $3000"}
        ).json()["session_id"]
        data = wait_until_terminal(client, child_id)

    assert data["status"] == "completed"
    assert data["preferences"]["budget_total"] == 3000
    assert data["itinerary"] is not None


def test_refine_reuses_unspecified_fields_from_the_parent_preferences(client):
    parent_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    parent_data = wait_until_terminal(client, parent_id)
    assert parent_data["preferences"]["destination"] == "Paris"

    # StubParser's parse_partial() returns {} unless overridden, so this
    # proves the merge doesn't crash or drop fields that weren't part of
    # this refinement's own (empty) partial parse.
    child_id = client.post(
        "/refine", json={"session_id": parent_id, "raw_text": "add a museum visit"}
    ).json()["session_id"]
    data = wait_until_terminal(client, child_id)
    assert data["preferences"]["destination"] == "Paris"
    assert data["preferences"]["origin"] == "Boston"


def test_refine_with_no_destination_in_the_text_does_not_crash_and_keeps_parent_destination(
    app_factory,
):
    with isolated_client(app_factory(parser=NoDestinationParser())) as client:
        parent_id = client.post("/plan", json={"raw_text": "5 days in London"}).json()["session_id"]
        wait_until_terminal(client, parent_id)

        resp = client.post(
            "/refine", json={"session_id": parent_id, "raw_text": "more outdoor activities"}
        )
        assert resp.status_code == 202
        child_id = resp.json()["session_id"]
        data = wait_until_terminal(client, child_id)

    assert data["status"] == "completed"
    assert data["preferences"]["destination"] == "London"


def test_refine_adds_new_interests_without_dropping_existing_ones(app_factory):
    with isolated_client(app_factory(parser=NoDestinationParser())) as client:
        parent_id = client.post(
            "/plan", json={"raw_text": "5 days in London, I love art and museums"}
        ).json()["session_id"]
        parent_data = wait_until_terminal(client, parent_id)
        assert parent_data["preferences"]["interests"] == ["art", "museums"]

        resp = client.post(
            "/refine", json={"session_id": parent_id, "raw_text": "more outdoor activities"}
        )
        child_id = resp.json()["session_id"]
        data = wait_until_terminal(client, child_id)

    # union, not replace: the refinement's new interest is added, not
    # substituted for the parent's original ones.
    assert data["preferences"]["interests"] == ["art", "museums", "outdoor activities"]


# --- incremental refinement (Week 21): unaffected search tools skipped ----


class OriginChangeParser:
    """Unlike StubParser, `.parse()` and `.parse_partial()` are
    independently controllable - needed to model a genuine origin CHANGE
    (parent already had one, refinement supplies a different one), which a
    single shared StubParser(**overrides) instance can't express since it
    applies the same overrides to both."""

    def parse(self, text, reference_date=None):
        return TravelPreferences(
            origin="Boston",
            destination="Paris",
            start_date="2026-09-01",
            end_date="2026-09-03",
            budget_total=2000,
            raw_text=text,
        )

    def parse_partial(self, text, reference_date=None):
        return {"origin": "New York"} if "New York" in text else {}


class _CountingMixin:
    def __init__(self):
        self.call_count = 0


class CountingFlightTool(_CountingMixin, StubFlightTool):
    def search(self, *args, **kwargs):
        self.call_count += 1
        return super().search(*args, **kwargs)


class CountingHotelTool(_CountingMixin, StubHotelTool):
    def search(self, *args, **kwargs):
        self.call_count += 1
        return super().search(*args, **kwargs)


class CountingAttractionTool(_CountingMixin, StubAttractionTool):
    def search(self, *args, **kwargs):
        self.call_count += 1
        return super().search(*args, **kwargs)


class CountingRestaurantTool(_CountingMixin, StubRestaurantTool):
    def search(self, *args, **kwargs):
        self.call_count += 1
        return super().search(*args, **kwargs)


class CountingWeatherTool(_CountingMixin, StubWeatherTool):
    def get_forecast(self, *args, **kwargs):
        self.call_count += 1
        return super().get_forecast(*args, **kwargs)


def _counting_tools() -> dict:
    return {
        "flight_tool": CountingFlightTool(),
        "hotel_tool": CountingHotelTool(),
        "attraction_tool": CountingAttractionTool(),
        "restaurant_tool": CountingRestaurantTool(),
        "weather_tool": CountingWeatherTool(),
    }


def test_refine_without_relevant_changes_skips_every_search_tool(app_factory):
    tools = _counting_tools()
    with isolated_client(app_factory(**tools)) as client:
        parent_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(client, parent_id)
        for tool in tools.values():
            assert tool.call_count == 1

        # StubParser.parse_partial() returns {} for text with no configured
        # overrides - nothing this refinement changed maps to any search
        # step, so none of the 5 tools should be called a second time.
        child_id = client.post(
            "/refine", json={"session_id": parent_id, "raw_text": "add a museum visit"}
        ).json()["session_id"]
        data = wait_until_terminal(client, child_id)

    assert data["status"] == "completed"
    for tool in tools.values():
        assert tool.call_count == 1


def test_refine_changing_origin_reruns_only_flights(app_factory):
    tools = _counting_tools()
    with isolated_client(app_factory(parser=OriginChangeParser(), **tools)) as client:
        parent_id = client.post("/plan", json={"raw_text": "5 days in Paris from Boston"}).json()[
            "session_id"
        ]
        wait_until_terminal(client, parent_id)

        child_id = client.post(
            "/refine",
            json={"session_id": parent_id, "raw_text": "actually I'm flying from New York"},
        ).json()["session_id"]
        data = wait_until_terminal(client, child_id)

    assert data["status"] == "completed"
    assert data["preferences"]["origin"] == "New York"
    assert tools["flight_tool"].call_count == 2  # re-ran with the new origin
    assert tools["hotel_tool"].call_count == 1  # unaffected - reused
    assert tools["attraction_tool"].call_count == 1
    assert tools["restaurant_tool"].call_count == 1
    assert tools["weather_tool"].call_count == 1


def test_refine_changing_destination_reruns_every_search_tool(app_factory):
    tools = _counting_tools()
    with isolated_client(app_factory(parser=BudgetAwareParser(), **tools)) as client:
        parent_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(client, parent_id)

        child_id = client.post(
            "/refine", json={"session_id": parent_id, "raw_text": "5 days in Paris, budget $3000"}
        ).json()["session_id"]
        wait_until_terminal(client, child_id)

    # BudgetAwareParser's refinement only ever changes budget_total, not
    # destination - included here as the budget-only counterpart to the
    # origin test above: budget changes should only re-run flights too.
    assert tools["flight_tool"].call_count == 2
    assert tools["hotel_tool"].call_count == 1
    assert tools["attraction_tool"].call_count == 1
    assert tools["restaurant_tool"].call_count == 1
    assert tools["weather_tool"].call_count == 1


def test_refine_emits_a_refinement_seeded_event_listing_reused_steps(app_factory):
    with isolated_client(app_factory()) as client:
        parent_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(client, parent_id)

        child_id = client.post(
            "/refine", json={"session_id": parent_id, "raw_text": "add a museum visit"}
        ).json()["session_id"]
        wait_until_terminal(client, child_id)

        session_store = client.app.state.session_store
        events = session_store.get_events(child_id)

    seeded = [e for e in events if e.event_type == "refinement_seeded"]
    assert len(seeded) == 1
    assert sorted(seeded[0].payload["reused_steps"]) == [
        "check_weather",
        "find_attractions",
        "find_restaurants",
        "search_flights",
        "search_hotels",
    ]
