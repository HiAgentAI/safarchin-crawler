import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.karnaval.crawler import KarnavalCrawler
from app.schemas.accommodation import AccommodationSearchQuery

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

@pytest.fixture
def karnaval_accommodation_fixture():
    with open(FIXTURES_DIR / "karnaval_accommodation_response.json") as f:
        return json.load(f)

@pytest.mark.asyncio
async def test_karnaval_search_accommodations(karnaval_accommodation_fixture):
    crawler = KarnavalCrawler()

    mock_response = AsyncMock()
    mock_response.json.return_value = karnaval_accommodation_fixture

    with patch.object(crawler.client, "get", return_value=mock_response):
        query = AccommodationSearchQuery(
            city="Ramsar",
            checkin_date="2026-10-15",
            checkout_date="2026-10-18",
            guests=6,
        )
        results = await crawler.search_accommodations(query)

        assert len(results) == 1
        v1 = results[0]
        assert v1.id == "karnaval_villa_99"
        assert v1.provider.name == "karnaval"
        assert v1.title == "ویلای دوبلکس استخردار رامسر"
        assert v1.city == "رامسر"
        assert v1.price_per_night.amount == 4500000
        assert v1.bedrooms == 3
        assert "استخر آبگرم" in v1.amenities
