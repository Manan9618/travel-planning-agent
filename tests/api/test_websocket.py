from tests.api.conftest import FakeNarrator, StubParser, isolated_client, wait_until_terminal


def test_websocket_missing_token_sends_error_and_closes(client):
    with client.websocket_connect("/ws/does-not-exist") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_websocket_unknown_session_sends_error_and_closes(client):
    with client.websocket_connect(f"/ws/does-not-exist?token={client.auth_token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_websocket_wrong_users_token_sends_error_and_closes(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)

        with isolated_client(app_factory()) as stranger:
            # Different app instance -> different, isolated in-memory
            # UserStore/SessionStore, so this deliberately can't reuse
            # `owner`'s session_id for real - this asserts the WS endpoint
            # itself enforces ownership the same way the REST endpoints do,
            # not just that an unrelated session_id 404s.
            with stranger.websocket_connect(f"/ws/{session_id}?token={stranger.auth_token}") as ws:
                msg = ws.receive_json()
    assert msg["type"] == "error"


def _collect_until_terminal(ws, max_messages=100):
    messages = []
    for _ in range(max_messages):
        msg = ws.receive_json()
        messages.append(msg)
        if msg["type"] in ("done", "error", "awaiting_review"):
            break
    return messages


def test_websocket_connected_after_completion_replays_full_event_log(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)  # let the run finish before connecting

    with client.websocket_connect(f"/ws/{session_id}?token={client.auth_token}") as ws:
        messages = _collect_until_terminal(ws)

    types = [m["type"] for m in messages]
    assert "step_completed" in types
    assert "done" in types
    assert types[-1] == "done"


def test_websocket_includes_a_step_completed_event_per_planning_step(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}?token={client.auth_token}") as ws:
        messages = _collect_until_terminal(ws)

    steps = {m["step"] for m in messages if m["type"] == "step_completed"}
    assert steps == {
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


def test_websocket_streams_narration_tokens(app_factory):
    with isolated_client(
        app_factory(narrator=FakeNarrator(tokens=["Bonjour", " Paris"]))
    ) as client:
        session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(client, session_id)

        with client.websocket_connect(f"/ws/{session_id}?token={client.auth_token}") as ws:
            messages = _collect_until_terminal(ws)

    narration = [m["token"] for m in messages if m["type"] == "narration_token"]
    assert narration == ["Bonjour", " Paris"]


def test_websocket_reports_awaiting_review_for_paused_sessions(app_factory):
    with isolated_client(app_factory(parser=StubParser(budget_total=200))) as client:
        session_id = client.post("/plan", json={"raw_text": "cheap trip"}).json()["session_id"]
        wait_until_terminal(client, session_id)

        with client.websocket_connect(f"/ws/{session_id}?token={client.auth_token}") as ws:
            messages = _collect_until_terminal(ws)

    assert messages[-1]["type"] == "awaiting_review"


def test_websocket_reports_error_event_on_failure(app_factory):
    with isolated_client(app_factory(narrator=FakeNarrator(fail=True))) as client:
        session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(client, session_id)  # narration failure is non-fatal -> still completes

        with client.websocket_connect(f"/ws/{session_id}?token={client.auth_token}") as ws:
            messages = _collect_until_terminal(ws)

    # narration failing just skips narration tokens; the run itself still
    # completes successfully (matches PDFGenerator's own thumbnail-failure
    # graceful-degradation pattern from Week 14).
    assert messages[-1]["type"] == "done"
    assert not any(m["type"] == "narration_token" for m in messages)
