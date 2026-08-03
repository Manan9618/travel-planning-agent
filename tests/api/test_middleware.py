import pytest

from tests.api.conftest import isolated_client, wait_until_terminal
from travel_agent.config import settings


@pytest.fixture(autouse=True)
def _restore_api_key():
    original = settings.api_key
    yield
    settings.api_key = original


# --- API key validation ---------------------------------------------------


def test_no_api_key_configured_allows_requests_without_a_header(app_factory):
    settings.api_key = ""
    with isolated_client(app_factory()) as client:
        resp = client.post("/plan", json={"raw_text": "trip"})
    assert resp.status_code == 202


def test_api_key_configured_rejects_requests_with_no_header(app_factory):
    settings.api_key = "secret123"
    with isolated_client(app_factory()) as client:
        resp = client.post("/plan", json={"raw_text": "trip"})
    assert resp.status_code == 401


def test_api_key_configured_rejects_wrong_key(app_factory):
    settings.api_key = "secret123"
    with isolated_client(app_factory()) as client:
        resp = client.post("/plan", json={"raw_text": "trip"}, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_api_key_configured_accepts_correct_key(app_factory):
    settings.api_key = "secret123"
    with isolated_client(app_factory()) as client:
        resp = client.post("/plan", json={"raw_text": "trip"}, headers={"X-API-Key": "secret123"})
    assert resp.status_code == 202


def test_api_key_enforced_on_get_plan_too(app_factory):
    settings.api_key = ""
    with isolated_client(app_factory()) as client:
        session_id = client.post("/plan", json={"raw_text": "trip"}).json()["session_id"]
        wait_until_terminal(client, session_id)

    settings.api_key = "secret123"
    with isolated_client(app_factory()) as client2:
        resp = client2.get(f"/plan/{session_id}")
    assert resp.status_code == 401


# --- rate limiting -------------------------------------------------------


def test_plan_endpoint_is_rate_limited_after_ten_requests_per_minute(client):
    statuses = [client.post("/plan", json={"raw_text": f"trip {i}"}).status_code for i in range(12)]
    assert statuses[:10] == [202] * 10
    assert statuses[10:] == [429, 429]


def test_refine_endpoint_is_rate_limited_after_ten_requests_per_minute(client):
    session_id = client.post("/plan", json={"raw_text": "trip"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    statuses = [
        client.post(
            "/refine", json={"session_id": session_id, "raw_text": f"refine {i}"}
        ).status_code
        for i in range(12)
    ]
    assert statuses[:10] == [202] * 10
    assert statuses[10:] == [429, 429]


def test_get_plan_polling_is_not_rate_limited(client):
    session_id = client.post("/plan", json={"raw_text": "trip"}).json()["session_id"]
    statuses = [client.get(f"/plan/{session_id}").status_code for _ in range(20)]
    assert all(s == 200 for s in statuses)


# --- CORS (Week 16 frontend) ------------------------------------------------


def test_allowed_origin_gets_cors_header(client):
    resp = client.options(
        "/plan",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_disallowed_origin_gets_no_cors_header(client):
    resp = client.options(
        "/plan",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in resp.headers
