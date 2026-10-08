"""Route geometry helpers for corridor search.

Distances are computed in a local projection anchored at the route's mean
latitude. Over the few hundred kilometres an Iranian intercity route covers,
equirectangular distortion stays well under a metre, and it avoids pulling in
a geodesy dependency for what is a near-linear calculation. The existing
``haversine_distance`` in the OSM normaliser stays the right tool for the
short-range proximity check in deduplication.
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

EARTH_RADIUS_M = 6371000.0
_DEGREES_TO_RADIANS = math.pi / 180.0

Point = Tuple[float, float]  # (lat, lon)


class RouteProjection:
    """A route geometry prepared for repeated point-to-line projection.

    Building this once per search keeps the per-station cost linear in the
    number of route segments rather than repeating the latitude setup for
    every candidate.
    """

    def __init__(self, coordinates: Sequence[Point]):
        if len(coordinates) < 2:
            raise ValueError("A route needs at least two coordinates to project onto")
        self._points: List[Tuple[float, float]] = [
            (float(lat), float(lon)) for lat, lon in coordinates
        ]
        self._mean_lat = sum(p[0] for p in self._points) / len(self._points)
        self._lon_scale = EARTH_RADIUS_M * _DEGREES_TO_RADIANS * math.cos(
            self._mean_lat * _DEGREES_TO_RADIANS
        )
        self._lat_scale = EARTH_RADIUS_M * _DEGREES_TO_RADIANS

        # Precompute planar coordinates and cumulative distance along the route.
        self._projected: List[Tuple[float, float]] = [
            (lon * self._lon_scale, lat * self._lat_scale)
            for lat, lon in self._points
        ]
        self._cumulative: List[float] = [0.0]
        for i in range(1, len(self._projected)):
            ax, ay = self._projected[i - 1]
            bx, by = self._projected[i]
            self._cumulative.append(
                self._cumulative[-1] + math.hypot(bx - ax, by - ay)
            )

    @property
    def total_length_m(self) -> float:
        return self._cumulative[-1]

    def bbox(self, pad_m: float) -> Tuple[float, float, float, float]:
        """Bounding box as (south, west, north, east), padded by pad_m metres.

        This is the envelope a single Overpass bounding-box query needs to
        cover every station within pad_m of the route.
        """
        pad_lat = pad_m / self._lat_scale
        pad_lon = pad_m / self._lon_scale
        lats = [p[0] for p in self._points]
        lons = [p[1] for p in self._points]
        return (
            min(lats) - pad_lat,
            min(lons) - pad_lon,
            max(lats) + pad_lat,
            max(lons) + pad_lon,
        )

    def project(self, lat: float, lon: float) -> Dict[str, float]:
        """Project a point onto the route.

        Returns the perpendicular distance from the route line and the distance
        travelled along the route to the closest point on it.
        """
        px = lon * self._lon_scale
        py = lat * self._lat_scale

        best_off = float("inf")
        best_along = 0.0

        for i in range(len(self._projected) - 1):
            ax, ay = self._projected[i]
            bx, by = self._projected[i + 1]
            dx, dy = bx - ax, by - ay
            length_squared = dx * dx + dy * dy

            if length_squared == 0.0:
                # Degenerate segment; treat as a point.
                closest_x, closest_y = ax, ay
                segment_offset = 0.0
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / length_squared
                # Clamp so the closest point stays within the segment.
                t = max(0.0, min(1.0, t))
                closest_x = ax + t * dx
                closest_y = ay + t * dy
                segment_offset = math.hypot(px - closest_x, py - closest_y)

            if segment_offset < best_off:
                best_off = segment_offset
                along = (
                    self._cumulative[i]
                    + math.hypot(closest_x - ax, closest_y - ay)
                )
                best_along = along

        return {
            "distance_off_route_m": best_off,
            "distance_along_route_m": best_along,
        }


def largest_gap_km(
    stations: Sequence[Dict[str, float]],
    total_route_km: float,
) -> Optional[float]:
    """Longest stretch of route with no station, in km.

    ``stations`` must be ordered by distance into the trip. Gaps are measured
    between consecutive stations, including from the origin to the first
    station and from the last station to the destination, because a caller
    driving the route cares about those too.

    Returns None when there are no stations at all, since an unmeasured gap
    should not be reported as a number.
    """
    if not stations:
        return None

    positions = sorted(float(s["km_into_trip"]) for s in stations)
    gaps = []
    # Origin to first station.
    gaps.append(positions[0])
    # Between consecutive stations.
    for previous, current in zip(positions, positions[1:]):
        gaps.append(current - previous)
    # Last station to destination.
    gaps.append(max(0.0, total_route_km - positions[-1]))

    return max(gaps)