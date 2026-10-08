"""Geometry tests for corridor projection.

The straight-line cases use a route along the equator meridian or a constant
latitude, where expected distances can be stated exactly, so a regression in
the projection shows up as a number that moved.
"""
import pytest

from app.crawlers.fuelstation.geometry import RouteProjection, largest_gap_km


# A due-south route: constant longitude, stepping down in latitude.
# 1 degree of latitude is about 111.19 km.
SOUTH_ROUTE = [(35.0, 51.0), (34.0, 51.0), (33.0, 51.0)]


def test_projection_requires_two_points():
    with pytest.raises(ValueError):
        RouteProjection([(35.0, 51.0)])


def test_total_length_along_meridian():
    proj = RouteProjection(SOUTH_ROUTE)
    # Two one-degree steps.
    assert proj.total_length_m == pytest.approx(222_400, abs=500)


def test_point_on_route_has_zero_offset():
    """A point lying exactly on the line has no perpendicular offset."""
    proj = RouteProjection(SOUTH_ROUTE)
    result = proj.project(34.5, 51.0)
    assert result["distance_off_route_m"] == pytest.approx(0.0, abs=1.0)
    # 34.5 is half a degree below the route's start at 35.0.
    assert result["distance_along_route_m"] == pytest.approx(55_600, abs=200)


def test_perpendicular_offset_is_measured_from_the_line():
    """A station offset east of the route is measured east-west, not along it."""
    proj = RouteProjection(SOUTH_ROUTE)
    # 0.01 degrees of longitude at this latitude is roughly 0.92 km.
    result = proj.project(34.0, 51.01)
    assert result["distance_off_route_m"] == pytest.approx(920, abs=60)
    # Its distance along the route is unchanged by the eastward offset.
    assert result["distance_along_route_m"] == pytest.approx(111_200, abs=200)


def test_projection_clamps_to_route_ends():
    """A point beyond the route's extent measures from the nearest end."""
    proj = RouteProjection(SOUTH_ROUTE)
    result = proj.project(36.0, 51.0)  # north of the first point
    assert result["distance_along_route_m"] == pytest.approx(0.0, abs=1.0)
    assert result["distance_off_route_m"] == pytest.approx(111_200, abs=500)


def test_bbox_pads_the_route_envelope():
    proj = RouteProjection(SOUTH_ROUTE)
    south, west, north, east = proj.bbox(pad_m=0.0)
    assert south == pytest.approx(33.0)
    assert north == pytest.approx(35.0)
    assert west == pytest.approx(51.0)
    assert east == pytest.approx(51.0)

    padded_south, padded_west, padded_north, padded_east = proj.bbox(pad_m=10_000)
    assert padded_south < 33.0
    assert padded_north > 35.0
    assert padded_west < 51.0
    assert padded_east > 51.0


def test_bbox_covers_a_station_just_inside_the_pad():
    """A station within the pad must fall inside the padded bbox.

    This is the property the Overpass query depends on: if a station inside
    the corridor falls outside the bbox, the query silently misses it.
    """
    proj = RouteProjection(SOUTH_ROUTE)
    radius_m = 1_000
    south, west, north, east = proj.bbox(pad_m=radius_m)

    station_lat, station_lon = 34.0, 51.008  # roughly 740 m east
    projection = proj.project(station_lat, station_lon)
    assert projection["distance_off_route_m"] < radius_m
    assert south <= station_lat <= north
    assert west <= station_lon <= east


def test_stations_project_to_expected_distances():
    """Three stations along a known route get their expected offsets and order."""
    proj = RouteProjection(SOUTH_ROUTE)
    cases = [
        (34.8, 51.0, 0.0, 22_200),    # 0.2 deg down, on the line
        (34.5, 51.005, 460.0, 55_600),  # mid-route, slightly east
        (33.2, 51.0, 0.0, 200_000),    # near the far end, on the line
    ]
    for lat, lon, expected_off, expected_along in cases:
        result = proj.project(lat, lon)
        assert result["distance_off_route_m"] == pytest.approx(expected_off, abs=60)
        assert result["distance_along_route_m"] == pytest.approx(expected_along, abs=400)


# --- largest_gap_km -------------------------------------------------------

def test_gap_between_adjacent_stations():
    stations = [
        {"km_into_trip": 0.0},
        {"km_into_trip": 10.0},
        {"km_into_trip": 100.0},
    ]
    assert largest_gap_km(stations, 120.0) == pytest.approx(90.0)


def test_gap_includes_origin_and_destination_stretches():
    stations = [{"km_into_trip": 30.0}, {"km_into_trip": 40.0}]
    # origin->30 is 30, between is 10, 40->100 is 60.
    assert largest_gap_km(stations, 100.0) == pytest.approx(60.0)


def test_gap_ignores_input_ordering():
    stations = [{"km_into_trip": 100.0}, {"km_into_trip": 10.0}, {"km_into_trip": 40.0}]
    assert largest_gap_km(stations, 120.0) == pytest.approx(60.0)


def test_gap_is_none_without_stations():
    assert largest_gap_km([], 400.0) is None


def test_gap_with_single_station_is_the_larger_end():
    stations = [{"km_into_trip": 20.0}]
    # origin->20 is 20, 20->100 is 80.
    assert largest_gap_km(stations, 100.0) == pytest.approx(80.0)