"""GoogleOAuthClient — the two real network calls behind "Continue with
Google" (`api/app.py`'s `/auth/google/login` + `/callback`), split out into
its own injectable collaborator for the same reason `EmailSender` and
`CurrencyConverter` are: `create_app()` can swap in a fake for tests
without either endpoint making a real network call, and every credential
here is optional — `configured` is False (and the login endpoint degrades
to a friendly redirect instead of erroring) whenever `GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET` aren't set, the same graceful-degradation pattern
every other optional integration in this project already uses.

`authorize_url` needs no network call — it just builds the URL Google's own
consent screen lives at. `exchange_code` trades the one-time `code` Google
redirected back with for an access token; `fetch_userinfo` uses that token
to get the signed-in Google account's id/email — that `sub` claim is what
this app treats as the durable "Google identity" (`users.google_id`), not
the email alone, since a Google account's email is mutable but its `sub` is
not.
"""

from __future__ import annotations

from urllib.parse import urlencode

import requests

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
OAUTH_TIMEOUT = 10


class GoogleOAuthClient:
    def __init__(self, client_id: str = "", client_secret: str = "") -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            # Re-shows the consent screen every time rather than silently
            # re-approving — simpler to reason about than Google's default
            # "skip consent if already granted" for a demo/capstone project,
            # and costs the user one extra click at most.
            "prompt": "select_account",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> str:
        """Returns a Google access token for the code Google's callback
        redirect just handed us. Raises requests.RequestException (a bad/
        expired/already-used code, network failure, etc.) — the caller
        (the /auth/google/callback endpoint) turns that into a friendly
        redirect back to the frontend rather than a raw 500."""
        resp = requests.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=OAUTH_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def fetch_userinfo(self, access_token: str) -> dict:
        """Returns Google's userinfo payload — at minimum `sub` (the
        durable Google account id) and `email`. Raises requests.
        RequestException on failure, same reasoning as `exchange_code`."""
        resp = requests.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=OAUTH_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
