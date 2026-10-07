import pytest
from unittest.mock import AsyncMock, patch
from app.schemas.restaurant import RestaurantResult
from app.schemas.common import ProviderInfo
from app.db.models import APIKey
from app.core.security import generate_api_key

@pytest.fixture
async def auth_header(db_session):
    plain_key, key_hash = generate_api_key()
    api_key_record = APIKey(
        key_hash=key_hash,
        client_name="Test Suite",
        tier="enterprise",
        rate_limit_per_min=500,
        is_active=True,
    )
    db_session.add(api_key_record)
    await db_session.commit()
    return {"X-API-Key": plain_key}


@pytest.mark.asyncio
async def test_restaurants_search_unauthorized(async_client):
    resp = await async_client.get(
        "/api/v1/restaurants/search",
        params={"city": "Tehran"},
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_restaurants_search_authorized(async_client, auth_header):
    fake_results = [
        RestaurantResult(
            id="osm:node:100",
            provider=ProviderInfo(name="openstreetmap"),
            name="رستوران البرز",
            city="Tehran",
            latitude=35.70,
            longitude=51.40,
            cuisine="iranian",
        )
    ]
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_restaurants", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = fake_results
        resp = await async_client.get(
            "/api/v1/restaurants/search",
            params={"city": "Tehran", "cuisine": "iranian", "limit": 10},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["city"] == "Tehran"
        assert data["total_results"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "رستوران البرز"
