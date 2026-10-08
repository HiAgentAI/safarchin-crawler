"""Fuel station search along a route.

Composition only. The four stages are separate modules with separate tests:

    resolve endpoints -> route -> bbox + project -> filter, classify, order

This class owns the ordering of those stages and the shape of the response.
It does not attempt cache-merge or provider plurality, which is what
CrawlerOrchestrator is for; see design.md Decision 1 for why that pipeline is
not used here.
"""
import logging
from typing import Any, Dict, List, Optional

from app.crawlers.fuelstation.fuel_types import classify_fuel_type
from app.crawlers.fuelstation.geometry import RouteProjection, largest_gap_km
from app.crawlers.fuelstation.overpass import (
    OverpassRetrievalError,
    extract_station,
    fetch_corridor_stations,
)
from app.crawlers.fuelstation.routing import (
    LocationResolutionError,
    RoutingError,
    fetch_route,
    resolve_endpoint,
)
from app.core.config import settings
from app.schemas.common import ProviderInfo
from app.schemas.fuel_station import (
    FuelStationResult,
    FuelStationSearchQuery,
    FuelType,
)

logger = logging.getLogger(__name__)

DATA_SOURCE = "openstreetmap"


class FuelStationService:
    """Fuel stations located within a corridor of a road route."""

    provider_name = DATA_SOURCE

    async def search(
        self,
        query: FuelStationSearchQuery,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Return stations along the route, ordered by distance into the trip.

        Raises LocationResolutionError, RoutingError or OverpassRetrievalError
        on failure. A successful search with no stations in the corridor
        returns an empty list, which is the only way to get one.
        """
        origin = await resolve_endpoint(query.origin)
        destination = await resolve_endpoint(query.destination)

        route = await fetch_route(origin, destination, use_cache=use_cache)

        projection = RouteProjection(route.coordinates)
        bbox = projection.bbox(pad_m=query.radius_m)

        candidates = await fetch_corridor_stations(bbox)

        results: List[FuelStationResult] = []
        for element in candidates:
            station = extract_station(element)
            if station is None:
                continue

            placement = projection.project(
                station["latitude"], station["longitude"]
            )
            off_route = placement["distance_off_route_m"]
            if off_route > query.radius_m:
                continue

            tags = station["tags"]
            fuel_type = classify_fuel_type(tags, station["name"] or station["name_en"])

            results.append(
                FuelStationResult(
                    id=station["id"],
                    provider=ProviderInfo(
                        name=DATA_SOURCE,
                        deep_link=_deep_link(station["id"]),
                    ),
                    name=station["name"],
                    name_en=station["name_en"],
                    latitude=station["latitude"],
                    longitude=station["longitude"],
                    fuel_type=fuel_type,
                    km_into_trip=placement["distance_along_route_m"] / 1000.0,
                    distance_off_route_m=off_route,
                    address=station["address"],
                    opening_hours=station["opening_hours"],
                    tags=tags,
                )
            )

        # Travel order is the point of the feature, so this is not optional.
        results.sort(key=lambda r: r.km_into_trip)

        if query.fuel_types:
            wanted = set(query.fuel_types)
            results = [r for r in results if r.fuel_type in wanted]

        route_km = route.distance_km
        return {
            "status": "success",
            "total_results": len(results),
            "data_source": DATA_SOURCE,
            "route": {
                "origin": query.origin,
                "destination": query.destination,
                "distance_km": round(route_km, 2),
                "duration_h": round(route.duration_h, 2),
            },
            "corridor_radius_m": query.radius_m,
            "largest_gap_km": _rounded_gap(
                largest_gap_km(
                    [{"km_into_trip": r.km_into_trip} for r in results], route_km
                )
            ),
            "results": results,
        }


def _deep_link(station_id: str) -> Optional[str]:
    """Build an openstreetmap.org URL from an 'osm:node:123' identifier."""
    parts = station_id.split(":")
    if len(parts) == 3 and parts[0] == "osm":
        return f"https://www.openstreetmap.org/{parts[1]}/{parts[2]}"
    return None


def _rounded_gap(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 2)