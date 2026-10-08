"""Endpoint tests for GET /api/v1/fuel-stations (tasks 6.3 and 6.4).

Every network stage is stubbed, so these assert response shape and status
codes without depending on OSRM, Nominatim, or Overpass being available.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.fuelstation.overpass import OverpassRetrievalError
from app.crawlers.fuelstation.routing import (
    LocationResolutionError,
    RoutingError,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
STATIONS = json.loads(
    (FIXTURES / "fuel_stations_sample.json").read_text(encoding="utf-8")
)
ROUTE = json.loads(
    (FIXTURES / "osrm_route_tehran_isfahan.json").read_text(encoding="utf-8")
)
ROUTE_COORDS = [(lat, lon) for lon, lat in ROUTE["coordinates"]]

TEHRAN = (35.6892, 51.3890)
ISFAHAN = (32.6539, 51.6660)

ENDPOINT = "/api/v1/fuel-stations"
BASE_PARAMS = {
    "origin": "35.6892,51.3890",
    "destination": "32.6539,51.6660",
}


def _fake_route():
    return AsyncMock(
        return_value=type(
            "R",
            (),
            {
                "origin": TEHRAN,
                "destination": ISFAHAN,
                "coordinates": ROUTE_COORDS,
                "distance_m": ROUTE["distance_m"],
                "duration_s": ROUTE["duration_s"],
                "distance_km": ROUTE["distance_m"] / 1000.0,
                "duration_h": ROUTE["duration_s"] / 3600.0,
            },
        )()
    )


def _coord(value):
    """Parse a 'lat,lon' pair the way the service does, so patching stays honest."""
    parts = str(value).split(",")
    return (float(parts[0]), float(parts[1]))


def _patched(elements=None):
    """Stub every network stage the service reaches for."""
    elements = STATIONS["elements"] if elements is None else elements
    return patch.multiple(
        "app.crawlers.fuelstation.crawler",
        resolve_endpoint=AsyncMock(side_effect=lambda v, *a, **k: _coord(v)),
        fetch_route=_fake_route(),
        fetch_corridor_stations=AsyncMock(return_value=elements),
    )


@pytest.fixture
async def headers(db_session):
    """An active API key header, following the restaurant endpoint pattern."""
    from app.core.security import generate_api_key
    from app.db.models import APIKey

    plain_key, key_hash = generate_api_key()
    db_session.add(
        APIKey(
            key_hash=key_hash,
            client_name="Fuel Station Test Suite",
            tier="enterprise",
            rate_limit_per_min=500,
            is_active=True,
        )
    )
    await db_session.commit()
    return {"X-API-Key": plain_key}


# --- 6.3 Success shape ---------------------------------------------------

async def test_returns_stations_for_a_fixture_backed_route(async_client, headers):
    with _patched():
        resp = await async_client.get(
            ENDPOINT, params={**BASE_PARAMS, "radius_m": 3000}, headers=headers
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["data_source"] == "openstreetmap"
    assert body["total_results"] == len(body["results"])
    assert body["total_results"] > 0
    assert body["route"]["distance_km"] > 0
    assert "largest_gap_km" in body
    assert body["corridor_radius_m"] == 3000


async def test_results_are_ordered_by_km_into_trip(async_client, headers):
    with patch.multiple(
        "app.crawlers.fuelstation.crawler",
        resolve_endpoint=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        fetch_route=_fake_route(),
        fetch_corridor_stations=AsyncMock(return_value=STATIONS["elements"]),
    ):
        resp = await async_client.get(
            ENDPOINT, params={**BASE_PARAMS, "radius_m": 3000}, headers=headers
        )

    assert resp.status_code == 200, resp.text
    positions = [r["km_into_trip"] for r in resp.json()["results"]]
    assert positions == sorted(positions)


async def test_payload_contains_no_price_field(async_client, headers):
    with patch.multiple(
        "app.crawlers.fuelstation.crawler",
        resolve_endpoint=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        fetch_route=_fake_route(),
        fetch_corridor_stations=AsyncMock(return_value=STATIONS["elements"]),
    ):
        resp = await async_client.get(
            ENDPOINT, params={**BASE_PARAMS, "radius_m": 3000}, headers=headers
        )

    body = resp.json()

    def walk(node, path="body"):
        if isinstance(node, dict):
            for k, v in node.items():
                assert "price" not in k.lower(), f"{path}.{k} is a price field"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(body)


async def test_fuel_type_filter_is_applied(async_client, headers):
    with patch.multiple(
        "app.crawlers.fuelstation.crawler",
        resolve_endpoint=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        fetch_route=_fake_route(),
        fetch_corridor_stations=AsyncMock(return_value=STATIONS["elements"]),
    ):
        resp = await async_client.get(
            ENDPOINT,
            params={**BASE_PARAMS, "radius_m": 3000, "fuel_types": "cng"},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    types = {r["fuel_type"] for r in resp.json()["results"]}
    assert types <= {"cng"}


async def test_missing_api_key_is_rejected(async_client):
    resp = await async_client.get(ENDPOINT, params=BASE_PARAMS)
    assert resp.status_code == 401


# --- 6.4 Failures are non-200 --------------------------------------------

async def test_routing_failure_returns_502(async_client, headers):
    with patch.multiple(
        "app.crawlers.fuelstation.crawler",
        resolve_endpoint=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        fetch_route=AsyncMock(side_effect=RoutingError("No drivable route available")),
    ):
        resp = await async_client.get(ENDPOINT, params=BASE_PARAMS, headers=headers)

    assert resp.status_code == 502
    # It must not have reported success with zero results.
    assert resp.json().get("total_results") != 0


async def test_overpass_failure_returns_502(async_client, headers):
    with patch.multiple(
        "app.crawlers.fuelstation.crawler",
        resolve_endpoint=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        fetch_route=_fake_route(),
        fetch_corridor_stations=AsyncMock(
            side_effect=OverpassRetrievalError("all mirrors failed")
        ),
    ):
        resp = await async_client.get(ENDPOINT, params=BASE_PARAMS, headers=headers)

    assert resp.status_code == 502
    assert "results" not in resp.json() or resp.json()["total_results"] != 0


async def test_unresolvable_location_returns_400(async_client, headers):
    with patch.multiple(
        "app.crawlers.fuelstation.crawler",
        resolve_endpoint=AsyncMock(
            side_effect=LocationResolutionError("Could not resolve 'Atlantis'")
        ),
    ):
        resp = await async_client.get(
            ENDPOINT,
            params={"origin": "Atlantis", "destination": "Isfahan"},
            headers=headers,
        )

    assert resp.status_code == 400
    assert "Atlantis" in resp.json()["detail"]


async def test_unknown_fuel_type_returns_400(async_client, headers):
    resp = await async_client.get(
        ENDPOINT, params={**BASE_PARAMS, "fuel_types": "unobtainium"}, headers=headers
    )
    assert resp.status_code == 400
    assert "unobtainium" in resp.json()["detail"]


async def test_radius_above_the_maximum_is_rejected(async_client, headers):
    resp = await async_client.get(
        ENDPOINT, params={**BASE_PARAMS, "radius_m": 99999}, headers=headers
    )
    assert resp.status_code == 422


async def test_endpoint_is_documented_in_openapi(async_client):
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    assert ENDPOINT in resp.json()["paths"]