import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.jajiga.crawler import JajigaCrawler
from app.schemas.accommodation import AccommodationSearchQuery

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

@pytest.fixture
def jajiga_accommodation_fixture():
    with open(FIXTURES_DIR / "jajiga_accommodation_response.json", encoding="utf-8") as f:
        return json.load(f)

@pytest.mark.asyncio
async def test_jajiga_search_accommodations(jajiga_accommodation_fixture):
    crawler = JajigaCrawler()

    mock_response = AsyncMock()
    mock_response.json.return_value = jajiga_accommodation_fixture

    with patch.object(crawler.client, "get", return_value=mock_response):
        query = AccommodationSearchQuery(
            city="سوادکوه",
            checkin_date="2026-10-15",
            checkout_date="2026-10-18",
            guests=4,
            property_type="cottage",
            min_price=1000000,
            max_price=5000000,
            amenities=["pool", "wifi"],
            sort_by="low_price",
            page=1,
        )
        results = await crawler.search_accommodations(query)

        assert len(results) == 1
        r = results[0]
        assert r.id == "3254790"
        assert r.provider.name == "jajiga"
        assert "3254790" in r.provider.deep_link
        assert r.title == "رزرو کلبه چوبی در سوادکوه - لفور"
        assert r.city == "سوادکوه"
        assert r.capacity_standard == 4
        assert r.capacity_max == 8
        assert r.bedrooms == 2
        assert r.price_per_night.amount == 2200000  # price_after_discount
        assert r.price_per_night.currency.value == "IRT"
        assert r.rating == 4.9
        assert r.reviews_count == 67
        assert "https://storage.jajiga.com" in r.thumbnail_url
        assert "pool" in r.amenities

        # Verify structured pagination metadata
        assert crawler.last_pagination is not None
        assert crawler.last_pagination.current_page == 1
        assert crawler.last_pagination.per_page == 18
        assert crawler.last_pagination.total_count == 1105
        assert crawler.last_pagination.total_pages == 62
        assert crawler.last_pagination.has_next_page is True
        assert crawler.last_pagination.has_prev_page is False

def test_jajiga_build_search_params():
    crawler = JajigaCrawler()
    query = AccommodationSearchQuery(
        city="savadkuh",
        checkin_date="1405-07-24",  # Jalali date
        checkout_date="1405-07-26",
        guests=6,
        property_type="swiss_cottage",
        min_price=1500000,
        max_price=4000000,
        amenities=["pool", "jacuzzi"],
        sort_by="cheapest",
        page=2,
    )
    params = crawler._build_search_params(query, location_id="305")

    assert params["locations[]"] == "305"
    assert params["capacity"] == 6
    assert params["types[]"] == "swiss_cottage"
    assert params["min_price"] == 1500000
    assert params["max_price"] == 4000000
    assert params["features[]"] == ["pool", "jacuzzi"]
    assert params["order"] == "low_price"
    assert params["page"] == 2
    # Verify Gregorian date conversion
    assert params["checkin"].startswith("2026-")

@pytest.mark.asyncio
async def test_jajiga_auth_headers_with_token():
    crawler = JajigaCrawler()
    with patch("app.crawlers.jajiga.crawler.get_provider_token", return_value={"token": "test_jwt_123", "token_type": "Bearer"}):
        headers = await crawler._get_auth_headers()
        assert headers.get("Authorization") == "Bearer test_jwt_123"
        assert headers.get("Origin") == "https://www.jajiga.com"

@pytest.mark.asyncio
async def test_jajiga_auth_headers_without_token():
    crawler = JajigaCrawler()
    with patch("app.crawlers.jajiga.crawler.get_provider_token", return_value=None):
        headers = await crawler._get_auth_headers()
        assert "Authorization" not in headers
        assert headers.get("Origin") == "https://www.jajiga.com"

@pytest.mark.asyncio
async def test_jajiga_get_provinces():
    crawler = JajigaCrawler()
    mock_response = AsyncMock()
    mock_response.json.return_value = [
        {"id": "p24", "slug": "gilan", "name": "گیلان", "rooms_count": 8940},
        {"id": "p26", "slug": "mazandaran", "name": "مازندران", "rooms_count": 12150},
    ]

    with patch.object(crawler.client, "get", return_value=mock_response):
        provinces = await crawler.get_provinces()
        assert len(provinces) == 2
        assert provinces[0].id == "p24"
        assert provinces[0].slug == "gilan"
        assert provinces[0].name == "گیلان"
        assert provinces[0].rooms_count == 8940
        assert provinces[1].id == "p26"

@pytest.mark.asyncio
async def test_jajiga_get_cities():
    crawler = JajigaCrawler()
    mock_response = AsyncMock()
    mock_response.json.return_value = [
        {"id": "305", "url": "/s/savadkuh", "name": "سوادکوه", "rooms_count": 1105},
        {"id": "201", "url": "/s/ramsar", "name": "رامسر", "rooms_count": 2180},
    ]

    with patch.object(crawler.client, "get", return_value=mock_response):
        cities = await crawler.get_cities(province_id="p26")
        assert len(cities) == 2
        assert cities[0].id == "305"
        assert cities[0].slug == "savadkuh"
        assert cities[0].name == "سوادکوه"
        assert cities[0].rooms_count == 1105
        assert cities[0].province_id == "p26"

@pytest.mark.asyncio
async def test_jajiga_429_failover_rotates_token():
    crawler = JajigaCrawler()

    # Create mock response that returns 429 on first call, 200 on second call
    err_resp = AsyncMock()
    err_resp.status_code = 429

    success_resp = AsyncMock()
    success_resp.status_code = 200
    success_resp.json.return_value = [{"id": "p24", "slug": "gilan", "name": "گیلان"}]

    error_429 = Exception("HTTP 429 Too Many Requests")
    error_429.response = err_resp

    call_count = 0
    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise error_429
        return success_resp

    with patch.object(crawler.client, "get", side_effect=mock_get):
        with patch("app.crawlers.jajiga.crawler.rotate_provider_token", new_callable=AsyncMock) as mock_rotate:
            mock_rotate.return_value = {"token": "next_token_456"}
            resp = await crawler._execute_with_failover("https://api.jajiga.com/api/provinces")
            assert resp.status_code == 200
            assert mock_rotate.await_count == 1

