from tests.api.conftest import FailingParser, StubParser, isolated_client, wait_until_terminal

# --- POST /plan ---------------------------------------------------------


def test_post_plan_returns_202_with_session_id_and_running_status(client):
    resp = client.post("/plan", json={"raw_text": "5 days in Paris"})
    assert resp.status_code == 202
    body = resp.json()
    assert "session_id" in body
    assert body["status"] == "running"


def test_post_plan_rejects_empty_raw_text(client):
    resp = client.post("/plan", json={"raw_text": ""})
    assert resp.status_code == 422


def test_post_plan_rejects_missing_raw_text(client):
    resp = client.post("/plan", json={})
    assert resp.status_code == 422


def test_each_plan_call_gets_a_distinct_session_id(client):
    a = client.post("/plan", json={"raw_text": "trip a"}).json()["session_id"]
    b = client.post("/plan", json={"raw_text": "trip b"}).json()["session_id"]
    assert a != b


# --- GET /plan/{session_id} — happy path ---------------------------------


def test_plan_runs_to_completion_and_produces_full_itinerary(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    data = wait_until_terminal(client, session_id)

    assert data["status"] == "completed"
    assert data["errors"] == []
    assert data["itinerary"] is not None
    assert len(data["itinerary"]["days"]) == 3  # 2026-09-01 to 2026-09-03
    assert data["budget_evaluation"] is not None
    assert data["pdf_path"] is not None
    assert data["map_html_available"] is True
    assert isinstance(data["conflict_log"], list)
    assert set(data["completed_steps"]) == {
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
    }


def test_get_plan_for_unknown_session_returns_404(client):
    resp = client.get("/plan/does-not-exist")
    assert resp.status_code == 404


def test_get_plan_reflects_running_status_before_completion(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    data = client.get(f"/plan/{session_id}").json()
    assert data["status"] in ("running", "completed")  # may finish very fast on a stub graph


def test_completed_session_exposes_preferences_parsed_from_raw_text(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    data = wait_until_terminal(client, session_id)
    assert data["preferences"]["destination"] == "Paris"


# --- error propagation ----------------------------------------------------


def test_parser_failure_is_recorded_but_the_run_still_completes(app_factory):
    # A parse failure is caught inside the node itself (Week 4 design: one
    # tool failing doesn't halt the graph), so preferences stay None,
    # determine_valid_steps routes straight to DONE, and the session reaches
    # "completed" with the failure visible only in `errors` — not "failed".

    with isolated_client(app_factory(parser=FailingParser())) as client:
        session_id = client.post("/plan", json={"raw_text": "trip"}).json()["session_id"]
        data = wait_until_terminal(client, session_id)
    assert data["status"] == "completed"
    assert any("parser boom" in e for e in data["errors"])
    assert data["itinerary"] is None


# --- human-in-the-loop pause ----------------------------------------------


def test_unresolvable_budget_pauses_with_awaiting_review_status(app_factory):

    low_budget_parser = StubParser(budget_total=200)
    with isolated_client(app_factory(parser=low_budget_parser)) as client:
        session_id = client.post("/plan", json={"raw_text": "cheap trip"}).json()["session_id"]
        data = wait_until_terminal(client, session_id)

    assert data["status"] == "awaiting_review"
    assert "human_review" not in data["completed_steps"]
    assert "generate_pdf" in data["completed_steps"]  # runs before human_review
    # ConflictResolver logs every attempt, successful or not (Week 6), so an
    # unresolvable budget overrun still leaves a trail of what it tried.
    assert len(data["conflict_log"]) > 0
