from tests.api.conftest import FailingParser, isolated_client, wait_until_terminal


def _shared_token(share_url: str) -> str:
    return share_url.rsplit("shared=", 1)[1]


# --- creating a share link ---------------------------------------------------


def test_create_share_link_without_a_token_is_rejected(app_factory):
    with isolated_client(app_factory()) as authed:
        session_id = authed.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        authed.headers.pop("Authorization")
        resp = authed.post(f"/plan/{session_id}/share")
    assert resp.status_code == 401


def test_another_user_cannot_share_someone_elses_trip(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)

    with isolated_client(app_factory()) as stranger:
        resp = stranger.post(f"/plan/{session_id}/share")
    assert resp.status_code == 404


def test_sharing_before_the_itinerary_exists_is_rejected(app_factory):
    # A plain just-started session risks a race on a fast stub graph (it
    # may complete before the assertion runs) - FailingParser guarantees
    # parse_preferences fails, preferences stays None, and the graph routes
    # straight to DONE without ever building an itinerary, deterministically
    # (see test_plan_endpoint.py's own use of this same pattern).
    with isolated_client(app_factory(parser=FailingParser())) as authed:
        session_id = authed.post("/plan", json={"raw_text": "trip"}).json()["session_id"]
        wait_until_terminal(authed, session_id)
        resp = authed.post(f"/plan/{session_id}/share")
    assert resp.status_code == 400


def test_create_share_link_returns_a_url_with_a_token(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    resp = client.post(f"/plan/{session_id}/share")
    assert resp.status_code == 200
    assert "shared=" in resp.json()["share_url"]


def test_create_share_link_is_idempotent(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    first = client.post(f"/plan/{session_id}/share").json()["share_url"]
    second = client.post(f"/plan/{session_id}/share").json()["share_url"]
    assert first == second


# --- viewing a shared trip ----------------------------------------------------


def test_shared_trip_is_viewable_without_any_auth(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)
        token = _shared_token(owner.post(f"/plan/{session_id}/share").json()["share_url"])

        owner.headers.pop("Authorization")
        resp = owner.get(f"/shared/{token}")
    assert resp.status_code == 200
    assert resp.json()["itinerary"] is not None


def test_shared_trip_response_has_no_session_internals(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)
    token = _shared_token(client.post(f"/plan/{session_id}/share").json()["share_url"])

    body = client.get(f"/shared/{token}").json()
    assert set(body.keys()) == {"itinerary", "budget_evaluation", "pdf_available", "map_available"}


def test_unknown_share_token_returns_404(client):
    resp = client.get("/shared/not-a-real-token")
    assert resp.status_code == 404


def test_shared_pdf_is_downloadable_without_auth(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)
        token = _shared_token(owner.post(f"/plan/{session_id}/share").json()["share_url"])

        owner.headers.pop("Authorization")
        resp = owner.get(f"/shared/{token}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_shared_map_is_viewable_without_auth(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)
        token = _shared_token(owner.post(f"/plan/{session_id}/share").json()["share_url"])

        owner.headers.pop("Authorization")
        resp = owner.get(f"/shared/{token}/map")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_shared_pdf_for_unknown_token_is_404(client):
    resp = client.get("/shared/not-a-real-token/pdf")
    assert resp.status_code == 404


def test_shared_map_for_unknown_token_is_404(client):
    resp = client.get("/shared/not-a-real-token/map")
    assert resp.status_code == 404


# --- revoking a share link ----------------------------------------------------


def test_revoke_share_link_without_a_token_is_rejected(app_factory):
    with isolated_client(app_factory()) as authed:
        session_id = authed.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        authed.headers.pop("Authorization")
        resp = authed.delete(f"/plan/{session_id}/share")
    assert resp.status_code == 401


def test_another_user_cannot_revoke_someone_elses_share_link(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)
        owner.post(f"/plan/{session_id}/share")

    with isolated_client(app_factory()) as stranger:
        resp = stranger.delete(f"/plan/{session_id}/share")
    assert resp.status_code == 404


def test_revoke_share_link_disables_the_link(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)
    token = _shared_token(client.post(f"/plan/{session_id}/share").json()["share_url"])

    revoke_resp = client.delete(f"/plan/{session_id}/share")
    assert revoke_resp.status_code == 204

    resp = client.get(f"/shared/{token}")
    assert resp.status_code == 404


def test_revoke_share_link_when_never_shared_is_a_no_op(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)
    resp = client.delete(f"/plan/{session_id}/share")
    assert resp.status_code == 204


def test_reshare_after_revoke_gets_a_new_token(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    first_token = _shared_token(client.post(f"/plan/{session_id}/share").json()["share_url"])
    client.delete(f"/plan/{session_id}/share")
    second_token = _shared_token(client.post(f"/plan/{session_id}/share").json()["share_url"])

    assert first_token != second_token
