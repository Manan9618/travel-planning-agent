from tests.api.conftest import isolated_client, wait_until_terminal
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
