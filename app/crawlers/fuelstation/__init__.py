"""Fuel stations along a route, from OpenStreetMap and OSRM."""

from app.crawlers.fuelstation.crawler import DATA_SOURCE, FuelStationService
from app.crawlers.fuelstation.fuel_types import classify_fuel_type
from app.crawlers.fuelstation.geometry import RouteProjection, largest_gap_km
from app.crawlers.fuelstation.overpass import (
    OverpassRetrievalError,
    build_corridor_query,
    extract_station,
    fetch_corridor_stations,
)
from app.crawlers.fuelstation.routing import (
    LocationResolutionError,
    RoutingError,
    fetch_route,
    geocode,
    parse_coordinates,
    resolve_endpoint,
)

__all__ = [
    "FuelStationService",
    "DATA_SOURCE",
    "classify_fuel_type",
    "RouteProjection",
    "largest_gap_km",
    "OverpassRetrievalError",
    "build_corridor_query",
    "extract_station",
    "fetch_corridor_stations",
    "RoutingError",
    "LocationResolutionError",
    "fetch_route",
    "geocode",
    "parse_coordinates",
    "resolve_endpoint",
]