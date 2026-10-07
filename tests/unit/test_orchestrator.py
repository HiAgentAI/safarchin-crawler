import asyncio
import pytest
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import CrawlerRegistry
from app.crawlers.orchestrator import CrawlerOrchestrator
from app.core.redis import CacheManager, resolve_cache_params
from app.schemas.flight import FlightSearchQuery, FlightResult, FlightSegment
from app.schemas.hotel import HotelSearchQuery, HotelResult, RoomOffer
from app.schemas.accommodation import AccommodationSearchQuery, AccommodationResult, ProvinceItem, CityItem
from app.schemas.transport import TransportSearchQuery, TransportResult
from app.schemas.restaurant import RestaurantSearchQuery, RestaurantResult
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

class SlowFlightCrawler(BaseCrawler):
    """Exceeds any sane per-provider budget."""
    provider_name = "slow_prov"
    supported_services = {"flight"}

    async def search_flights(self, query: FlightSearchQuery):
        await asyncio.sleep(5)
        return [
            FlightResult(
                id="slow",
                provider=ProviderInfo(name="slow_prov"),
                price=PriceInfo(amount=1, currency=Currency.IRT),
                outbound=[FlightSegment(
                    airline_name="SlowAir", flight_number="S1",
                    origin_code=query.origin, destination_code=query.destination,
                    departure_time="10:00", arrival_time="11:00", departure_date=query.depart_date,
                )],
            )
        ]

class RialFlightCrawler(BaseCrawler):
    provider_name = "rial_prov"
    supported_services = {"flight"}

    async def search_flights(self, query: FlightSearchQuery):
        # 1,000,000 Rial == 100,000 Toman
        return [
            FlightResult(
                id="rial",
                provider=ProviderInfo(name="rial_prov"),
                price=PriceInfo(amount=1_000_000, currency=Currency.IRR),
                outbound=[FlightSegment(
                    airline_name="RialAir", flight_number="R1",
                    origin_code=query.origin, destination_code=query.destination,
                    departure_time="10:00", arrival_time="11:00", departure_date=query.depart_date,
                )],
            )
        ]

class TomanFlightCrawler(BaseCrawler):
    provider_name = "toman_prov"
    supported_services = {"flight"}

    async def search_flights(self, query: FlightSearchQuery):
        # Equal real value to RialFlightCrawler: 100,000 Toman == 1,000,000 Rial
        return [
            FlightResult(
                id="toman",
                provider=ProviderInfo(name="toman_prov"),
                price=PriceInfo(amount=100_000, currency=Currency.IRT),
                outbound=[FlightSegment(
                    airline_name="TomanAir", flight_number="T9",
                    origin_code=query.origin, destination_code=query.destination,
                    departure_time="12:00", arrival_time="13:00", departure_date=query.depart_date,
                )],
            )
        ]

def _cached_payload(mock_redis, orchestrator, query):
    """Read back the raw search-cache payload the orchestrator wrote."""
    import json
    cache_key = orchestrator._generate_cache_key("flight", query.model_dump())
    raw = mock_redis._store.get(cache_key)
    return json.loads(raw) if raw else None

@pytest.mark.asyncio
async def test_orchestrator_attributes_results_to_their_own_provider(mock_redis, monkeypatch):
    """
    A failing provider must not shift the surviving provider's results onto itself.

    The previous implementation zipped the full crawler list against a results
    list that had already dropped failures, so survivor results were attributed
    to the failed crawler and cached under the failed crawler's name.
    """
    test_registry = CrawlerRegistry()
    test_registry.register(FailingFlightCrawler)
    test_registry.register(SuccessFlightCrawler)

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr)

    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
    results = await orchestrator.search_flights(query, use_cache=True, ttl_seconds=600)

    assert len(results) == 1
    # The survivor keeps its own identity on the result itself
    assert results[0].provider.name == "success_prov"

    # ...and the cache records the survivor, never the failed provider
    payload = _cached_payload(mock_redis, orchestrator, query)
    assert payload is not None, "expected the survivor's results to be cached"
    assert set(payload["cached_providers"]) == {"success_prov"}, (
        f"expected only the surviving provider to be cached, got {payload['cached_providers']}"
    )

    # The payload stored under the cache must carry the survivor's own rows
    assert len(payload["results"]) == 1
    assert payload["results"][0]["provider"]["name"] == "success_prov"

@pytest.mark.asyncio
async def test_orchestrator_slow_provider_does_not_discard_fast_sibling(mock_redis, monkeypatch):
    """
    Each provider gets its own deadline; a slow one drops out alone.

    Previously one shared wait_for wrapped the whole gather, so a single slow
    provider failed the entire request and discarded siblings that had already
    succeeded.
    """
    test_registry = CrawlerRegistry()
    test_registry.register(SlowFlightCrawler)
    test_registry.register(SuccessFlightCrawler)

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    cache_mgr = CacheManager(client=mock_redis)
    # Short budget so the test does not actually wait 5 real seconds
    orchestrator = CrawlerOrchestrator(cache_manager=cache_mgr, timeout=0.05)

    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
    results = await orchestrator.search_flights(query, use_cache=False)

    # The fast sibling survives; the slow provider contributes nothing
    assert len(results) == 1
    assert results[0].provider.name == "success_prov"
    assert all(r.provider.name != "slow_prov" for r in results)

