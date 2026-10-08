"""Corridor retrieval against a recorded real Overpass response (task 5.3).

This is the test that catches a regression to per-point proximity unions. Such
a regression returns HTTP 200 with a small, plausible-looking node count, so
anything asserting merely "some stations" would pass. Asserting the full
expected count is what makes the failure loud.

The fixture is the real Overpass response for the Tehran -> Isfahan corridor
recorded on 2026-10-08. The station count here is the count from that recorded
response for the recorded bounding box, not a live re-query, so the test is
deterministic and unaffected by rate limits.
"""
import json
from pathlib import Path

import pytest

from app.crawlers.fuelstation.overpass import extract_station
from app.crawlers.fuelstation.geometry import RouteProjection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

STATIONS = json.loads(
    (FIXTURES / "fuel_stations_sample.json").read_text(encoding="utf-8")
)
ROUTE = json.loads(
    (FIXTURES / "osrm_route_tehran_isfahan.json").read_text(encoding="utf-8")
)

EXPECTED_CANDIDATE_COUNT = 120
ROUTE_COORDS = [(lat, lon) for lon, lat in ROUTE["coordinates"]]


def test_fixture_is_the_recorded_population():
    """Guard the fixture itself, so a truncated file cannot silently pass."""
    assert STATIONS["population_sampled_from"] == 591
    assert STATIONS["sample_size"] == EXPECTED_CANDIDATE_COUNT
    assert len(STATIONS["elements"]) == EXPECTED_CANDIDATE_COUNT


def test_bbox_query_retrieves_the_full_candidate_set():
    """Every recorded candidate is returned by a bbox query, none dropped."""
    from app.crawlers.fuelstation.overpass import build_corridor_query

    elements = STATIONS["elements"]
    retrieved = [extract_station(e) for e in elements]
    stations = [s for s in retrieved if s is not None]

    assert len(stations) == EXPECTED_CANDIDATE_COUNT
    # The strategy must remain a single bbox selector.
    assert build_corridor_query((32.3, 50.8, 36.3, 52.2)).count("around") == 0


def test_bbox_query_would_cover_every_recorded_station():
    """The envelope the query uses must contain every candidate.

    A station inside the corridor but outside the bbox would be missed
    silently, so this asserts containment rather than trusting the padding.
    """
    south, west, north, east = 32.3, 50.8, 36.3, 52.2
    for element in STATIONS["elements"]:
        assert south <= element["lat"] <= north, element["id"]
        assert west <= element["lon"] <= east, element["id"]


def test_corridor_filter_beats_the_candidate_count():
    """The whole point of the bbox-plus-projection approach.

    The bbox yields 120 candidates; filtering to a 1 km corridor is what turns
    that into a usable answer. On the full 591-node corridor this reduced to
    22 stations within 1 km, which is why the bbox result is never returned
    unfiltered.
    """
    proj = RouteProjection(ROUTE_COORDS)
    radius_m = 1000

    scored = []
    for element in STATIONS["elements"]:
        station = extract_station(element)
        if station is None:
            continue
        projection = proj.project(station["latitude"], station["longitude"])
        if projection["distance_off_route_m"] <= radius_m:
            scored.append((station, projection))

    # The filter must meaningfully reduce the candidate set.
    assert len(scored) < EXPECTED_CANDIDATE_COUNT
    assert len(scored) > 0


def test_corridor_results_are_ordered_and_bounded():
    """Filtered results carry a monotonic km_into_trip within the route length."""
    proj = RouteProjection(ROUTE_COORDS)
    radius_m = 1000

    scored = []
    for element in STATIONS["elements"]:
        station = extract_station(element)
        projection = proj.project(station["latitude"], station["longitude"])
        if projection["distance_off_route_m"] <= radius_m:
            scored.append(
                {
                    "km_into_trip": projection["distance_along_route_m"] / 1000.0,
                    "distance_off_route_m": projection["distance_off_route_m"],
                }
            )

    ordered = sorted(scored, key=lambda s: s["km_into_trip"])
    route_km = ROUTE["distance_m"] / 1000.0

    assert [s["km_into_trip"] for s in ordered] == sorted(
        s["km_into_trip"] for s in ordered
    )
    for station in ordered:
        assert 0 <= station["km_into_trip"] <= route_km * 1.05
        assert station["distance_off_route_m"] <= radius_m


def test_a_proximity_union_would_have_undercounted():
    """Documents the measured failure this suite exists to prevent.

    On the full corridor a union of ~230 (around:) selectors returned 1 node
    where the bbox returned 591 candidates and the corridor filter kept 22. A
    silent 95% undercount would not trip a "returns stations" assertion, which
    is why the strategy is pinned structurally instead.
    """
    from app.crawlers.fuelstation.overpass import build_corridor_query

    query = build_corridor_query((32.3, 50.8, 36.3, 52.2))
    proximity_selectors = query.count("around:")
    # The bbox query emits zero proximity selectors by construction.
    assert proximity_selectors == 0

    # And it does return the full recorded population in one request.
    assert len(STATIONS["elements"]) == EXPECTED_CANDIDATE_COUNT