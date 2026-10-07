import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.crawlers.openstreetmap.normalize import (
    haversine_distance,
    extract_restaurant_result,
    deduplicate_restaurants,
    normalize_text,
)
from app.crawlers.openstreetmap.crawler import OpenStreetMapCrawler
from app.schemas.restaurant import RestaurantSearchQuery, RestaurantResult
from app.schemas.common import ProviderInfo

def test_haversine_distance():
    # Same point should be 0 meters
    assert haversine_distance(35.6892, 51.3890, 35.6892, 51.3890) == 0.0

    # Approx 1 km difference in latitude (1 deg lat ~ 111 km)
    dist = haversine_distance(35.6892, 51.3890, 35.6982, 51.3890)
    assert 900 < dist < 1100

def test_extract_restaurant_result():
    # 1. Node with direct lat/lon
    node_el = {
        "type": "node",
        "id": 101,
        "lat": 35.70,
        "lon": 51.40,
        "timestamp": "2026-01-01T00:00:00Z",
        "tags": {
            "name": "رستوران البرز",
            "name:en": "Alborz Restaurant",
            "cuisine": "kebab;iranian",
            "phone": "02188888888",
            "addr:street": "سهروردی شمالی",
        },
    }
    res = extract_restaurant_result(node_el, "Tehran")
    assert res is not None
    assert res.id == "osm:node:101"
    assert res.name == "رستوران البرز"
    assert res.name_en == "Alborz Restaurant"
    assert res.latitude == 35.70
    assert res.longitude == 51.40
    assert res.cuisine == "kebab;iranian"
    assert res.phone == "02188888888"
    assert res.address == "سهروردی شمالی"
    assert res.last_edited == "2026-01-01T00:00:00Z"

    # 2. Way with center
    way_el = {
        "type": "way",
        "id": 202,
        "center": {"lat": 35.71, "lon": 51.41},
        "tags": {
            "name": "رستوران مسلم",
            "cuisine": "iranian",
        },
    }
    way_res = extract_restaurant_result(way_el, "Tehran")
    assert way_res is not None
    assert way_res.id == "osm:way:202"
    assert way_res.name == "رستوران مسلم"
    assert way_res.latitude == 35.71
    assert way_res.longitude == 51.41

    # 3. Element with no name returns None
    anon_el = {"type": "node", "id": 303, "lat": 35.0, "lon": 51.0, "tags": {"amenity": "restaurant"}}
    assert extract_restaurant_result(anon_el, "Tehran") is None

    # 4. Element with no coordinates returns None
    no_coord_el = {"type": "way", "id": 404, "tags": {"name": "رستوران بی نام"}}
    assert extract_restaurant_result(no_coord_el, "Tehran") is None

def test_deduplicate_restaurants():
    r1 = RestaurantResult(
        id="osm:node:1",
        provider=ProviderInfo(name="openstreetmap"),
        name="رستوران نایب",
        city="Tehran",
        latitude=35.72000,
        longitude=51.41000,
        phone="0211111111",
        tags={"amenity": "restaurant"},
    )
    # Duplicate way 10 meters away with same name, carrying website and address
    r2 = RestaurantResult(
        id="osm:way:2",
        provider=ProviderInfo(name="openstreetmap"),
        name="رستوران نایب",
        name_en="Nayeb Restaurant",
        city="Tehran",
        latitude=35.72005,
        longitude=51.41005,
        website="https://nayeb.ir",
        address="خیابان وزرا",
        tags={"amenity": "restaurant", "building": "yes"},
    )
    # Distinct restaurant 5km away
    r3 = RestaurantResult(
        id="osm:node:3",
        provider=ProviderInfo(name="openstreetmap"),
        name="رستوران نایب شعبه تجریش",
        city="Tehran",
        latitude=35.80000,
        longitude=51.43000,
        tags={"amenity": "restaurant"},
    )

    deduped = deduplicate_restaurants([r1, r2, r3], proximity_meters=50.0)
    assert len(deduped) == 2

    first = deduped[0]
    assert first.name == "رستوران نایب"
    # Merged properties from r2 into r1
    assert first.phone == "0211111111"
    assert first.website == "https://nayeb.ir"
    assert first.address == "خیابان وزرا"
    assert first.name_en == "Nayeb Restaurant"

@pytest.mark.asyncio
async def test_osm_crawler_search_restaurants(mocker):
    crawler = OpenStreetMapCrawler()

    # Mock resolve_boundary
    mocker.patch.object(crawler, "resolve_boundary", return_value=3608188592)

    # Mock Overpass response
    fake_overpass_payload = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 32.65,
                "lon": 51.67,
                "tags": {"name": "رستوران بهارستان", "cuisine": "iranian"},
            },
            {
                "type": "node",
                "id": 2,
                "lat": 32.66,
                "lon": 51.68,
                "tags": {"name": "پیتزا شب", "cuisine": "pizza;fast_food"},
            },
            {
                "type": "way",
                "id": 3,
                "center": {"lat": 32.67, "lon": 51.69},
                "tags": {"name": "رستوران شهرزاد", "name:en": "Shahrzad Restaurant", "cuisine": "iranian"},
            },
        ]
    }
    mocker.patch.object(crawler, "_query_overpass", return_value=fake_overpass_payload)

    # 1. Search all
    query_all = RestaurantSearchQuery(city="Isfahan", limit=10)
    results = await crawler.search_restaurants(query_all)
    assert len(results) == 3

    # 2. Search by cuisine
    query_cuisine = RestaurantSearchQuery(city="Isfahan", cuisine="pizza", limit=10)
    pizza_results = await crawler.search_restaurants(query_cuisine)
    assert len(pizza_results) == 1
    assert pizza_results[0].name == "پیتزا شب"

    # 3. Search by name
    query_name = RestaurantSearchQuery(city="Isfahan", name="شهرزاد", limit=10)
    name_results = await crawler.search_restaurants(query_name)
    assert len(name_results) == 1
    assert name_results[0].name == "رستوران شهرزاد"

    # 4. Pagination
    query_page = RestaurantSearchQuery(city="Isfahan", page=2, limit=2)
    page_results = await crawler.search_restaurants(query_page)
    assert len(page_results) == 1
    assert page_results[0].name == "رستوران شهرزاد"

@pytest.mark.asyncio
async def test_osm_crawler_boundary_resolution(mocker):
    crawler = OpenStreetMapCrawler()

    # Mock Redis cache to return None
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mocker.patch("app.crawlers.openstreetmap.crawler.get_redis_client", return_value=mock_redis)

    # Mock Nominatim response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"osm_type": "relation", "osm_id": 6566419, "display_name": "Isfahan, Iran"}
    ]
    crawler.client.get = AsyncMock(return_value=mock_resp)


    area_id = await crawler.resolve_boundary("Isfahan")
    assert area_id == 3600000000 + 6566419
    mock_redis.set.assert_called_once()
