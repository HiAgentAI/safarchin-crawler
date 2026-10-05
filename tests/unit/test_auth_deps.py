import pytest
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.core.security import generate_api_key
from app.db.models import APIKey

test_router = APIRouter()

@test_router.get("/protected")
async def protected_route(key: APIKey = Depends(verify_api_key)):
    return {"status": "authorized", "client": key.client_name, "tier": key.tier}

@pytest.mark.asyncio
async def test_auth_missing_key(async_client):
    from app.main import app
    app.include_router(test_router)

    resp = await async_client.get("/protected")
    assert resp.status_code == 401
    assert "Missing 'X-API-Key'" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_auth_invalid_key(async_client):
    resp = await async_client.get("/protected", headers={"X-API-Key": "sc_live_invalidkey12345"})
    assert resp.status_code == 401
    assert "Invalid API Key" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_auth_valid_key(async_client, db_session):
    plain_key, key_hash = generate_api_key()
    api_key_record = APIKey(
        key_hash=key_hash,
        client_name="Test Frontend",
        tier="pro",
        rate_limit_per_min=10,
        is_active=True,
    )
    db_session.add(api_key_record)
    await db_session.commit()

    resp = await async_client.get("/protected", headers={"X-API-Key": plain_key})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "authorized"
    assert data["client"] == "Test Frontend"
    assert data["tier"] == "pro"

@pytest.mark.asyncio
async def test_auth_inactive_key(async_client, db_session):
    plain_key, key_hash = generate_api_key()
    api_key_record = APIKey(
        key_hash=key_hash,
        client_name="Revoked Client",
        is_active=False,
    )
    db_session.add(api_key_record)
    await db_session.commit()

    resp = await async_client.get("/protected", headers={"X-API-Key": plain_key})
    assert resp.status_code == 403
    assert "inactive or revoked" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_auth_rate_limiting(async_client, db_session):
    plain_key, key_hash = generate_api_key()
    api_key_record = APIKey(
        key_hash=key_hash,
        client_name="Limited Client",
        rate_limit_per_min=2,
        is_active=True,
    )
    db_session.add(api_key_record)
    await db_session.commit()

    # Request 1: ok
    r1 = await async_client.get("/protected", headers={"X-API-Key": plain_key})
    assert r1.status_code == 200

    # Request 2: ok
    r2 = await async_client.get("/protected", headers={"X-API-Key": plain_key})
    assert r2.status_code == 200

    # Request 3: rate limited
    r3 = await async_client.get("/protected", headers={"X-API-Key": plain_key})
    assert r3.status_code == 429
    assert "Rate limit exceeded" in r3.json()["detail"]
