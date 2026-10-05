import secrets
import hashlib
from app.core.config import settings

def hash_api_key(plain_key: str) -> str:
    """Hash the API key using SHA-256 salted with SECRET_KEY."""
    salted = f"{settings.SECRET_KEY}:{plain_key}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()

def generate_api_key(prefix: str = "sc_live_") -> tuple[str, str]:
    """
    Generate a secure random API key.
    Returns:
        (plain_key, key_hash)
    """
    random_part = secrets.token_urlsafe(32)
    plain_key = f"{prefix}{random_part}"
    key_hash = hash_api_key(plain_key)
    return plain_key, key_hash

def verify_api_key_hash(plain_key: str, stored_hash: str) -> bool:
    """Verify that a plaintext API key matches a stored hash."""
    return secrets.compare_digest(hash_api_key(plain_key), stored_hash)
