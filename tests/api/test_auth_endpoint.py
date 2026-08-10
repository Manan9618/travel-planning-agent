from tests.api.conftest import isolated_client, wait_until_terminal


def test_register_returns_a_token_and_the_new_user(client):
    resp = client.post(
        "/auth/register", json={"email": "new@example.com", "password": "hunter2222"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["email"] == "new@example.com"
    assert body["access_token"]


def test_register_lowercases_the_email(client):
    resp = client.post(
        "/auth/register", json={"email": "New@Example.COM", "password": "hunter2222"}
    )
    assert resp.json()["email"] == "new@example.com"


def test_register_rejects_duplicate_email(client):
    client.post("/auth/register", json={"email": "dup@example.com", "password": "hunter2222"})
    resp = client.post(
        "/auth/register", json={"email": "dup@example.com", "password": "hunter2222"}
    )
    assert resp.status_code == 409


def test_register_rejects_invalid_email(client):
    resp = client.post("/auth/register", json={"email": "not-an-email", "password": "hunter2222"})
    assert resp.status_code == 422


def test_register_rejects_short_password(client):
    resp = client.post("/auth/register", json={"email": "short@example.com", "password": "short"})
    assert resp.status_code == 422


def test_login_with_correct_credentials_returns_a_token(client):
    client.post("/auth/register", json={"email": "login@example.com", "password": "hunter2222"})
    resp = client.post("/auth/login", json={"email": "login@example.com", "password": "hunter2222"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_with_wrong_password_is_rejected(client):
    client.post("/auth/register", json={"email": "login2@example.com", "password": "hunter2222"})
    resp = client.post("/auth/login", json={"email": "login2@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_with_unknown_email_is_rejected(client):
    resp = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "hunter2222"}
    )
    assert resp.status_code == 401


def test_me_returns_the_authenticated_user(client):
    resp = client.get("/auth/me")  # `client` fixture already sends its own token
    assert resp.status_code == 200
    assert resp.json()["email"] == "traveler@example.com"


def test_me_without_a_token_is_rejected(app_factory):
    with isolated_client(app_factory()) as authed:
        authed.headers.pop("Authorization")
        resp = authed.get("/auth/me")
    assert resp.status_code == 401


def test_me_with_a_garbage_token_is_rejected(app_factory):
    with isolated_client(app_factory()) as authed:
        authed.headers["Authorization"] = "Bearer not-a-real-token"
        resp = authed.get("/auth/me")
    assert resp.status_code == 401


# --- session ownership is actually enforced, not just recorded ------------


def test_plan_without_a_token_is_rejected(app_factory):
    with isolated_client(app_factory()) as authed:
        authed.headers.pop("Authorization")
        resp = authed.post("/plan", json={"raw_text": "5 days in Paris"})
    assert resp.status_code == 401


def test_a_session_belongs_to_the_user_who_created_it(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    resp = client.get(f"/plan/{session_id}")
    assert resp.status_code == 200


def test_another_user_cannot_read_someone_elses_session(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)

    with isolated_client(app_factory()) as stranger:
        resp = stranger.get(f"/plan/{session_id}")
    assert resp.status_code == 404


def test_another_user_cannot_refine_someone_elses_session(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)

    with isolated_client(app_factory()) as stranger:
        resp = stranger.post(
            "/refine", json={"session_id": session_id, "raw_text": "make it shorter"}
        )
    assert resp.status_code == 404


def test_another_user_cannot_resume_someone_elses_session(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)

    with isolated_client(app_factory()) as stranger:
        resp = stranger.post(f"/plan/{session_id}/resume", json={"approved": True})
    assert resp.status_code == 404


def test_another_user_cannot_export_someone_elses_pdf(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)

    with isolated_client(app_factory()) as stranger:
        resp = stranger.get(f"/export/{session_id}/pdf")
    assert resp.status_code == 404


def test_another_user_cannot_export_someone_elses_map(app_factory):
    with isolated_client(app_factory()) as owner:
        session_id = owner.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
        wait_until_terminal(owner, session_id)

    with isolated_client(app_factory()) as stranger:
        resp = stranger.get(f"/export/{session_id}/map")
    assert resp.status_code == 404


def test_refine_creates_the_new_session_under_the_same_user(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    child_id = client.post(
        "/refine", json={"session_id": session_id, "raw_text": "add a museum"}
    ).json()["session_id"]
    # If /refine hadn't stamped the new session with the current user's
    # id, this would 404 exactly like the cross-user tests above.
    resp = client.get(f"/plan/{child_id}")
    assert resp.status_code == 200


# --- GET /sessions (trip history) ------------------------------------------


def test_sessions_without_a_token_is_rejected(app_factory):
    with isolated_client(app_factory()) as authed:
        authed.headers.pop("Authorization")
        resp = authed.get("/sessions")
    assert resp.status_code == 401


def test_sessions_lists_a_trip_the_user_started(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    resp = client.get("/sessions")
    assert resp.status_code == 200
    ids = [s["session_id"] for s in resp.json()["sessions"]]
    assert session_id in ids


def test_sessions_is_empty_for_a_brand_new_user(app_factory):
    with isolated_client(app_factory()) as authed:
        resp = authed.get("/sessions")
    assert resp.json()["sessions"] == []


def test_sessions_never_shows_another_users_trips(app_factory):
    with isolated_client(app_factory()) as owner:
        owner.post("/plan", json={"raw_text": "5 days in Paris"})

    with isolated_client(app_factory()) as stranger:
        resp = stranger.get("/sessions")
    assert resp.json()["sessions"] == []


def test_sessions_excludes_refinement_follow_ups(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)
    client.post("/refine", json={"session_id": session_id, "raw_text": "add a museum"})

    resp = client.get("/sessions")
    ids = [s["session_id"] for s in resp.json()["sessions"]]
    assert ids == [session_id]


def test_sessions_are_ordered_most_recent_first(client):
    first = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    second = client.post("/plan", json={"raw_text": "3 days in Rome"}).json()["session_id"]
    resp = client.get("/sessions")
    ids = [s["session_id"] for s in resp.json()["sessions"]]
    assert ids.index(second) < ids.index(first)
