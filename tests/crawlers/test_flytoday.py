import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.flytoday.crawler import FlyTodayCrawler
from app.schemas.flight import FlightSearchQuery
from app.schemas.transport import TransportSearchQuery

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

@pytest.fixture
def flytoday_flight_fixture():
    with open(FIXTURES_DIR / "flytoday_flight_response.json") as f:
        return json.load(f)

@pytest.fixture
def flytoday_transport_fixture():
    with open(FIXTURES_DIR / "flytoday_transport_response.json") as f:
        return json.load(f)

@pytest.mark.asyncio
async def test_flytoday_search_flights(flytoday_flight_fixture):
    crawler = FlyTodayCrawler()

    mock_response = AsyncMock()
    mock_response.json.return_value = flytoday_flight_fixture

    with patch.object(crawler.client, "post", return_value=mock_response):
        query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
        results = await crawler.search_flights(query)

        assert len(results) == 1
        f1 = results[0]
        assert f1.id == "flytoday_fl_201"
        assert f1.provider.name == "flytoday"
        assert f1.price.amount == 17800000
        assert f1.outbound[0].flight_number == "2801"
        assert f1.outbound[0].airline_name == "Meraj Airlines"

@pytest.mark.asyncio
async def test_flytoday_search_buses(flytoday_transport_fixture):
    crawler = FlyTodayCrawler()

    mock_response = AsyncMock()
    mock_response.json.return_value = flytoday_transport_fixture

    with patch.object(crawler.client, "post", return_value=mock_response):
        query = TransportSearchQuery(
            origin="Tehran",
            destination="Isfahan",
            depart_date="2026-10-15",
            transport_type="bus",
        )
        results = await crawler.search_transport(query)

        assert len(results) == 1
        b1 = results[0]
        assert b1.id == "ft_bus_301"
        assert b1.provider.name == "flytoday"
        assert b1.transport_type == "bus"
        assert b1.company_name == "همسفر چابکسواران"
        assert b1.available_seats == 8
        assert b1.price.amount == 2850000
