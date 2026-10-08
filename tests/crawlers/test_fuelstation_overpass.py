"""Overpass retrieval tests (tasks 5.1 and 5.2).

The strategy assertions here are the guard against a silent regression to
per-point proximity unions, which measured 1 node instead of 22 on the
Tehran -> Isfahan corridor while returning HTTP 200.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.crawlers.fuelstation.overpass import (
    OverpassRetrievalError,
    build_corridor_query,
    extract_station,
    fetch_corridor_stations,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = json.loads(
    (FIXTURES / "fuel_stations_sample.json").read_text(encoding="utf-8")
)

BBOX = (32.3, 50.8, 36.3, 52.2)


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- 5.1 Query shape ------------------------------------------------------

def test_query_is_a_single_bounding_box_selector():
    """One bbox selector, not a union of per-point proximity lookups."""
    query = build_corridor_query(BBOX)
    assert 'node["amenity"="fuel"]' in query
    assert "around:" not in query
    assert query.count("node[") == 1, "must emit exactly one node selector"


def test_query_does_not_repeat_proximity_selectors():
    """The measured failure mode: ~230 (around:) terms returning 1 node."""
    query = build_corridor_query(BBOX)
    assert query.count("around") == 0
    # One statement terminator per line, and exactly three statements:
    # the settings header, the single selector, and the output clause.
    assert query.count(";") == 3


def test_query_contains_the_bbox_bounds():
    query = build_corridor_query((32.3, 50.8, 36.3, 52.2))
    assert "32.300000,50.800000,36.300000,52.200000" in query


def test_query_requests_element_bodies():
    query = build_corridor_query(BBOX)
    assert "out body" in query


def test_query_uses_a_timeout():
    query = build_corridor_query(BBOX)
    assert "timeout:" in query


# --- Mirror rotation and failure (5.2) -----------------------------------

async def test_returns_elements_from_a_working_mirror():
    body = {"elements": SAMPLE["elements"]}

    def handler(request):
        return httpx.Response(200, json=body)

    async with _mock_client(handler) as client:
        elements = await fetch_corridor_stations(
            BBOX, client=client, mirrors=["https://mirror-a"]
        )

    assert len(elements) == len(SAMPLE["elements"])


async def test_rotates_to_the_next_mirror_when_one_rate_limits():
    """429 on the first mirror must fall through to the second."""
    attempted = []

    def handler(request):
        attempted.append(str(request.url))
        if "mirror-a" in str(request.url):
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, json={"elements": [{"type": "node", "id": 1}]})

    async with _mock_client(handler) as client:
        elements = await fetch_corridor_stations(
            BBOX, client=client, mirrors=["https://mirror-a", "https://mirror-b"]
        )

    assert len(attempted) == 2
    assert len(elements) == 1


async def test_rejects_a_200_that_carries_html_instead_of_json():
    """Some deployments answer rate limits with an HTML body under a 200."""
    def handler(request):
        if "mirror-a" in str(request.url):
            return httpx.Response(200, text="<html><body>Rate limited</body></html>")
        return httpx.Response(200, json={"elements": []})

    async with _mock_client(handler) as client:
        elements = await fetch_corridor_stations(
            BBOX, client=client, mirrors=["https://mirror-a", "https://mirror-b"]
        )

    assert elements == []


async def test_all_mirrors_failing_raises_rather_than_returning_empty():
    """Spec: total mirror failure must surface as an error, not an empty list."""

    def handler(request):
        return httpx.Response(429, text="Too Many Requests")

    async with _mock_client(handler) as client:
        with pytest.raises(OverpassRetrievalError):
            await fetch_corridor_stations(
                BBOX,
                client=client,
                mirrors=["https://mirror-a", "https://mirror-b", "https://mirror-c"],
            )


async def test_transport_failure_on_every_mirror_raises():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    async with _mock_client(handler) as client:
        with pytest.raises(OverpassRetrievalError):
            await fetch_corridor_stations(
                BBOX, client=client, mirrors=["https://mirror-a"]
            )


async def test_error_names_the_retrieval_failure():
    def handler(request):
        return httpx.Response(503, text="unavailable")

    async with _mock_client(handler) as client:
        with pytest.raises(OverpassRetrievalError) as exc:
            await fetch_corridor_stations(BBOX, client=client, mirrors=["https://m"])

    assert "mirror" in str(exc.value).lower()


async def test_successful_empty_response_is_not_an_error():
    """A valid response with zero elements is a real answer, not a failure."""

    def handler(request):
        return httpx.Response(200, json={"elements": []})

    async with _mock_client(handler) as client:
        elements = await fetch_corridor_stations(
            BBOX, client=client, mirrors=["https://mirror-a"]
        )

    assert elements == []


async def test_default_mirrors_are_the_shared_osm_mirror_list():
    """Mirror rotation must reuse the list the OSM adapter already proved."""
    from app.crawlers.openstreetmap.crawler import DEFAULT_OVERPASS_MIRRORS

    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"elements": []})

    async with _mock_client(handler) as client:
        await fetch_corridor_stations(BBOX, client=client)

    assert len(seen) == 1
    assert any(m in seen[0] for m in DEFAULT_OVERPASS_MIRRORS)


# --- 5.3 Station extraction ----------------------------------------------

def test_extracts_a_node_into_station_fields():
    station = extract_station(SAMPLE["elements"][0])
    assert station is not None
    assert station["id"].startswith("osm:node:")
    assert isinstance(station["latitude"], float)
    assert isinstance(station["longitude"], float)
    assert station["tags"]
    assert station["name"] or station["name_en"]


def test_station_id_is_stable_across_extractions():
    """Spec: identifier derived from OSM element, unchanged between searches."""
    first = extract_station(SAMPLE["elements"][0])
    second = extract_station(SAMPLE["elements"][0])
    assert first["id"] == second["id"]


def test_skips_elements_without_a_position():
    assert extract_station({"type": "node", "id": 1, "tags": {}}) is None


def test_skips_non_node_elements():
    assert extract_station({"type": "way", "id": 1, "lat": 35.0, "lon": 51.0}) is None


def test_tolerates_a_station_with_no_tags():
    station = extract_station({"type": "node", "id": 7, "lat": 35.0, "lon": 51.0})
    assert station is not None
    assert station["tags"] == {}
    assert station["name"] is None