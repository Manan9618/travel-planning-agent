from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tests.api.conftest import register_and_authenticate
from travel_agent.api.auth import create_access_token, create_oauth_state_token, decode_access_token
from travel_agent.tools.google_oauth import GoogleOAuthClient


class FakeGoogleOAuthClient(GoogleOAuthClient):
    """Same public interface as GoogleOAuthClient, no real network call —
    `exchange_code`/`fetch_userinfo` return whatever this test wired up
    instead of ever reaching Google."""

    def __init__(self, userinfo=None, exchange_error=None, userinfo_error=None):
        super().__init__(client_id="test-client-id", client_secret="test-client-secret")
        self._userinfo = userinfo or {"sub": "google-123", "email": "traveler@example.com"}
        self._exchange_error = exchange_error
        self._userinfo_error = userinfo_error
        self.exchange_code_calls: list[tuple[str, str]] = []

    def exchange_code(self, code: str, redirect_uri: str) -> str:
        self.exchange_code_calls.append((code, redirect_uri))
        if self._exchange_error:
            raise self._exchange_error
        return "fake-google-access-token"

    def fetch_userinfo(self, access_token: str) -> dict:
        if self._userinfo_error:
            raise self._userinfo_error
        return self._userinfo


def _app(app_factory, **kwargs):
    return app_factory(google_oauth=FakeGoogleOAuthClient(**kwargs))


def _unconfigured_app(app_factory):
    return app_factory(google_oauth=GoogleOAuthClient(client_id="", client_secret=""))


# --- /auth/google/login ------------------------------------------------------


def test_login_redirects_to_googles_consent_screen(app_factory):
    with TestClient(_app(app_factory)) as client:
        resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth")


def test_login_includes_a_state_param(app_factory):
    with TestClient(_app(app_factory)) as client:
        resp = client.get("/auth/google/login", follow_redirects=False)
    query = parse_qs(urlparse(resp.headers["location"]).query)
    assert "state" in query


def test_login_redirects_to_frontend_when_not_configured(app_factory):
    with TestClient(_unconfigured_app(app_factory)) as client:
        resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "oauth_error=not_configured" in resp.headers["location"]
    assert "accounts.google.com" not in resp.headers["location"]


def test_login_is_not_behind_the_api_key(app_factory, monkeypatch):
    from travel_agent.config import settings

    monkeypatch.setattr(settings, "api_key", "secret-deployment-key")
    with TestClient(_app(app_factory)) as client:
        resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307)  # not a 401


# --- /auth/google/callback: success paths ------------------------------------


def test_callback_creates_a_new_account_and_redirects_with_a_token(app_factory):
    with TestClient(_app(app_factory)) as client:
        state = create_oauth_state_token()
        resp = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "oauth_token=" in location
    token = parse_qs(urlparse(location).query)["oauth_token"][0]
    assert decode_access_token(token)  # a real, valid bearer token


def test_callback_new_account_is_actually_usable(app_factory):
    app = _app(app_factory)
    with TestClient(app) as client:
        state = create_oauth_state_token()
        resp = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        token = parse_qs(urlparse(resp.headers["location"]).query)["oauth_token"][0]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "traveler@example.com"


def test_callback_second_sign_in_reuses_the_same_account(app_factory):
    app = _app(app_factory)
    with TestClient(app) as client:
        state1 = create_oauth_state_token()
        resp1 = client.get(
            "/auth/google/callback",
            params={"code": "code-1", "state": state1},
            follow_redirects=False,
        )
        token1 = parse_qs(urlparse(resp1.headers["location"]).query)["oauth_token"][0]
        user_id1 = decode_access_token(token1)

        state2 = create_oauth_state_token()
        resp2 = client.get(
            "/auth/google/callback",
            params={"code": "code-2", "state": state2},
            follow_redirects=False,
        )
        token2 = parse_qs(urlparse(resp2.headers["location"]).query)["oauth_token"][0]
        user_id2 = decode_access_token(token2)
    assert user_id1 == user_id2


def test_callback_links_google_id_to_an_existing_password_account(app_factory):
    app = _app(app_factory, userinfo={"sub": "google-999", "email": "traveler@example.com"})
    with TestClient(app) as client:
        # A normal password account already exists with this email...
        register_and_authenticate(client, email="traveler@example.com", password="hunter2222")
        password_token = client.headers["Authorization"].removeprefix("Bearer ")
        password_user_id = decode_access_token(password_token)

        # ...then signs in with Google for the first time.
        state = create_oauth_state_token()
        resp = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        google_token = parse_qs(urlparse(resp.headers["location"]).query)["oauth_token"][0]
        google_user_id = decode_access_token(google_token)
    assert google_user_id == password_user_id  # linked, not duplicated


# --- /auth/google/callback: failure paths -------------------------------------


def test_callback_redirects_with_denied_when_google_reports_an_error(app_factory):
    with TestClient(_app(app_factory)) as client:
        resp = client.get(
            "/auth/google/callback", params={"error": "access_denied"}, follow_redirects=False
        )
    assert "oauth_error=denied" in resp.headers["location"]


def test_callback_redirects_with_invalid_request_when_code_is_missing(app_factory):
    with TestClient(_app(app_factory)) as client:
        state = create_oauth_state_token()
        resp = client.get("/auth/google/callback", params={"state": state}, follow_redirects=False)
    assert "oauth_error=invalid_request" in resp.headers["location"]


def test_callback_redirects_with_invalid_state_on_a_forged_state(app_factory):
    with TestClient(_app(app_factory)) as client:
        resp = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": "forged-not-a-real-token"},
            follow_redirects=False,
        )
    assert "oauth_error=invalid_state" in resp.headers["location"]


def test_callback_redirects_with_invalid_state_on_someone_elses_reset_token(app_factory):
    # A reset token is signed with the same secret and would otherwise
    # decode fine — the `purpose` claim is what stops it from being replayed
    # here too (mirrors auth.py's existing purpose-claim isolation tests).
    with TestClient(_app(app_factory)) as client:
        resp = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": create_access_token("someone")},
            follow_redirects=False,
        )
    assert "oauth_error=invalid_state" in resp.headers["location"]


def test_callback_redirects_with_exchange_failed_when_google_rejects_the_code(app_factory):
    import requests

    app = _app(app_factory, exchange_error=requests.HTTPError("400 invalid_grant"))
    with TestClient(app) as client:
        state = create_oauth_state_token()
        resp = client.get(
            "/auth/google/callback",
            params={"code": "bad-code", "state": state},
            follow_redirects=False,
        )
    assert "oauth_error=exchange_failed" in resp.headers["location"]


def test_callback_redirects_with_exchange_failed_when_userinfo_fails(app_factory):
    import requests

    app = _app(app_factory, userinfo_error=requests.HTTPError("401 invalid_token"))
    with TestClient(app) as client:
        state = create_oauth_state_token()
        resp = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
    assert "oauth_error=exchange_failed" in resp.headers["location"]


def test_callback_does_not_leak_a_state_token_from_a_different_purpose_as_valid(app_factory):
    from travel_agent.api.auth import create_reset_token

    with TestClient(_app(app_factory)) as client:
        resp = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": create_reset_token("someone")},
            follow_redirects=False,
        )
    assert "oauth_error=invalid_state" in resp.headers["location"]
