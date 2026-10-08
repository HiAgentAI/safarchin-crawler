"""Routing and geocoding tests.

All HTTP is stubbed and all route geometry comes from a recorded real OSRM
response, so nothing here depends on a live third-party service.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.crawlers.fuelstation.routing import (
    LocationResolutionError,
    RoutingError,
    fetch_route,
    geocode,
    parse_coordinates,
    resolve_endpoint,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
OSRM_FIXTURE = json.loads(
    (FIXTURES / "osrm_route_tehran_isfahan.json").read_text(encoding="utf-8")
)

TEHRAN = (35.6892, 51.3890)
ISFAHAN = (32.6539, 51.6660)


@pytest.fixture(autouse=True)
def isolated_redis():
    """Keep every test off the real Redis.

    Without this, a geocode cached by an earlier test is read back from the
    live instance and the test passes or fails on leftover state rather than
    on its own behaviour.
    """
    from unittest.mock import patch as _patch

    from tests.conftest import MockRedisClient

    with _patch(
        "app.crawlers.fuelstation.routing.get_redis_client",
        return_value=MockRedisClient(),
    ):
        yield


def _osrm_response():
    """Rebuild a realistic OSRM body from the recorded fixture."""
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": OSRM_FIXTURE["distance_m"],
                "duration": OSRM_FIXTURE["duration_s"],
                "geometry": {
                    "type": "LineString",
                    "coordinates": OSRM_FIXTURE["coordinates"],
                },
            }
        ],
    }


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- Coordinate parsing ---------------------------------------------------

def test_parse_coordinates_accepts_a_pair():
    assert parse_coordinates("35.6892,51.3890") == (35.6892, 51.3890)


def test_parse_coordinates_tolerates_whitespace():
    assert parse_coordinates(" 35.6892 , 51.3890 ") == (35.6892, 51.3890)


@pytest.mark.parametrize(
    "value", ["Tehran", "", "51.3890", "35.6892,51.3890,12", "north,south", "999,999"]
)
def test_parse_coordinates_rejects_non_pairs(value):
    assert parse_coordinates(value) is None


# --- 4.1 Route resolution -------------------------------------------------

async def test_fetch_route_parses_geometry_distance_and_duration():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_osrm_response())

    async with _mock_client(handler) as client:
        route = await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)

    assert route.distance_km == pytest.approx(437.96, abs=0.1)
    assert route.duration_h == pytest.approx(4.82, abs=0.01)
    # GeoJSON is [lon, lat]; the adapter must swap it to (lat, lon).
    assert route.coordinates[0] == pytest.approx((35.688858, 51.389167))
    assert route.origin == TEHRAN
    assert route.destination == ISFAHAN
    assert "/route/v1/driving/" in seen["url"]


async def test_fetch_route_builds_a_driving_url_from_the_pair():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_osrm_response())

    async with _mock_client(handler) as client:
        await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)

    # Coordinates are formatted to fixed precision, lon before lat.
    assert "51.389000,35.689200" in seen["url"]
    assert "51.666000,32.653900" in seen["url"]
    assert "overview=full" in seen["url"]


# --- 4.2 Routing failures raise ------------------------------------------

async def test_no_route_raises_routing_error():
    """OSRM reports failure in the body with HTTP 200, so it must be checked."""

    def handler(request):
        return httpx.Response(200, json={"code": "NoRoute", "message": "No route found"})

    async with _mock_client(handler) as client:
        with pytest.raises(RoutingError) as exc:
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)

    assert "No route" in str(exc.value)


async def test_router_http_error_raises():
    def handler(request):
        return httpx.Response(503, text="unavailable")

    async with _mock_client(handler) as client:
        with pytest.raises(RoutingError) as exc:
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)

    assert "503" in str(exc.value)


async def test_router_unreachable_raises():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    async with _mock_client(handler) as client:
        with pytest.raises(RoutingError) as exc:
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)

    assert "unreachable" in str(exc.value).lower()


async def test_malformed_router_body_raises():
    def handler(request):
        return httpx.Response(200, text="<html>not json</html>")

    async with _mock_client(handler) as client:
        with pytest.raises(RoutingError):
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)


async def test_routing_failure_is_never_an_empty_route():
    """A failure raises; it never resolves to a route with no coordinates."""
    def handler(request):
        return httpx.Response(200, json={"code": "Ok", "routes": []})

    async with _mock_client(handler) as client:
        with pytest.raises(RoutingError):
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)


# --- 4.3 Geocoding, and skipping it for coordinate input ------------------

async def test_resolve_endpoint_returns_coordinates_without_calling_the_network():
    """A supplied coordinate pair must not trigger any HTTP request."""
    def handler(request):
        raise AssertionError("geocoding must not be attempted for coordinates")

    async with _mock_client(handler) as client:
        origin = await resolve_endpoint("35.6892,51.3890", client=client)
        destination = await resolve_endpoint("32.6539,51.6660", client=client)

    assert origin == (35.6892, 51.3890)
    assert destination == (32.6539, 51.6660)


async def test_resolve_endpoint_geocodes_a_city_name():
    def handler(request):
        return httpx.Response(
            200, json=[{"lat": "35.6892", "lon": "51.3890", "osm_id": 123}]
        )

    async with _mock_client(handler) as client:
        result = await resolve_endpoint("Tehran", client=client)

    assert result == (35.6892, 51.3890)


async def test_geocode_falls_back_to_the_free_form_query():
    """Mirrors the OSM adapter: structured query first, free-form as backup."""
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if "city=Tehran" in str(request.url):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"lat": "35.6892", "lon": "51.3890"}])

    async with _mock_client(handler) as client:
        result = await geocode("Tehran", client=client)

    assert result == (35.6892, 51.3890)
    assert len(calls) == 2


async def test_geocode_caches_in_redis(mock_redis):
    """A repeat lookup is served from Redis without a second HTTP request."""
    hits = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(200, json=[{"lat": "35.6892", "lon": "51.3890"}])

    with patch("app.crawlers.fuelstation.routing.get_redis_client", return_value=mock_redis):
        async with _mock_client(handler) as client:
            first = await geocode("Tehran", client=client)
            second = await geocode("Tehran", client=client)

    assert first == second == (35.6892, 51.3890)
    assert len(hits) == 1, "second lookup should have been served from cache"


# --- 4.4 Unresolvable locations raise ------------------------------------

async def test_unknown_city_raises_location_error():
    def handler(request):
        return httpx.Response(200, json=[])

    async with _mock_client(handler) as client:
        with pytest.raises(LocationResolutionError) as exc:
            await geocode("Atlantis", client=client)

    assert "Atlantis" in str(exc.value)


async def test_empty_location_name_raises():
    async with _mock_client(lambda r: httpx.Response(200, json=[])) as client:
        with pytest.raises(LocationResolutionError):
            await geocode("   ", client=client)


async def test_nominatim_http_failure_raises_rather_than_returning_empty():
    def handler(request):
        return httpx.Response(500, text="boom")

    async with _mock_client(handler) as client:
        with pytest.raises(LocationResolutionError):
            await geocode("Tehran", client=client)


async def test_result_without_coordinates_is_skipped_not_crashed():
    def handler(request):
        return httpx.Response(200, json=[{"display_name": "Tehran"}])

    async with _mock_client(handler) as client:
        with pytest.raises(LocationResolutionError):
            await geocode("Tehran", client=client)


# --- 4.5 Route caching ----------------------------------------------------

async def test_route_is_cached_by_origin_destination_pair(mock_redis):
    hits = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(200, json=_osrm_response())

    with patch("app.crawlers.fuelstation.routing.get_redis_client", return_value=mock_redis):
        async with _mock_client(handler) as client:
            first = await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=True)
            second = await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=True)

    assert len(hits) == 1, "second route request should have been served from cache"
    assert second.distance_km == first.distance_km
    assert second.duration_h == first.duration_h
    assert len(second.coordinates) == len(first.coordinates)
    assert second.coordinates[0] == first.coordinates[0]


async def test_different_pairs_are_cached_separately(mock_redis):
    hits = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(200, json=_osrm_response())

    with patch("app.crawlers.fuelstation.routing.get_redis_client", return_value=mock_redis):
        async with _mock_client(handler) as client:
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=True)
            await fetch_route(ISFAHAN, TEHRAN, client=client, use_cache=True)

    assert len(hits) == 2, "reversed endpoints are a different route"


async def test_cache_can_be_bypassed(mock_redis):
    hits = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(200, json=_osrm_response())

    with patch("app.crawlers.fuelstation.routing.get_redis_client", return_value=mock_redis):
        async with _mock_client(handler) as client:
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)
            await fetch_route(TEHRAN, ISFAHAN, client=client, use_cache=False)

    assert len(hits) == 2