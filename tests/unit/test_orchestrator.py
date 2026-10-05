import pytest
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import CrawlerRegistry
from app.crawlers.orchestrator import CrawlerOrchestrator
from app.core.redis import CacheManager, resolve_cache_params
from app.schemas.flight import FlightSearchQuery, FlightResult, FlightSegment
from app.schemas.hotel import HotelSearchQuery, HotelResult, RoomOffer
from app.schemas.accommodation import AccommodationSearchQuery, AccommodationResult, ProvinceItem, CityItem
from app.schemas.common import PriceInfo, ProviderInfo, Currency

class SuccessFlightCrawler(BaseCrawler):
    provider_name = "success_prov"
    supported_services = {"flight"}

    async def search_flights(self, query: FlightSearchQuery):
        return [
            FlightResult(
                id="f1",
                provider=ProviderInfo(name="success_prov"),
                price=PriceInfo(amount=1000, currency=Currency.IRT),
                outbound=[FlightSegment(
                    airline_name="TestAir", flight_number="T1",
                    origin_code=query.origin, destination_code=query.destination,
                    departure_time="10:00", arrival_time="11:30", departure_date=query.depart_date,
                )]
            )
        ]

class FailingFlightCrawler(BaseCrawler):
    provider_name = "failing_prov"
    supported_services = {"flight"}

    async def search_flights(self, query: FlightSearchQuery):
        raise ConnectionError("External API down")

@pytest.mark.asyncio
async def test_orchestrator_partial_failure_resilience(mock_redis, monkeypatch):
    test_registry = CrawlerRegistry()
    test_registry.register(SuccessFlightCrawler)
    test_registry.register(FailingFlightCrawler)

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
    results = await orchestrator.search_flights(query, use_cache=False)

    # Failing crawler failed gracefully, Success crawler returned results!
    assert len(results) == 1
    assert results[0].provider.name == "success_prov"
    assert results[0].price.amount == 1000

@pytest.mark.asyncio
async def test_orchestrator_caching(mock_redis, monkeypatch):
    test_registry = CrawlerRegistry()
    crawler_instance = SuccessFlightCrawler()
    test_registry.register(SuccessFlightCrawler)

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
    
    # 1st call: crawls and populates cache
    results1 = await orchestrator.search_flights(query, use_cache=True)
    assert len(results1) == 1

    # Clear registry so any live crawl would fail
    test_registry.clear()

    # 2nd call: hits cache!
    results2 = await orchestrator.search_flights(query, use_cache=True)
    assert len(results2) == 1
    assert results2[0].id == "f1"


class MockJajigaAccommodationCrawler(BaseCrawler):
    provider_name = "jajiga"
    supported_services = {"accommodation"}
    is_cacheable = True

    def __init__(self):
        self.call_count = 0

    async def search_accommodations(self, query):
        self.call_count += 1
        return [
            AccommodationResult(
                id="j1",
                provider=ProviderInfo(name="jajiga"),
                title="Jajiga Villa",
                property_type="villa",
                city=query.city,
                capacity_standard=2,
                capacity_max=4,
                bedrooms=2,
                price_per_night=PriceInfo(amount=2000, currency=Currency.IRT),
            )
        ]

    async def get_provinces(self):
        self.call_count += 1
        return [ProvinceItem(id="p24", slug="gilan", name="Gilan", rooms_count=50)]

    async def get_cities(self, province_id=None):
        self.call_count += 1
        return [CityItem(id="c1", slug="rasht", name="Rasht", province_id=province_id, rooms_count=20)]


