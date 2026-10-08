"""Route resolution and geocoding for corridor search.

Two distinct steps, deliberately kept apart:

- **Routing** turns two coordinate pairs into a drivable road geometry. OSRM
  serves Iran correctly, so a standard instance is all that is needed.
- **Geocoding** turns city names into coordinates. Nominatim does this, and
  the OSM adapter already depends on it, so the Redis key convention and TTL
  from there are reused rather than inventing a second cache.

Failures raise. Returning an empty result for a routing or geocoding failure
would make "we could not look" indistinguishable from "there is nothing
there", which is the specific defect this project documents as
KNOWN_ISSUES.md issue 1.
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

USER_AGENT = "SafarchinApp/1.0 (contact@safarchin.ir)"

# Nominatim asks that repeat lookups be cached; 30 days matches the OSM
# adapter's existing boundary cache.
GEOCODE_CACHE_TTL_SECONDS = 2_592_000
GEOCODE_CACHE_PREFIX = "osm:geocode:"

ROUTE_CACHE_PREFIX = "fuel:route:"


class RoutingError(RuntimeError):
    """No drivable route exists, or the router could not be reached."""


class LocationResolutionError(ValueError):
    """A supplied city name could not be resolved to coordinates."""


@dataclass
class Route:
    """A resolved drivable route."""

    origin: Tuple[float, float]  # (lat, lon)
    destination: Tuple[float, float]  # (lat, lon)
    coordinates: List[Tuple[float, float]]  # [(lat, lon), ...]
    distance_m: float
    duration_s: float

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000.0

    @property
    def duration_h(self) -> float:
        return self.duration_s / 3600.0


def parse_coordinates(value: str) -> Optional[Tuple[float, float]]:
    """Parse a 'lat,lon' pair, or return None if the string is not one.

    Detection is by shape rather than by a separate parameter, so a caller
    supplying coordinates never triggers a geocoding request.
    """
    if not value or "," not in value:
        return None
    parts = value.split(",")
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


async def geocode(city: str, client: Optional[httpx.AsyncClient] = None) -> Tuple[float, float]:
    """Resolve a city name to (lat, lon) via Nominatim.

    Raises LocationResolutionError rather than returning None, so an
    unresolvable city is an error and not an empty result.
    """
    normalized = (city or "").strip()
    if not normalized:
        raise LocationResolutionError("Location name is empty")

    cache_key = f"{GEOCODE_CACHE_PREFIX}{normalized.lower()}"

    try:
        redis_client = get_redis_client()
        cached = await redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            return (float(data["lat"]), float(data["lon"]))
    except Exception as e:  # cache is an optimisation, not a dependency
        logger.debug(f"Geocode cache lookup failed for '{normalized}': {e}")

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True)
    try:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        # Structured query first, free-form as the OSM adapter does.
        for params in (
            {"city": normalized, "country": "Iran", "format": "json", "limit": "1"},
            {"q": f"{normalized}, Iran", "format": "json", "limit": "1"},
        ):
            try:
                response = await http.get(
                    settings.NOMINATIM_URL, params=params, headers=headers
                )
                if response.status_code != 200:
                    continue
                data = response.json()
            except Exception as e:
                logger.debug(f"Nominatim request failed for '{normalized}': {e}")
                continue

            if not data or not isinstance(data, list):
                continue

            first = data[0]
            try:
                lat = float(first["lat"])
                lon = float(first["lon"])
            except (KeyError, TypeError, ValueError):
                continue

            try:
                redis_client = get_redis_client()
                await redis_client.set(
                    cache_key,
                    json.dumps({"lat": lat, "lon": lon}),
                    ex=GEOCODE_CACHE_TTL_SECONDS,
                )
            except Exception as e:
                logger.debug(f"Geocode cache write failed for '{normalized}': {e}")

            return (lat, lon)
    finally:
        if owns_client:
            await http.aclose()

    raise LocationResolutionError(
        f"Could not resolve location '{normalized}' to coordinates"
    )


async def resolve_endpoint(value: str, client: Optional[httpx.AsyncClient] = None) -> Tuple[float, float]:
    """Resolve either a 'lat,lon' pair or a city name to coordinates."""
    coords = parse_coordinates(value)
    if coords is not None:
        return coords
    return await geocode(value, client=client)


def _route_cache_key(origin: Tuple[float, float], destination: Tuple[float, float]) -> str:
    o_lat, o_lon = origin
    d_lat, d_lon = destination
    return f"{ROUTE_CACHE_PREFIX}{o_lat:.4f},{o_lon:.4f}:{d_lat:.4f},{d_lon:.4f}"


async def fetch_route(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    client: Optional[httpx.AsyncClient] = None,
    use_cache: bool = True,
) -> Route:
    """Resolve a drivable road route between two coordinate pairs.

    Raises RoutingError when the router cannot be reached or reports that no
    route exists, so the caller never mistakes either for an empty corridor.
    """
    cache_key = _route_cache_key(origin, destination)

    if use_cache:
        try:
            redis_client = get_redis_client()
            cached = await redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                return Route(
                    origin=(float(data["origin"][0]), float(data["origin"][1])),
                    destination=(
                        float(data["destination"][0]),
                        float(data["destination"][1]),
                    ),
                    coordinates=[
                        (float(lat), float(lon)) for lat, lon in data["coordinates"]
                    ],
                    distance_m=float(data["distance_m"]),
                    duration_s=float(data["duration_s"]),
                )
        except Exception as e:
            logger.debug(f"Route cache lookup failed for {cache_key}: {e}")

    o_lat, o_lon = origin
    d_lat, d_lon = destination
    # Fixed precision rather than bare f-string interpolation, so the URL is
    # deterministic and does not depend on float repr.
    url = (
        f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/"
        f"{o_lon:.6f},{o_lat:.6f};{d_lon:.6f},{d_lat:.6f}"
    )
    params = {"overview": "full", "geometries": "geojson"}

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=25.0, follow_redirects=True)
    try:
        try:
            response = await http.get(url, params=params, headers={"User-Agent": USER_AGENT})
        except Exception as e:
            raise RoutingError(f"Routing service unreachable at {url}: {e}") from e

        if response.status_code != 200:
            raise RoutingError(
                f"Routing service returned HTTP {response.status_code} for {url}"
            )

        try:
            payload = response.json()
        except Exception as e:
            raise RoutingError(f"Routing service returned a malformed response: {e}") from e

        # OSRM reports failure in the body with a 200 status, so the code field
        # has to be checked explicitly.
        if payload.get("code") != "Ok":
            message = payload.get("message") or payload.get("code") or "unknown"
            raise RoutingError(f"No drivable route available: {message}")

        routes = payload.get("routes") or []
        if not routes:
            raise RoutingError("No drivable route available: router returned no routes")

        leg = routes[0]
        coordinates = [
            (float(lat), float(lon)) for lon, lat in leg["geometry"]["coordinates"]
        ]
        if len(coordinates) < 2:
            raise RoutingError("Routing service returned a degenerate route geometry")

        route = Route(
            origin=origin,
            destination=destination,
            coordinates=coordinates,
            distance_m=float(leg["distance"]),
            duration_s=float(leg["duration"]),
        )
    finally:
        if owns_client:
            await http.aclose()

    if use_cache:
        try:
            redis_client = get_redis_client()
            await redis_client.set(
                cache_key,
                json.dumps(
                    {
                        "origin": list(route.origin),
                        "destination": list(route.destination),
                        "coordinates": [[lat, lon] for lat, lon in route.coordinates],
                        "distance_m": route.distance_m,
                        "duration_s": route.duration_s,
                    }
                ),
                ex=settings.FUEL_ROUTE_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.debug(f"Route cache write failed for {cache_key}: {e}")

    return route