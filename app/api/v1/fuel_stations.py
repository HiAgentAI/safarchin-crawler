from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import verify_api_key
from app.core.config import settings
from app.core.redis import resolve_cache_params
from app.crawlers.fuelstation.crawler import FuelStationService
from app.crawlers.fuelstation.overpass import OverpassRetrievalError
from app.crawlers.fuelstation.routing import (
    LocationResolutionError,
    RoutingError,
)
from app.db.models import APIKey
from app.schemas.fuel_station import FuelStationSearchQuery, FuelType

router = APIRouter(prefix="/fuel-stations", tags=["Fuel Stations"])


@router.get("")
async def search_fuel_stations(
    origin: str = Query(
        ...,
        description="Origin city name or 'lat,lon' pair (e.g. Tehran or 35.6892,51.3890)",
    ),
    destination: str = Query(
        ...,
        description="Destination city name or 'lat,lon' pair (e.g. Isfahan or 32.6539,51.6660)",
    ),
    radius_m: int = Query(
        default=settings.FUEL_CORRIDOR_RADIUS_M,
        ge=50,
        le=settings.FUEL_CORRIDOR_MAX_RADIUS_M,
        description="Corridor half-width in metres",
    ),
    fuel_types: Optional[str] = Query(
        default=None,
        description=(
            "Comma-separated fuel types to restrict to, e.g. 'petrol,diesel'. "
            "Omit to return every type. One of: petrol, diesel, cng, lpg, unknown."
        ),
    ),
    no_cache: bool = Query(default=False, description="Bypass the cached route lookup"),
    key: APIKey = Depends(verify_api_key),
):
    """Fuel stations located along the road route between two points.

    Results are ordered by distance from the route's start, so reading them
    top to bottom follows the direction of travel. The response reports the
    longest stretch with no station, because OpenStreetMap coverage is uneven
    and an unreported gap reads as a verified absence.

    No prices are returned: Iranian octane-tier pricing and ration cards are
    administratively set and are not present in OpenStreetMap.
    """
    parsed_types: Optional[List[FuelType]] = None
    if fuel_types:
        parsed_types = []
        for raw in fuel_types.split(","):
            token = raw.strip().lower()
            if not token:
                continue
            try:
                parsed_types.append(FuelType(token))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Unknown fuel type '{raw}'. Valid values: "
                        + ", ".join(t.value for t in FuelType)
                    ),
                )

    query = FuelStationSearchQuery(
        origin=origin,
        destination=destination,
        radius_m=radius_m,
        fuel_types=parsed_types,
    )

    use_cache, _ttl = resolve_cache_params(no_cache=no_cache)

    try:
        payload = await FuelStationService().search(query, use_cache=use_cache)
    except LocationResolutionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except RoutingError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )
    except OverpassRetrievalError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )

    return {
        **payload,
        "results": [
            r if isinstance(r, dict) else r.model_dump() for r in payload["results"]
        ],
    }