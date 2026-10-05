import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from app.crawlers.iranhotel.crawler import IranHotelCrawler
from app.schemas.hotel import HotelSearchQuery
from app.schemas.accommodation import AccommodationSearchQuery

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

@pytest.fixture
def iranhotel_search_fixture():
    with open(FIXTURES_DIR / "iranhotel_search_response.json", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture
def iranhotel_rooms_fixture():
    with open(FIXTURES_DIR / "iranhotel_rooms_response.json", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture
def iranhotel_states_cities_fixture():
    with open(FIXTURES_DIR / "iranhotel_states_cities_response.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_iranhotel_search_hotels(iranhotel_search_fixture):
    crawler = IranHotelCrawler()

    mock_resp = AsyncMock()
    mock_resp.json.return_value = iranhotel_search_fixture

    with patch.object(crawler.client, "get", return_value=mock_resp) as mock_get:
        query = HotelSearchQuery(
            city="tehran",
            checkin_date="1405/07/15",
            checkout_date="1405/07/16",
            rooms=1,
            adults=2,
            stars=5,
            page=1,
        )
        results = await crawler.search_hotels(query)

        # Check call arguments
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["CityName"] == "tehran"
        assert call_kwargs["params"]["StartDate"] == "1405/07/15"
        assert call_kwargs["params"]["EndDate"] == "1405/07/16"
        assert call_kwargs["params"]["grades"] == "5"

        # Check parsed results
        assert len(results) == 2
        h1 = results[0]
        assert h1.id == "iho_149"
        assert h1.provider.name == "iranhotel"
        assert h1.hotel_name == "هتل پارسیان آزادی تهران"
        assert h1.stars == 5
        assert h1.user_rating == 4.4
        assert h1.reviews_count == 386
        assert h1.min_price_per_night.amount == 152000000.0
        assert h1.min_price_per_night.currency.value == "IRR"
        assert h1.discount_percent == 5.0
        assert h1.latitude == 35.789708
        assert h1.longitude == 51.390082
        assert "https://cdn.iranhotelonline.com" in h1.thumbnail_url

        h2 = results[1]
        assert h2.id == "iho_77"
        assert h2.hotel_name == "هتل کوثر تهران"
        assert h2.stars == 4
        assert h2.min_price_per_night.amount == 50000000.0


@pytest.mark.asyncio
async def test_iranhotel_fetch_hotel_rooms(iranhotel_rooms_fixture):
    crawler = IranHotelCrawler()

    mock_resp = AsyncMock()
    mock_resp.json.return_value = iranhotel_rooms_fixture

    with patch.object(crawler.client, "post", return_value=mock_resp) as mock_post:
        rooms = await crawler.fetch_hotel_rooms(
            hotel_id=149,
            checkin_date="1405/07/15",
            checkout_date="1405/07/16",
        )

        mock_post.assert_called_once()
        assert len(rooms) == 2

        r1 = rooms[0]
        assert r1.room_name == "اتاق دو تخته دبل نرمال"
        assert r1.capacity == 2
        assert r1.has_breakfast is True
        assert r1.is_cancellable is True  # nonRefundable is False
        assert r1.price_per_night.amount == 152000000.0
        assert r1.extra_capacity == 1
        assert r1.extra_price.amount == 40000000.0

        r2 = rooms[1]
        assert r2.room_name == "اتاق یک تخته نرمال"
        assert r2.capacity == 1
        assert r2.is_cancellable is False  # nonRefundable is True
        assert r2.price_per_night.amount == 108000000.0


@pytest.mark.asyncio
async def test_iranhotel_get_provinces(iranhotel_states_cities_fixture):
    crawler = IranHotelCrawler()

    mock_resp = AsyncMock()
    mock_resp.json.return_value = iranhotel_states_cities_fixture

    with patch.object(crawler.client, "get", return_value=mock_resp):
        provinces = await crawler.get_provinces()

        assert len(provinces) == 2
        p1 = provinces[0]
        assert p1.id == "8"
        assert p1.name == "تهران"
        assert p1.rooms_count == 75

        p2 = provinces[1]
        assert p2.id == "11"
        assert p2.name == "خراسان رضوی"
        assert p2.rooms_count == 227


@pytest.mark.asyncio
async def test_iranhotel_get_cities(iranhotel_states_cities_fixture):
    crawler = IranHotelCrawler()

    mock_resp = AsyncMock()
    mock_resp.json.return_value = iranhotel_states_cities_fixture

    with patch.object(crawler.client, "get", return_value=mock_resp):
        # 1. All cities
        all_cities = await crawler.get_cities()
        assert len(all_cities) == 3

        # 2. Cities filtered by province '8' (Tehran)
        tehran_cities = await crawler.get_cities(province_id="8")
        assert len(tehran_cities) == 2
        assert tehran_cities[0].name == "تهران"
        assert tehran_cities[0].slug == "tehran"
        assert tehran_cities[1].name == "دماوند"

        # 3. Cities filtered by province '11' (Khorasan)
        khorasan_cities = await crawler.get_cities(province_id="11")
        assert len(khorasan_cities) == 1
        assert khorasan_cities[0].name == "مشهد"
        assert khorasan_cities[0].slug == "mashhad"


@pytest.mark.asyncio
async def test_iranhotel_search_accommodations(iranhotel_search_fixture):
    crawler = IranHotelCrawler()

    mock_resp = AsyncMock()
    mock_resp.json.return_value = iranhotel_search_fixture

    with patch.object(crawler.client, "get", return_value=mock_resp):
        query = AccommodationSearchQuery(
            city="tehran",
            checkin_date="1405/07/15",
            checkout_date="1405/07/16",
            guests=2,
        )
        results = await crawler.search_accommodations(query)

        assert len(results) == 2
        r1 = results[0]
        assert r1.id == "iho_149"
        assert r1.provider.name == "iranhotel"
        assert r1.title == "هتل پارسیان آزادی تهران"
        # Converted to Tomans
        assert r1.price_per_night.amount == 15200000.0
        assert r1.price_per_night.currency.value == "IRT"


def test_iranhotel_date_normalization():
    crawler = IranHotelCrawler()

    # Jalali input with dashes
    assert crawler._normalize_date_to_jalali("1405-07-15") == "1405/07/15"

    # Jalali input already with slashes
    assert crawler._normalize_date_to_jalali("1405/07/15") == "1405/07/15"

    # Gregorian input
    jalali_output = crawler._normalize_date_to_jalali("2026-10-07")
    assert jalali_output == "1405/07/15"