@pytest.mark.asyncio
async def test_orchestrator_timeout_is_per_provider_not_shared(mock_redis, monkeypatch):
    """A provider with an override keeps its larger budget instead of the shared default."""
    orchestrator = CrawlerOrchestrator(cache_manager=CacheManager(client=mock_redis), timeout=15.0)

    assert orchestrator._timeout_for("alibaba") > orchestrator.timeout
    assert orchestrator._timeout_for("flytoday") == orchestrator.timeout
    assert orchestrator._timeout_for("ALIBABA") == orchestrator._timeout_for("alibaba")
    assert orchestrator._timeout_for("") == orchestrator.timeout

def test_price_sort_key_normalizes_across_units():
    """IRT is one tenth of IRR, so equal real values must produce equal keys."""
    from app.crawlers.orchestrator import price_sort_key
    rial = PriceInfo(amount=1_000_000, currency=Currency.IRR)
    toman = PriceInfo(amount=100_000, currency=Currency.IRT)
    assert price_sort_key(rial) == price_sort_key(toman) == 1_000_000.0

@pytest.mark.asyncio
async def test_orchestrator_sorts_mixed_currencies_by_real_value(mock_redis, monkeypatch):
    """
    A cheaper Toman price must not be ranked as if it were 10x cheaper.

    Raw-amount sorting would place 100,000 Toman below 1,000,000 Rial even though
    the two are the same real amount.
    """
    test_registry = CrawlerRegistry()
    test_registry.register(RialFlightCrawler)
    test_registry.register(TomanFlightCrawler)

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)

    orchestrator = CrawlerOrchestrator(cache_manager=CacheManager(client=mock_redis))
    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
    results = await orchestrator.search_flights(query, use_cache=False)

    assert len(results) == 2
    # Equal real value, so both keys match and the order is only a tiebreak
    from app.crawlers.orchestrator import price_sort_key
    assert price_sort_key(results[0].price) == price_sort_key(results[1].price)

@pytest.mark.asyncio
async def test_orchestrator_cheaper_result_sorts_first_across_units(mock_redis, monkeypatch):
    """
    A cheaper option ranks first regardless of which unit it uses.

    The Rial option (500,000 IRR) is genuinely cheaper than the Toman option
    (300,000 IRT == 3,000,000 IRR), even though its raw amount is larger.
    Sorting on raw amounts ranks the Toman option first, which is wrong.
    """
    test_registry = CrawlerRegistry()
    test_registry.register(RialFlightCrawler)
    test_registry.register(TomanFlightCrawler)

    monkeypatch.setattr("app.crawlers.orchestrator.crawler_registry", test_registry)
    monkeypatch.setattr(RialFlightCrawler, "search_flights", _rial_at(500_000))
    monkeypatch.setattr(TomanFlightCrawler, "search_flights", _toman_at(300_000))

    orchestrator = CrawlerOrchestrator(cache_manager=CacheManager(client=mock_redis))
    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-15")
    results = await orchestrator.search_flights(query, use_cache=False)

    assert len(results) == 2
    assert results[0].provider.name == "rial_prov", (
        "the 500,000 IRR option is cheaper than 300,000 IRT and must sort first"
    )
    assert results[1].provider.name == "toman_prov"

def _rial_at(amount):
    async def search_flights(self, query: FlightSearchQuery):
        return [
            FlightResult(
                id="rial",
                provider=ProviderInfo(name="rial_prov"),
                price=PriceInfo(amount=amount, currency=Currency.IRR),
                outbound=[FlightSegment(
                    airline_name="RialAir", flight_number="R1",
                    origin_code=query.origin, destination_code=query.destination,
                    departure_time="10:00", arrival_time="11:00", departure_date=query.depart_date,
                )],
            )
        ]
    return search_flights

def _toman_at(amount):
    async def search_flights(self, query: FlightSearchQuery):
        return [
            FlightResult(
                id="toman",
                provider=ProviderInfo(name="toman_prov"),
                price=PriceInfo(amount=amount, currency=Currency.IRT),
                outbound=[FlightSegment(
                    airline_name="TomanAir", flight_number="T9",
                    origin_code=query.origin, destination_code=query.destination,
                    departure_time="12:00", arrival_time="13:00", departure_date=query.depart_date,
                )],
            )
        ]
    return search_flights

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


@pytest.mark.asyncio
async def test_orchestrator_search_restaurants(mock_redis):
    from unittest.mock import AsyncMock, patch
    from app.crawlers.openstreetmap.crawler import OpenStreetMapCrawler

    registry = CrawlerRegistry()
    crawler = OpenStreetMapCrawler()
    fake_res = [
        RestaurantResult(
            id="osm:node:1",
            provider=ProviderInfo(name="openstreetmap"),
            name="رستوران تست",
            city="Tehran",
            latitude=35.7,
            longitude=51.4,
        )
    ]
    crawler.search_restaurants = AsyncMock(return_value=fake_res)
    registry.register(OpenStreetMapCrawler, name="openstreetmap", services={"restaurant"})
    registry._instances["openstreetmap"] = crawler


    cache = CacheManager(client=mock_redis)
    orchestrator = CrawlerOrchestrator(cache_manager=cache)

    with patch("app.crawlers.orchestrator.crawler_registry", registry):
        query = RestaurantSearchQuery(city="Tehran")
        results = await orchestrator.search_restaurants(query)
        assert len(results) == 1
        assert results[0].name == "رستوران تست"

