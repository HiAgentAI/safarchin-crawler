import pytest
from app.schemas.restaurant import RestaurantSearchQuery, RestaurantResult
from app.schemas.common import ProviderInfo

def test_restaurant_search_query():
    q = RestaurantSearchQuery(city="Tehran", cuisine="iranian", page=1, limit=20)
    assert q.city == "Tehran"
    assert q.cuisine == "iranian"
    assert q.page == 1
    assert q.limit == 20
    assert q.providers is None

def test_restaurant_result_schema():
    res = RestaurantResult(
        id="osm:node:123456",
        provider=ProviderInfo(name="openstreetmap"),
        name="رستوران سنتی",
        name_en="Traditional Restaurant",
        city="Isfahan",
        cuisine="iranian",
        amenity="restaurant",
        latitude=32.65,
        longitude=51.67,
        address="خیابان چهارباغ",
        phone="03131234567",
        website="https://example.com",
        opening_hours="12:00-23:00",
        last_edited="2026-05-01T10:00:00Z",
        tags={"amenity": "restaurant", "cuisine": "iranian"},
    )
    dumped = res.model_dump()
    assert dumped["id"] == "osm:node:123456"
    assert dumped["provider"]["name"] == "openstreetmap"
    assert dumped["name"] == "رستوران سنتی"
    assert dumped["latitude"] == 32.65
    assert dumped["tags"]["cuisine"] == "iranian"
