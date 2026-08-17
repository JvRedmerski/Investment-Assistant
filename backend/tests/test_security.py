from datetime import timedelta

from app.core import security


def test_password_hash_and_verify_roundtrip():
    hashed = security.get_password_hash("StrongPassword123")
    assert hashed != "StrongPassword123"
    assert security.verify_password("StrongPassword123", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = security.get_password_hash("StrongPassword123")
    assert security.verify_password("WrongPassword", hashed) is False


def test_verify_password_handles_malformed_hash():
    # A malformed/invalid hash must fail safely instead of raising.
    assert security.verify_password("whatever", "not-a-valid-bcrypt-hash") is False


def test_create_and_decode_access_token_roundtrip():
    token = security.create_access_token({"sub": "42"})
    payload = security.decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert "exp" in payload
    assert "iat" in payload


def test_decode_access_token_rejects_garbage_token():
    assert security.decode_access_token("not-a-real-token") is None


def test_decode_access_token_rejects_expired_token():
    token = security.create_access_token(
        {"sub": "1"}, expires_delta=timedelta(seconds=-1)
    )
    assert security.decode_access_token(token) is None


def test_decode_access_token_rejects_tampered_signature():
    token = security.create_access_token({"sub": "1"})
    header, payload, signature = token.split(".")
    # Mutate the *first* character of the signature, not the last: base64url
    # can leave "don't care" padding bits in the final character for some
    # byte-length remainders, so flipping only the last character is not
    # guaranteed to change the decoded signature bytes (flaky test).
    mutated_char = "a" if signature[0] != "a" else "b"
    tampered = f"{header}.{payload}.{mutated_char}{signature[1:]}"
    assert security.decode_access_token(tampered) is None