class MockIranHotelCrawler(BaseCrawler):
    provider_name = "iranhotel"
    supported_services = {"accommodation", "hotel"}
    is_cacheable = False

    def __init__(self):
        self.call_count = 0

    async def search_accommodations(self, query):
        self.call_count += 1
        return [
            AccommodationResult(
                id="ih1",
                provider=ProviderInfo(name="iranhotel"),
                title="IranHotel Suite",
                property_type="suite",
                city=query.city,
                capacity_standard=2,
                capacity_max=3,
                bedrooms=1,
                price_per_night=PriceInfo(amount=3000, currency=Currency.IRT),
            )
        ]

    async def search_hotels(self, query):
        self.call_count += 1
        return [
            HotelResult(
                id="ih_h1",
                provider=ProviderInfo(name="iranhotel"),
                hotel_name="IranHotel Azadi",
                stars=5,
                city=query.city,
                min_price_per_night=PriceInfo(amount=50000000.0, currency=Currency.IRR),
            )
        ]

    async def fetch_hotel_rooms(self, hotel_id, checkin_date, checkout_date):
        self.call_count += 1
        return [
            RoomOffer(
                room_name="Deluxe Room",
                capacity=2,
                price_per_night=PriceInfo(amount=40000000.0, currency=Currency.IRR),
                total_price=PriceInfo(amount=40000000.0, currency=Currency.IRR),
            )
        ]

    async def get_provinces(self):
        self.call_count += 1
        return [ProvinceItem(id="8", slug="tehran", name="Tehran", rooms_count=100)]

    async def get_cities(self, province_id=None):
        self.call_count += 1
        return [CityItem(id="c8", slug="tehran", name="Tehran", province_id=province_id, rooms_count=80)]


@pytest.mark.asyncio
async def test_orchestrator_caller_defined_ttl(mock_redis, monkeypatch):
    test_registry = CrawlerRegistry()
    test_registry.register(SuccessFlightCrawler)
    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")

    # Search with caller-defined TTL of 120 seconds
    await orchestrator.search_flights(query, use_cache=True, ttl_seconds=120)

    cache_key = orchestrator._generate_cache_key("flight", query.model_dump())
    assert mock_redis._ttls.get(cache_key) == 120


@pytest.mark.asyncio
async def test_orchestrator_accommodation_caching_excludes_iranhotel(mock_redis, monkeypatch):
    test_registry = CrawlerRegistry()
    jajiga = MockJajigaAccommodationCrawler()
    iranhotel = MockIranHotelCrawler()

    test_registry._instances["jajiga"] = jajiga
    test_registry._classes["jajiga"] = MockJajigaAccommodationCrawler
    test_registry._instances["iranhotel"] = iranhotel
    test_registry._classes["iranhotel"] = MockIranHotelCrawler

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    query = AccommodationSearchQuery(city="tehran", checkin_date="2026-10-15", checkout_date="2026-10-18")

    # 1st call: both crawlers are called
    results1 = await orchestrator.search_accommodations(query, use_cache=True, ttl_seconds=300)
    assert len(results1) == 2
    assert jajiga.call_count == 1
    assert iranhotel.call_count == 1

    # Verify Redis cache contents: only jajiga must be cached, NOT iranhotel!
    cache_key = orchestrator._generate_cache_key("accommodation", query.model_dump())
    cached_data = await cache_mgr.get_json(cache_key)
    assert cached_data is not None
    assert "results" in cached_data
    cached_providers = {item["provider"]["name"] for item in cached_data["results"]}
    assert "jajiga" in cached_providers
    assert "iranhotel" not in cached_providers
    assert mock_redis._ttls.get(cache_key) == 300

    # 2nd call: Jajiga hits cache (NOT crawled again), Iran Hotel MUST crawl live!
    results2 = await orchestrator.search_accommodations(query, use_cache=True, ttl_seconds=300)
    assert len(results2) == 2
    assert jajiga.call_count == 1  # Hit cache!
    assert iranhotel.call_count == 2  # Live scrape repeated!

    # 3rd call with use_cache=False: forces live scrape on all
    results3 = await orchestrator.search_accommodations(query, use_cache=False)
    assert len(results3) == 2
    assert jajiga.call_count == 2
    assert iranhotel.call_count == 3


@pytest.mark.asyncio
async def test_orchestrator_hotels_caching_excludes_iranhotel(mock_redis, monkeypatch):
    test_registry = CrawlerRegistry()
    iranhotel = MockIranHotelCrawler()

    test_registry._instances["iranhotel"] = iranhotel
    test_registry._classes["iranhotel"] = MockIranHotelCrawler

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    query = HotelSearchQuery(city="tehran", checkin_date="2026-10-15", checkout_date="2026-10-18")

    # 1st call: crawled live, but NOT saved to cache because iranhotel is non-cacheable
    results1 = await orchestrator.search_hotels(query, use_cache=True, ttl_seconds=600)
    assert len(results1) == 1
    assert iranhotel.call_count == 1

    # Check that Redis contains nothing for this query
    cache_key = orchestrator._generate_cache_key("hotel", query.model_dump())
    cached_data = await cache_mgr.get_json(cache_key)
    assert cached_data is None

    # 2nd call: must crawl live again
    results2 = await orchestrator.search_hotels(query, use_cache=True)
    assert len(results2) == 1
    assert iranhotel.call_count == 2


