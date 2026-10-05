import pytest

@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    resp = await async_client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "/docs" in data["docs"]

@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    resp = await async_client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "safarchin_crawler"

@pytest.mark.asyncio
async def test_providers_endpoint(async_client):
    resp = await async_client.get("/api/v1/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    provider_names = [p["name"] for p in data["providers"]]
    assert "alibaba" in provider_names
    assert "flytoday" in provider_names
    assert "karnaval" in provider_names
