"""JWT-based user authentication.

Real user accounts: email/password signup+login, bcrypt-hashed passwords
(never stored or logged in plaintext), a signed JWT bearer token issued on
register/login and required thereafter on every session-scoped endpoint.

Deliberately separate from `verify_api_key` (Week 15's optional,
deployment-wide shared secret in `api/app.py`) — both can be active at
once: `API_KEY`, if set, gates the whole API from arbitrary internet
access before a request is even considered; this module identifies WHICH
user is making an already-let-through request, and scopes their sessions
to them.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException

from travel_agent.config import settings

JWT_ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 8

# Deliberately simple (not a full RFC 5322 parser) - good enough to catch
# "forgot the @" typos without rejecting real addresses a stricter regex
# might choke on (+ tags, subdomains, etc.).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash (shouldn't happen for a hash this module itself
        # produced) - fail closed, not open.
        return False


def create_access_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user_id (the token's `sub` claim). Raises 401 on any
    invalid, malformed, or expired token - callers never need to
    distinguish which. Also rejects a reset token presented as a bearer
    token — real access tokens never carry a `purpose` claim, a reset
    token always does (see `create_reset_token`) — so a leaked, still-valid
    reset link can't double as a way into the account within its short
    window."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc
    if "purpose" in payload:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return payload["sub"]


_RESET_TOKEN_PURPOSE = "password_reset"


def create_reset_token(user_id: str) -> str:
    """A short-lived JWT distinct from an access token — a `purpose` claim
    stops a leaked/expired access token from doubling as a password reset
    (and vice versa), the two are only allowed to do the one thing they
    were issued for."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "purpose": _RESET_TOKEN_PURPOSE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.password_reset_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_reset_token(token: str) -> str:
    """Returns the user_id a reset token was issued for. Raises 400 (not
    401 — this isn't an auth-bearer-token failure, it's a bad reset link)
    on any invalid, malformed, expired, or wrong-purpose token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="invalid or expired reset link") from exc
    if payload.get("purpose") != _RESET_TOKEN_PURPOSE:
        raise HTTPException(status_code=400, detail="invalid or expired reset link")
    return payload["sub"]


_OAUTH_STATE_PURPOSE = "oauth_state"
_OAUTH_STATE_EXPIRE_MINUTES = 5


def create_oauth_state_token() -> str:
    """The CSRF-protection `state` param for the Google sign-in redirect.
    No server-side session exists yet at this point in the flow (the user
    isn't authenticated), so rather than standing up a session store just
    for this, `state` is itself a short-lived, signed JWT — Google echoes
    it back verbatim on the callback, and a signature we can verify with
    our own secret is unforgeable by anyone who doesn't have it, exactly
    the same trick `create_reset_token` uses for a different purpose."""
    now = datetime.now(UTC)
    payload = {
        "purpose": _OAUTH_STATE_PURPOSE,
        "nonce": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(minutes=_OAUTH_STATE_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_oauth_state_token(token: str) -> None:
    """Raises HTTPException(400) if `token` isn't a valid, unexpired state
    token this backend itself issued moments earlier."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="invalid or expired oauth state") from exc
    if payload.get("purpose") != _OAUTH_STATE_PURPOSE:
        raise HTTPException(status_code=400, detail="invalid or expired oauth state")


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization.removeprefix("Bearer ").strip()