@pytest.mark.asyncio
async def test_orchestrator_hotel_rooms_iranhotel_never_cached(mock_redis, monkeypatch):
    test_registry = CrawlerRegistry()
    iranhotel = MockIranHotelCrawler()
    test_registry._instances["iranhotel"] = iranhotel
    test_registry._classes["iranhotel"] = MockIranHotelCrawler

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    # 1st call:
    rooms1 = await orchestrator.get_hotel_rooms(
        hotel_id=149,
        checkin_date="2026-10-15",
        checkout_date="2026-10-18",
        provider="iranhotel",
        use_cache=True,
        ttl_seconds=300,
    )
    assert len(rooms1) == 1
    assert iranhotel.call_count == 1

    # 2nd call: Iran Hotel must NOT hit cache
    rooms2 = await orchestrator.get_hotel_rooms(
        hotel_id=149,
        checkin_date="2026-10-15",
        checkout_date="2026-10-18",
        provider="iranhotel",
        use_cache=True,
    )
    assert len(rooms2) == 1
    assert iranhotel.call_count == 2

    # Check Redis has no hotel_rooms keys
    assert len(mock_redis._store) == 0


@pytest.mark.asyncio
async def test_orchestrator_locations_iranhotel_never_cached(mock_redis, monkeypatch):
    test_registry = CrawlerRegistry()
    iranhotel = MockIranHotelCrawler()
    jajiga = MockJajigaAccommodationCrawler()
    test_registry._instances["iranhotel"] = iranhotel
    test_registry._classes["iranhotel"] = MockIranHotelCrawler
    test_registry._instances["jajiga"] = jajiga
    test_registry._classes["jajiga"] = MockJajigaAccommodationCrawler

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    # Iran Hotel provinces: never cached
    p1 = await orchestrator.get_provinces(provider="iranhotel", use_cache=True)
    p2 = await orchestrator.get_provinces(provider="iranhotel", use_cache=True)
    assert len(p1) == 1
    assert iranhotel.call_count == 2
    assert "location_provinces:iranhotel" not in mock_redis._store

    # Jajiga provinces: ARE cached with caller TTL
    jp1 = await orchestrator.get_provinces(provider="jajiga", use_cache=True, ttl_seconds=450)
    assert jajiga.call_count == 1
    assert "location_provinces:jajiga" in mock_redis._store
    assert mock_redis._ttls.get("location_provinces:jajiga") == 450

    jp2 = await orchestrator.get_provinces(provider="jajiga", use_cache=True)
    assert jajiga.call_count == 1  # Hit cache!


def test_resolve_cache_params_helper():
    # Defaults
    use_cache, ttl = resolve_cache_params()
    assert use_cache is True
    assert ttl == 600

    # Caller defined cache_ttl
    use_cache, ttl = resolve_cache_params(cache_ttl=120)
    assert use_cache is True
    assert ttl == 120

    # Caller defined cache_time (alias)
    use_cache, ttl = resolve_cache_params(cache_time=300)
    assert use_cache is True
    assert ttl == 300

    # cache_ttl takes precedence over cache_time
    use_cache, ttl = resolve_cache_params(cache_ttl=100, cache_time=200)
    assert use_cache is True
    assert ttl == 100

    # no_cache disables caching
    use_cache, ttl = resolve_cache_params(no_cache=True, cache_ttl=120)
    assert use_cache is False
    assert ttl == 0

    # cache_ttl=0 disables caching
    use_cache, ttl = resolve_cache_params(cache_ttl=0)
    assert use_cache is False
    assert ttl == 0

    # cache_time=0 disables caching
    use_cache, ttl = resolve_cache_params(cache_time=0)
    assert use_cache is False
    assert ttl == 0
