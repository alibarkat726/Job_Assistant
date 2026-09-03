import pytest
from app.shared.security.hashing import hash_password, verify_password
from app.shared.security.jwt import (
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_opaque_token,
)


def test_password_hashing():
    raw = "SecurePassword123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_jwt_access_token():
    user_id_str = "12345678-1234-5678-1234-567812345678"
    token = create_access_token(subject=user_id_str)
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == user_id_str
    assert decoded["type"] == "access"


def test_opaque_token_hashing():
    raw_token = generate_opaque_token()
    token_hash1 = hash_opaque_token(raw_token)
    token_hash2 = hash_opaque_token(raw_token)
    assert len(raw_token) > 30
    assert token_hash1 == token_hash2
    assert token_hash1 != raw_token


@pytest.mark.asyncio
async def test_security_headers_and_csp(async_client):
    # Standard endpoint response headers
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "script-src 'self';" in response.headers["Content-Security-Policy"]

    # Docs endpoint response headers allowing CDN assets
    docs_response = await async_client.get("/docs")
    assert docs_response.status_code == 200
    csp = docs_response.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "'unsafe-inline'" in csp

