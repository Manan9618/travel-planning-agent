import pytest
from fastapi import HTTPException

from travel_agent.api.auth import (
    create_access_token,
    create_reset_token,
    decode_access_token,
    decode_reset_token,
    extract_bearer_token,
    hash_password,
    is_valid_email,
    verify_password,
)

# --- email validation -------------------------------------------------


@pytest.mark.parametrize("email", ["traveler@example.com", "a.b+tag@sub.example.co.uk", "x@y.io"])
def test_is_valid_email_accepts_real_looking_addresses(email):
    assert is_valid_email(email)


@pytest.mark.parametrize("email", ["not-an-email", "missing-domain@", "@no-local-part.com", ""])
def test_is_valid_email_rejects_malformed_addresses(email):
    assert not is_valid_email(email)


# --- password hashing ---------------------------------------------------


def test_hash_password_does_not_store_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in hashed


def test_hash_password_produces_a_verifiable_hash():
    hashed = hash_password("hunter2222")
    assert verify_password("hunter2222", hashed)


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("hunter2222")
    assert not verify_password("wrong-password", hashed)


def test_hash_password_is_salted_differently_each_time():
    # Same input, two calls -> different hashes (bcrypt's own random salt) -
    # both must still verify against the original password.
    first = hash_password("hunter2222")
    second = hash_password("hunter2222")
    assert first != second
    assert verify_password("hunter2222", first)
    assert verify_password("hunter2222", second)


def test_verify_password_returns_false_not_raises_on_malformed_hash():
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


# --- JWT issuance/verification ------------------------------------------


def test_create_and_decode_access_token_roundtrips_the_user_id():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_decode_access_token_rejects_garbage():
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-real-token")
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_a_token_signed_with_a_different_secret(monkeypatch):
    from travel_agent.config import settings

    token = create_access_token("user-123")
    monkeypatch.setattr(settings, "jwt_secret", "a-completely-different-secret-value")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_an_expired_token(monkeypatch):
    from travel_agent.config import settings

    monkeypatch.setattr(
        settings, "jwt_expire_minutes", -1
    )  # already expired the instant it's issued
    token = create_access_token("user-123")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


# --- password reset tokens -------------------------------------------------


def test_create_and_decode_reset_token_roundtrips_the_user_id():
    token = create_reset_token("user-123")
    assert decode_reset_token(token) == "user-123"


def test_decode_reset_token_rejects_garbage():
    with pytest.raises(HTTPException) as exc_info:
        decode_reset_token("not-a-real-token")
    assert exc_info.value.status_code == 400


def test_decode_reset_token_rejects_an_expired_token(monkeypatch):
    from travel_agent.config import settings

    monkeypatch.setattr(settings, "password_reset_expire_minutes", -1)
    token = create_reset_token("user-123")
    with pytest.raises(HTTPException) as exc_info:
        decode_reset_token(token)
    assert exc_info.value.status_code == 400


def test_decode_reset_token_rejects_a_real_access_token():
    # An access token is signed with the same secret and would otherwise
    # decode fine — the `purpose` claim is what stops it from also being
    # usable as a password reset link.
    token = create_access_token("user-123")
    with pytest.raises(HTTPException) as exc_info:
        decode_reset_token(token)
    assert exc_info.value.status_code == 400


def test_decode_access_token_rejects_a_real_reset_token():
    token = create_reset_token("user-123")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


# --- bearer token extraction ---------------------------------------------


def test_extract_bearer_token_strips_the_prefix():
    assert extract_bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"


@pytest.mark.parametrize("header", [None, "", "abc.def.ghi", "Basic abc.def.ghi", "Bearer"])
def test_extract_bearer_token_rejects_missing_or_malformed_headers(header):
    with pytest.raises(HTTPException) as exc_info:
        extract_bearer_token(header)
    assert exc_info.value.status_code == 401
