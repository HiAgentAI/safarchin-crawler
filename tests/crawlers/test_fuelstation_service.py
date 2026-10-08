"""Service-level tests: envelope, filtering, and failure surfacing (6.1, 6.2)."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.fuelstation.crawler import FuelStationService
from app.crawlers.fuelstation.overpass import OverpassRetrievalError
from app.crawlers.fuelstation.routing import (
    LocationResolutionError,
    RoutingError,
    fetch_route,
    resolve_endpoint,
)
from app.schemas.fuel_station import FuelStationSearchQuery, FuelType

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


def _patched(elements=None, route_mock=None):
    """Context managers patching every network stage of the service."""
    from contextlib import ExitStack

    elements = STATIONS["elements"] if elements is None else elements
    route_mock = route_mock or _fake_route()
    stack = ExitStack()
    stack.enter_context(
        patch(
            "app.crawlers.fuelstation.crawler.resolve_endpoint",
            new=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        )
    )
    stack.enter_context(
        patch(
            "app.crawlers.fuelstation.crawler.fetch_route",
            new=route_mock,
        )
    )
    stack.enter_context(
        patch(
            "app.crawlers.fuelstation.crawler.fetch_corridor_stations",
            new=AsyncMock(return_value=elements),
        )
    )
    return stack


QUERY = FuelStationSearchQuery(
    origin="35.6892,51.3890", destination="32.6539,51.6660", radius_m=1000
)


def _dicts(payload):
    """Results as plain dicts, matching what the endpoint serialises."""
    return [r if isinstance(r, dict) else r.model_dump() for r in payload["results"]]


# --- 6.1 Envelope ---------------------------------------------------------

async def test_envelope_reports_route_context_and_source():
    with _patched():
        payload = await FuelStationService().search(QUERY)

    assert payload["status"] == "success"
    assert payload["data_source"] == "openstreetmap"
    assert payload["route"]["distance_km"] == pytest.approx(437.96, abs=0.1)
    assert payload["route"]["duration_h"] == pytest.approx(4.82, abs=0.01)
    assert payload["corridor_radius_m"] == 1000
    assert payload["total_results"] == len(payload["results"])


async def test_envelope_reports_largest_gap():
    """Spec: the longest station-free stretch must be reported."""
    with _patched():
        payload = await FuelStationService().search(QUERY)

    assert payload["largest_gap_km"] is not None
    assert payload["largest_gap_km"] > 0
    assert payload["total_results"] > 0


async def test_gap_matches_the_gap_between_consecutive_stations():
    """The reported gap equals the largest spacing in the ordered results."""
    with _patched():
        payload = await FuelStationService().search(QUERY)

    positions = [r["km_into_trip"] for r in _dicts(payload)]
    route_km = payload["route"]["distance_km"]

    gaps = [positions[0]]
    for a, b in zip(positions, positions[1:]):
        gaps.append(b - a)
    gaps.append(max(0.0, route_km - positions[-1]))

    assert payload["largest_gap_km"] == pytest.approx(max(gaps), abs=0.02)


async def test_gap_is_none_when_no_stations_are_returned():
    with _patched(elements=[]):
        payload = await FuelStationService().search(QUERY)

    assert payload["total_results"] == 0
    assert payload["results"] == []
    assert payload["largest_gap_km"] is None


async def test_payload_carries_no_price_field():
    with _patched():
        payload = await FuelStationService().search(QUERY)

    def walk(node):
        if hasattr(node, "model_dump"):
            node = node.model_dump()
        if isinstance(node, dict):
            for k, v in node.items():
                assert "price" not in k.lower(), f"unexpected price key: {k}"
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)


# --- Ordering -------------------------------------------------------------

async def test_results_are_ordered_by_km_into_trip():
    with _patched():
        payload = await FuelStationService().search(QUERY)

    positions = [r["km_into_trip"] for r in _dicts(payload)]
    assert positions == sorted(positions)


async def test_every_result_respects_the_corridor_radius():
    with _patched():
        payload = await FuelStationService().search(QUERY)

    for result in _dicts(payload):
        assert result["distance_off_route_m"] <= QUERY.radius_m


async def test_narrower_corridor_returns_fewer_stations():
    with _patched():
        wide = await FuelStationService().search(
            FuelStationSearchQuery(
                origin="35.6892,51.3890",
                destination="32.6539,51.6660",
                radius_m=3000,
            )
        )
    with _patched():
        narrow = await FuelStationService().search(
            FuelStationSearchQuery(
                origin="35.6892,51.3890",
                destination="32.6539,51.6660",
                radius_m=500,
            )
        )

    assert narrow["total_results"] <= wide["total_results"]


# --- 6.2 Fuel type filtering ---------------------------------------------

async def test_petrol_diesel_filter_excludes_cng_lpg_and_unknown():
    query = FuelStationSearchQuery(
        origin="35.6892,51.3890",
        destination="32.6539,51.6660",
        radius_m=3000,
        fuel_types=[FuelType.PETROL, FuelType.DIESEL],
    )
    with _patched():
        payload = await FuelStationService().search(query)

    returned = {r["fuel_type"] for r in _dicts(payload)}
    assert returned
    assert returned <= {FuelType.PETROL.value, FuelType.DIESEL.value}


async def test_filter_excludes_unknown_stations():
    query = FuelStationSearchQuery(
        origin="35.6892,51.3890",
        destination="32.6539,51.6660",
        radius_m=3000,
        fuel_types=[FuelType.PETROL],
    )
    with _patched():
        payload = await FuelStationService().search(query)

    assert all(r["fuel_type"] == "petrol" for r in _dicts(payload))


async def test_cng_filter_returns_only_cng():
    query = FuelStationSearchQuery(
        origin="35.6892,51.3890",
        destination="32.6539,51.6660",
        radius_m=3000,
        fuel_types=[FuelType.CNG],
    )
    with _patched():
        payload = await FuelStationService().search(query)

    assert all(r["fuel_type"] == "cng" for r in _dicts(payload))


async def test_no_filter_returns_every_fuel_type():
    """Spec: filtering is a parameter, not a source-side exclusion."""
    with _patched():
        payload = await FuelStationService().search(
            FuelStationSearchQuery(
                origin="35.6892,51.3890",
                destination="32.6539,51.6660",
                radius_m=3000,
            )
        )

    returned = {r["fuel_type"] for r in _dicts(payload)}
    assert FuelType.CNG.value in returned
    assert FuelType.PETROL.value in returned


async def test_gap_is_recomputed_after_filtering():
    """Filtering changes the spacing, so the gap must reflect what was returned."""
    base = FuelStationSearchQuery(
        origin="35.6892,51.3890", destination="32.6539,51.6660", radius_m=3000
    )
    petrol_only = FuelStationSearchQuery(
        origin="35.6892,51.3890",
        destination="32.6539,51.6660",
        radius_m=3000,
        fuel_types=[FuelType.PETROL],
    )
    with _patched():
        unfiltered = await FuelStationService().search(base)
    with _patched():
        filtered = await FuelStationService().search(petrol_only)

    assert filtered["total_results"] <= unfiltered["total_results"]
    if filtered["total_results"] < unfiltered["total_results"]:
        assert filtered["largest_gap_km"] >= unfiltered["largest_gap_km"]


# --- Result identity ------------------------------------------------------

async def test_station_ids_are_stable_across_searches():
    with _patched():
        first = await FuelStationService().search(QUERY)
    with _patched():
        second = await FuelStationService().search(QUERY)

    first_ids = [r["id"] for r in _dicts(first)]
    second_ids = [r["id"] for r in _dicts(second)]
    assert first_ids == second_ids
    assert all(i.startswith("osm:node:") for i in first_ids)
    assert all(r["provider"]["name"] == "openstreetmap" for r in _dicts(first))


# --- 6.4 Failure surfaces ------------------------------------------------

async def test_routing_failure_propagates():
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch(
            "app.crawlers.fuelstation.crawler.resolve_endpoint",
            new=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        )
    )
    stack.enter_context(
        patch(
            "app.crawlers.fuelstation.crawler.fetch_route",
            new=AsyncMock(side_effect=RoutingError("No drivable route available")),
        )
    )
    with stack:
        with pytest.raises(RoutingError):
            await FuelStationService().search(QUERY)


async def test_location_resolution_failure_propagates():
    with patch(
        "app.crawlers.fuelstation.crawler.resolve_endpoint",
        new=AsyncMock(side_effect=LocationResolutionError("unknown city")),
    ):
        with pytest.raises(LocationResolutionError):
            await FuelStationService().search(QUERY)


async def test_overpass_failure_propagates_and_is_never_an_empty_list():
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch(
            "app.crawlers.fuelstation.crawler.resolve_endpoint",
            new=AsyncMock(side_effect=[TEHRAN, ISFAHAN]),
        )
    )
    stack.enter_context(patch("app.crawlers.fuelstation.crawler.fetch_route", new=_fake_route()))
    stack.enter_context(
        patch(
            "app.crawlers.fuelstation.crawler.fetch_corridor_stations",
            new=AsyncMock(side_effect=OverpassRetrievalError("all mirrors failed")),
        )
    )
    with stack:
        with pytest.raises(OverpassRetrievalError):
            await FuelStationService().search(QUERY)


async def test_successful_empty_corridor_is_not_an_error():
    """Only a genuinely empty corridor yields an empty list."""
    with _patched(elements=[]):
        payload = await FuelStationService().search(QUERY)
    assert payload["status"] == "success"
    assert payload["total_results"] == 0