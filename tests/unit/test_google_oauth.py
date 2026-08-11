import pytest
import responses
from requests.exceptions import HTTPError

from travel_agent.tools.google_oauth import (
    AUTHORIZE_URL,
    TOKEN_URL,
    USERINFO_URL,
    GoogleOAuthClient,
)


def _client(**overrides):
    defaults = dict(client_id="test-client-id", client_secret="test-client-secret")
    defaults.update(overrides)
    return GoogleOAuthClient(**defaults)


# --- configured ------------------------------------------------------------


def test_configured_is_true_with_both_credentials():
    assert _client().configured is True


@pytest.mark.parametrize(
    "client_id,client_secret", [("", ""), ("id-only", ""), ("", "secret-only")]
)
def test_configured_is_false_without_both_credentials(client_id, client_secret):
    assert GoogleOAuthClient(client_id=client_id, client_secret=client_secret).configured is False


# --- authorize_url (no network call) ----------------------------------------


def test_authorize_url_points_at_google():
    url = _client().authorize_url("http://localhost:8000/auth/google/callback", "state-123")
    assert url.startswith(AUTHORIZE_URL)


def test_authorize_url_includes_client_id_redirect_uri_and_state():
    url = _client().authorize_url("http://localhost:8000/auth/google/callback", "state-123")
    assert "client_id=test-client-id" in url
    assert "state=state-123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fgoogle%2Fcallback" in url


def test_authorize_url_requests_openid_email_profile_scope():
    url = _client().authorize_url("http://localhost:8000/auth/google/callback", "state-123")
    assert "scope=openid+email+profile" in url


# --- exchange_code -----------------------------------------------------------


@responses.activate
def test_exchange_code_returns_the_access_token():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "real-access-token"}, status=200)
    token = _client().exchange_code("auth-code", "http://localhost:8000/auth/google/callback")
    assert token == "real-access-token"


@responses.activate
def test_exchange_code_sends_client_credentials_and_the_code():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "x"}, status=200)
    _client().exchange_code("auth-code", "http://localhost:8000/auth/google/callback")
    sent = responses.calls[0].request.body
    assert "code=auth-code" in sent
    assert "client_id=test-client-id" in sent
    assert "client_secret=test-client-secret" in sent
    assert "grant_type=authorization_code" in sent


@responses.activate
def test_exchange_code_raises_on_a_rejected_code():
    responses.add(responses.POST, TOKEN_URL, json={"error": "invalid_grant"}, status=400)
    with pytest.raises(HTTPError):
        _client().exchange_code("bad-code", "http://localhost:8000/auth/google/callback")


# --- fetch_userinfo -----------------------------------------------------------


@responses.activate
def test_fetch_userinfo_returns_the_parsed_payload():
    responses.add(
        responses.GET,
        USERINFO_URL,
        json={"sub": "google-user-123", "email": "traveler@example.com"},
        status=200,
    )
    info = _client().fetch_userinfo("real-access-token")
    assert info["sub"] == "google-user-123"
    assert info["email"] == "traveler@example.com"


@responses.activate
def test_fetch_userinfo_sends_the_access_token_as_a_bearer_header():
    responses.add(
        responses.GET, USERINFO_URL, json={"sub": "x", "email": "x@example.com"}, status=200
    )
    _client().fetch_userinfo("real-access-token")
    assert responses.calls[0].request.headers["Authorization"] == "Bearer real-access-token"


@responses.activate
def test_fetch_userinfo_raises_on_an_invalid_token():
    responses.add(responses.GET, USERINFO_URL, json={"error": "invalid_token"}, status=401)
    with pytest.raises(HTTPError):
        _client().fetch_userinfo("bad-token")
