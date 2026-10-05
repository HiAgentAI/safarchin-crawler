import pytest
from unittest.mock import AsyncMock, patch
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
async def test_flights_search_unauthorized(async_client):
    resp = await async_client.get(
        "/api/v1/flights/search",
        params={"origin": "THR", "destination": "MHD", "depart_date": "2026-10-15"},
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_flights_search_authorized(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_flights", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/flights/search",
            params={"origin": "THR", "destination": "MHD", "depart_date": "2026-10-15"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total_results"] == 0

@pytest.mark.asyncio
async def test_hotels_search_authorized(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_hotels", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/hotels/search",
            params={"city": "Kish", "checkin_date": "2026-10-15", "checkout_date": "2026-10-18"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

@pytest.mark.asyncio
async def test_accommodations_search_authorized(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_accommodations", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/accommodations/search",
            params={"city": "Ramsar", "checkin_date": "2026-10-15", "checkout_date": "2026-10-18"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert "pagination" in resp.json()
        assert resp.json()["pagination"]["current_page"] == 1

@pytest.mark.asyncio
async def test_accommodations_provinces_authorized(async_client, auth_header):
    from app.schemas.accommodation import ProvinceItem
    mock_provinces = [
        ProvinceItem(id="p24", slug="gilan", name="گیلان", rooms_count=8940),
        ProvinceItem(id="p26", slug="mazandaran", name="مازندران", rooms_count=12150),
    ]
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.get_provinces", new_callable=AsyncMock) as mock_get_prov:
        mock_get_prov.return_value = mock_provinces
        resp = await async_client.get(
            "/api/v1/accommodations/provinces",
            params={"provider": "jajiga"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["provider"] == "jajiga"
        assert data["total"] == 2
        assert len(data["provinces"]) == 2
        assert data["provinces"][0]["id"] == "p24"

@pytest.mark.asyncio
async def test_accommodations_cities_authorized(async_client, auth_header):
    from app.schemas.accommodation import CityItem
    mock_cities = [
        CityItem(id="305", slug="savadkuh", name="سوادکوه", province_id="p26", rooms_count=1105),
    ]
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.get_cities", new_callable=AsyncMock) as mock_get_cities:
        mock_get_cities.return_value = mock_cities
        resp = await async_client.get(
            "/api/v1/accommodations/cities",
            params={"provider": "jajiga", "province_id": "p26"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["provider"] == "jajiga"
        assert data["province_id"] == "p26"
        assert data["total"] == 1
        assert data["cities"][0]["name"] == "سوادکوه"


@pytest.mark.asyncio
async def test_transport_buses_authorized(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_transport", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/transport/buses",
            params={"origin": "Tehran", "destination": "Isfahan", "depart_date": "2026-10-15"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

@pytest.mark.asyncio
async def test_flights_calendar_authorized(async_client, auth_header):
    mock_cal = {
        "origin": "Tehran",
        "destination": "Mashhad",
        "has_next_page": True,
        "calendar": [
            {"shamsi_date": "1405-07-14", "formatted_price": "9,312,000 تومان", "is_available": True}
        ]
    }
    with patch("app.crawlers.safarchin.crawler.SafarchinCrawler.search_calendar", new_callable=AsyncMock) as mock_cal_search:
        mock_cal_search.return_value = mock_cal
        resp = await async_client.get(
            "/api/v1/flights/calendar",
            params={"origin": "THR", "destination": "MHD", "page": 0},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["origin"] == "Tehran"
        assert len(data["data"]["calendar"]) == 1

@pytest.mark.asyncio
async def test_flights_airports_authorized(async_client, auth_header):
    resp = await async_client.get(
        "/api/v1/flights/airports",
        params={"query": "THR"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total"] >= 1
    assert data["airports"][0]["iata"] == "THR"


@pytest.mark.asyncio
async def test_accommodations_search_with_cache_ttl(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_accommodations", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/accommodations/search",
            params={"city": "Ramsar", "checkin_date": "2026-10-15", "checkout_date": "2026-10-18", "cache_ttl": 120},
            headers=auth_header,
        )
        assert resp.status_code == 200
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("use_cache") is True
        assert kwargs.get("ttl_seconds") == 120


@pytest.mark.asyncio
async def test_accommodations_search_with_cache_time(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_accommodations", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/accommodations/search",
            params={"city": "Ramsar", "checkin_date": "2026-10-15", "checkout_date": "2026-10-18", "cache_time": 180},
            headers=auth_header,
        )
        assert resp.status_code == 200
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("use_cache") is True
        assert kwargs.get("ttl_seconds") == 180


@pytest.mark.asyncio
async def test_accommodations_search_with_no_cache(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_accommodations", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/accommodations/search",
            params={"city": "Ramsar", "checkin_date": "2026-10-15", "checkout_date": "2026-10-18", "no_cache": True},
            headers=auth_header,
        )
        assert resp.status_code == 200
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("use_cache") is False


@pytest.mark.asyncio
async def test_hotels_search_with_cache_ttl(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_hotels", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/hotels/search",
            params={"city": "Tehran", "checkin_date": "2026-10-15", "checkout_date": "2026-10-18", "cache_ttl": 250},
            headers=auth_header,
        )
        assert resp.status_code == 200
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("use_cache") is True
        assert kwargs.get("ttl_seconds") == 250


@pytest.mark.asyncio
async def test_hotels_rooms_with_cache_ttl(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.get_hotel_rooms", new_callable=AsyncMock) as mock_rooms:
        mock_rooms.return_value = []
        resp = await async_client.get(
            "/api/v1/hotels/rooms",
            params={"hotel_id": 149, "checkin_date": "2026-10-15", "checkout_date": "2026-10-18", "cache_ttl": 300},
            headers=auth_header,
        )
        assert resp.status_code == 200
        mock_rooms.assert_called_once()
        _, kwargs = mock_rooms.call_args
        assert kwargs.get("use_cache") is True
        assert kwargs.get("ttl_seconds") == 300


@pytest.mark.asyncio
async def test_flights_calendar_with_cache_ttl(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.get_flight_calendar", new_callable=AsyncMock) as mock_cal:
        mock_cal.return_value = {"calendar": []}
        resp = await async_client.get(
            "/api/v1/flights/calendar",
            params={"origin": "THR", "destination": "MHD", "cache_ttl": 400},
            headers=auth_header,
        )
        assert resp.status_code == 200
        mock_cal.assert_called_once()
        _, kwargs = mock_cal.call_args
        assert kwargs.get("use_cache") is True
        assert kwargs.get("ttl_seconds") == 400


@pytest.mark.asyncio
async def test_transport_buses_with_cache_ttl(async_client, auth_header):
    with patch("app.crawlers.orchestrator.CrawlerOrchestrator.search_transport", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = await async_client.get(
            "/api/v1/transport/buses",
            params={"origin": "Tehran", "destination": "Isfahan", "depart_date": "2026-10-15", "cache_ttl": 500},
            headers=auth_header,
        )
        assert resp.status_code == 200
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("use_cache") is True
        assert kwargs.get("ttl_seconds") == 500


