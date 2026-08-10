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
    distinguish which."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc
    return payload["sub"]


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization.removeprefix("Bearer ").strip()
