import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.alibaba.crawler import AlibabaCrawler
from app.schemas.flight import FlightSearchQuery
from app.schemas.hotel import HotelSearchQuery
from app.schemas.accommodation import AccommodationSearchQuery

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

@pytest.fixture
def alibaba_flight_fixture():
    with open(FIXTURES_DIR / "alibaba_flight_response.json") as f:
        return json.load(f)

@pytest.mark.asyncio
async def test_alibaba_search_flights(alibaba_flight_fixture):
    crawler = AlibabaCrawler()
    
    mock_response = AsyncMock()
    mock_response.json.return_value = alibaba_flight_fixture
    
    with patch.object(crawler.client, "get", return_value=mock_response):
        query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
        results = await crawler.search_flights(query)

        assert len(results) == 2
        
        # Flight 1
        f1 = results[0]
        assert f1.id == "alibaba_fl_101"
        assert f1.provider.name == "alibaba"
        assert f1.price.amount == 18500000
        assert f1.is_charter is False
        assert len(f1.outbound) == 1
        assert f1.outbound[0].airline_name == "Mahan Air"
        assert f1.outbound[0].flight_number == "1032"

        # Flight 2
        f2 = results[1]
        assert f2.id == "alibaba_fl_102"
        assert f2.is_charter is True
        assert f2.outbound[0].airline_name == "Iran Air"
