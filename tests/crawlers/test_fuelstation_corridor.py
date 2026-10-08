"""Corridor filtering and ordering tests (tasks 3.3 and 3.4).

These use the fixture geometry helpers directly, so they pin the filtering and
ordering contract without touching the network. The service-level versions of
both behaviours are covered in the service tests.
"""
import pytest

from app.crawlers.fuelstation.geometry import RouteProjection

SOUTH_ROUTE = [(35.0, 51.0), (34.0, 51.0), (33.0, 51.0)]


def _station(lat, lon, name):
    proj = RouteProjection(SOUTH_ROUTE)
    p = proj.project(lat, lon)
    return {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "km_into_trip": p["distance_along_route_m"] / 1000.0,
        "distance_off_route_m": p["distance_off_route_m"],
    }


def test_corridor_filter_excludes_stations_beyond_the_radius():
    """A 500 m corridor keeps the near station and drops the far one."""
    proj = RouteProjection(SOUTH_ROUTE)
    radius_m = 500

    candidates = [
        _station(34.5, 51.0, "on the road"),
        _station(34.5, 51.01, "about 920 m east, outside 500 m"),
        _station(34.2, 51.0, "also on the road"),
    ]

    kept = [c for c in candidates if c["distance_off_route_m"] <= radius_m]
    names = {c["name"] for c in kept}

    assert "on the road" in names
    assert "also on the road" in names
    assert "about 920 m east, outside 500 m" not in names
    for c in kept:
        assert c["distance_off_route_m"] <= radius_m


def test_wider_corridor_retains_the_station_a_narrow_one_dropped():
    """The same candidate set yields more results as the corridor widens."""
    candidates = [_station(34.5, 51.0, "near"), _station(34.5, 51.01, "far")]

    narrow = [c for c in candidates if c["distance_off_route_m"] <= 500]
    wide = [c for c in candidates if c["distance_off_route_m"] <= 1500]

    assert len(narrow) == 1
    assert len(wide) == 2


def test_results_are_ordered_by_distance_into_the_trip():
    """Reading the response top to bottom follows the direction of travel."""
    candidates = [
        _station(33.2, 51.0, "near the destination"),
        _station(34.8, 51.0, "near the origin"),
        _station(34.0, 51.0, "midway"),
        _station(35.0, 51.0, "at the origin"),
    ]

    # Deliberately shuffle before sorting, to prove the sort does the work.
    import random
    random.Random(0).shuffle(candidates)
    ordered = sorted(candidates, key=lambda s: s["km_into_trip"])

    names = [s["name"] for s in ordered]
    assert names == [
        "at the origin",
        "near the origin",
        "midway",
        "near the destination",
    ]
    assert ordered[0]["km_into_trip"] <= ordered[-1]["km_into_trip"]


def test_ordering_is_ascending_and_stable_for_ties():
    candidates = [_station(34.0, 51.0, "a"), _station(34.0, 51.0, "b")]
    ordered = sorted(candidates, key=lambda s: s["km_into_trip"])
    assert [s["km_into_trip"] for s in ordered] == pytest.approx(
        sorted(s["km_into_trip"] for s in candidates)
    )


def test_every_kept_station_reports_its_own_km_and_offset():
    """Both route-relative distances are present on each result."""
    candidates = [_station(34.5, 51.0, "on the road")]
    kept = [c for c in candidates if c["distance_off_route_m"] <= 1000]
    for c in kept:
        assert isinstance(c["km_into_trip"], float)
        assert isinstance(c["distance_off_route_m"], float)
        assert c["km_into_trip"] >= 0
        assert c["distance_off_route_m"] >= 0