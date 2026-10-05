import pytest
from app.core.security import generate_api_key, hash_api_key, verify_api_key_hash

def test_api_key_generation():
    plain, key_hash = generate_api_key()
    assert plain.startswith("sc_live_")
    assert len(plain) > 30
    assert len(key_hash) == 64  # SHA-256 hex length
    assert verify_api_key_hash(plain, key_hash) is True

def test_api_key_verification_fails_for_invalid():
    plain, key_hash = generate_api_key()
    assert verify_api_key_hash("invalid_key", key_hash) is False
    assert verify_api_key_hash(plain + "x", key_hash) is False
