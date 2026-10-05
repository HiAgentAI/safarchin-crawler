import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Local persistent backup file so tokens survive Redis restarts without DB migrations
TOKENS_FILE = Path(__file__).parent.parent / "data" / "provider_tokens.json"

def _ensure_data_dir():
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TOKENS_FILE.exists():
        TOKENS_FILE.write_text("{}", encoding="utf-8")

def _read_local_storage() -> Dict[str, Any]:
    _ensure_data_dir()
    try:
        content = TOKENS_FILE.read_text(encoding="utf-8")
        data = json.loads(content) if content.strip() else {}
        # Normalize old single-token format to pool format if needed
        for p_name, p_data in list(data.items()):
            if "tokens" not in p_data and "token" in p_data:
                data[p_name] = {
                    "provider": p_name,
                    "active_index": 0,
                    "tokens": [
                        {
                            "id": "tok_1",
                            "token": p_data["token"],
                            "token_type": p_data.get("token_type", "Bearer"),
                            "expires_at": p_data.get("expires_at"),
                            "cooldown_until": None,
                            "added_at": p_data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                    "updated_at": p_data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                }
        return data
    except Exception as e:
        logger.warning(f"Failed to read local tokens file: {e}")
        return {}

def _write_local_storage(data: Dict[str, Any]):
    _ensure_data_dir()
    try:
        TOKENS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to write local tokens file: {e}")

def _clean_token_str(token: str) -> str:
    t = token.strip()
    if t.lower().startswith("bearer "):
        return t[7:].strip()
    return t

async def _save_pool_to_redis(provider: str, pool_data: dict):
    try:
        redis_client = get_redis_client()
        redis_key = f"provider_pool:{provider}"
        await redis_client.set(redis_key, json.dumps(pool_data))
    except Exception as e:
        logger.debug(f"Redis store pool error for {provider}: {e}")

async def _get_pool_from_redis(provider: str) -> Optional[dict]:
    try:
        redis_client = get_redis_client()
        raw = await redis_client.get(f"provider_pool:{provider}")
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.debug(f"Redis get pool error for {provider}: {e}")
    return None

async def add_provider_token(
    provider: str,
    token: str,
    expires_at: Optional[str] = None,
    token_type: str = "Bearer",
) -> dict:
    """
    Append a new token to the provider's token pool for multi-token rotation.
    """
    provider_clean = provider.strip().lower()
    token_clean = _clean_token_str(token)
    local_data = _read_local_storage()

    pool = local_data.get(provider_clean, {
        "provider": provider_clean,
        "active_index": 0,
        "tokens": [],
    })

    token_obj = {
        "id": f"tok_{uuid.uuid4().hex[:6]}",
        "token": token_clean,
        "token_type": token_type,
        "expires_at": expires_at or "2027-10-01T00:00:00Z",
        "cooldown_until": None,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }

    # Avoid duplicate tokens in pool
    existing_tokens = [t["token"] for t in pool["tokens"]]
    if token_clean not in existing_tokens:
        pool["tokens"].append(token_obj)
    pool["updated_at"] = datetime.now(timezone.utc).isoformat()

    local_data[provider_clean] = pool
    _write_local_storage(local_data)
    await _save_pool_to_redis(provider_clean, pool)

    return token_obj

async def set_provider_token(
    provider: str,
    token: str,
    expires_at: Optional[str] = None,
    token_type: str = "Bearer",
) -> dict:
    """
    Set primary token for a provider, resetting or initializing the pool.
    """
    provider_clean = provider.strip().lower()
    token_clean = _clean_token_str(token)
    local_data = _read_local_storage()

    pool = {
        "provider": provider_clean,
        "active_index": 0,
        "tokens": [
            {
                "id": "tok_1",
                "token": token_clean,
                "token_type": token_type,
                "expires_at": expires_at or "2027-10-01T00:00:00Z",
                "cooldown_until": None,
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    local_data[provider_clean] = pool
    _write_local_storage(local_data)
    await _save_pool_to_redis(provider_clean, pool)

    return pool["tokens"][0]

async def get_provider_token(provider: str) -> Optional[dict]:
    """
    Retrieve active token for a provider.
    Skips tokens that are currently on cooldown (e.g. following a 429).
    Falls back to environment settings (e.g. settings.JAJIGA_TOKEN) if no pool configured.
    """
    provider_clean = provider.strip().lower()

    # 1. Fetch pool from Redis or local storage
    pool = await _get_pool_from_redis(provider_clean)
    if not pool:
        local_data = _read_local_storage()
        pool = local_data.get(provider_clean)

    now = datetime.now(timezone.utc)

    if pool and pool.get("tokens"):
        tokens: List[dict] = pool["tokens"]
        total = len(tokens)
        active_idx = pool.get("active_index", 0) % total

        # Check tokens starting from active_index
        for offset in range(total):
            idx = (active_idx + offset) % total
            candidate = tokens[idx]
            cooldown = candidate.get("cooldown_until")
            if cooldown:
                try:
                    cd_dt = datetime.fromisoformat(cooldown.replace("Z", "+00:00"))
                    if cd_dt > now:
                        # Candidate is still on cooldown
                        continue
                    else:
                        # Cooldown elapsed
                        candidate["cooldown_until"] = None
                except Exception:
                    candidate["cooldown_until"] = None

            # Candidate is available
            if idx != active_idx:
                pool["active_index"] = idx
                await _save_pool_to_redis(provider_clean, pool)
                _write_local_storage({**_read_local_storage(), provider_clean: pool})

            return candidate

        logger.warning(f"All tokens in pool for {provider_clean} are currently on rate-limit cooldown.")

    # 2. Fallback to Environment Settings
    if provider_clean == "jajiga" and settings.JAJIGA_TOKEN:
        tok = _clean_token_str(settings.JAJIGA_TOKEN)
        return {
            "id": "env_token",
            "token": tok,
            "token_type": "Bearer",
            "expires_at": "2027-10-01T00:00:00Z",
            "source": "environment",
        }

    return None

async def rotate_provider_token(
    provider: str,
    reason: str = "429_rate_limit",
    cooldown_seconds: int = 300,
) -> Optional[dict]:
    """
    Rotate provider to the next token in the pool.
    If called due to a 429, marks the current token with a cooldown timestamp.
    """
    provider_clean = provider.strip().lower()

    pool = await _get_pool_from_redis(provider_clean)
    if not pool:
        local_data = _read_local_storage()
        pool = local_data.get(provider_clean)

    if not pool or not pool.get("tokens"):
        logger.warning(f"Cannot rotate tokens for {provider_clean}: No token pool found.")
        return None

    tokens = pool["tokens"]
    curr_idx = pool.get("active_index", 0) % len(tokens)

    # Mark current token on cooldown if rate-limited
    if reason.startswith("429"):
        now = datetime.now(timezone.utc)
        cd_dt = now + timedelta(seconds=cooldown_seconds)
        tokens[curr_idx]["cooldown_until"] = cd_dt.isoformat()
        logger.warning(f"Token {tokens[curr_idx]['id']} for {provider_clean} marked on cooldown until {cd_dt.isoformat()} ({reason})")

    # Advance index
    next_idx = (curr_idx + 1) % len(tokens)
    pool["active_index"] = next_idx
    pool["updated_at"] = datetime.now(timezone.utc).isoformat()

    local_data = _read_local_storage()
    local_data[provider_clean] = pool
    _write_local_storage(local_data)
    await _save_pool_to_redis(provider_clean, pool)

    next_tok = tokens[next_idx]
    logger.info(f"Rotated {provider_clean} token to {next_tok['id']} (index {next_idx}/{len(tokens)})")
    return next_tok

async def remove_provider_token(provider: str, token_id_or_prefix: str) -> bool:
    """Remove a specific token from the pool by ID or prefix."""
    provider_clean = provider.strip().lower()
    local_data = _read_local_storage()
    pool = local_data.get(provider_clean)
    if not pool or not pool.get("tokens"):
        return False

    orig_count = len(pool["tokens"])
    pool["tokens"] = [
        t for t in pool["tokens"]
        if t["id"] != token_id_or_prefix and not t["token"].startswith(token_id_or_prefix)
    ]
    if len(pool["tokens"]) < orig_count:
        pool["active_index"] = 0
        pool["updated_at"] = datetime.now(timezone.utc).isoformat()
        local_data[provider_clean] = pool
        _write_local_storage(local_data)
        await _save_pool_to_redis(provider_clean, pool)
        return True
    return False

async def list_provider_tokens() -> List[dict]:
    """List all registered providers and their token pools."""
    local_data = _read_local_storage()

    # Merge env token if not already in local data
    if "jajiga" not in local_data and settings.JAJIGA_TOKEN:
        tok = _clean_token_str(settings.JAJIGA_TOKEN)
        local_data["jajiga"] = {
            "provider": "jajiga",
            "active_index": 0,
            "tokens": [
                {
                    "id": "env_token",
                    "token": tok,
                    "token_type": "Bearer",
                    "expires_at": "2027-10-01T00:00:00Z",
                    "cooldown_until": None,
                    "added_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    return list(local_data.values())

async def revoke_provider_token(provider: str) -> bool:
    """Revoke all tokens for a provider."""
    provider_clean = provider.strip().lower()
    local_data = _read_local_storage()
    removed = local_data.pop(provider_clean, None) is not None
    _write_local_storage(local_data)

    try:
        redis_client = get_redis_client()
        await redis_client.delete(f"provider_pool:{provider_clean}")
    except Exception as e:
        logger.warning(f"Redis delete pool failed: {e}")

    return removed
