from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import ProviderInfo


class FuelType(str, Enum):
    PETROL = "petrol"
    DIESEL = "diesel"
    CNG = "cng"
    LPG = "lpg"
    UNKNOWN = "unknown"


class FuelStationSearchQuery(BaseModel):
    """Origin and destination are either a city name or a 'lat,lon' pair.

    A coordinate pair is detected by shape, so callers can skip geocoding
    entirely when they already know where the trip starts and ends.
    """

    origin: str = Field(..., description="Origin city name or 'lat,lon' pair (e.g. Tehran or 35.6892,51.3890)")
    destination: str = Field(..., description="Destination city name or 'lat,lon' pair (e.g. Isfahan or 32.6539,51.6660)")
    radius_m: int = Field(default=1000, ge=50, le=10000, description="Corridor half-width in metres")
    fuel_types: Optional[List[FuelType]] = Field(
        default=None,
        description="Restrict results to these fuel types (default: all types)",
    )


class FuelStationResult(BaseModel):
    """A fuel station found along the route.

    Deliberately has no price field. Iranian octane-tier pricing and ration
    card programmes are administratively set and are not present in
    OpenStreetMap, so there is no value this API could report honestly.
    """

    id: str = Field(..., description="Stable id derived from the OSM element (e.g. osm:node:12345)")
    provider: ProviderInfo
    name: Optional[str] = Field(default=None, description="Station name, Persian where mapped")
    name_en: Optional[str] = Field(default=None, description="English name if available")
    latitude: float
    longitude: float
    fuel_type: FuelType = Field(default=FuelType.UNKNOWN, description="Classified fuel type, or unknown when undeterminable")
    km_into_trip: float = Field(..., description="Distance from the route's start, in km")
    distance_off_route_m: float = Field(..., description="Perpendicular distance from the route line, in metres")
    address: Optional[str] = Field(default=None, description="Street address if mapped")
    opening_hours: Optional[str] = Field(default=None, description="Opening hours string if mapped")
    tags: dict = Field(default_factory=dict, description="Raw OSM tags")


class FuelStationSearchResponse(BaseModel):
    """Envelope reporting route context and coverage.

    largest_gap_km exists because OpenStreetMap coverage is uneven: a long
    stretch with no station may be unmapped ground rather than a stretch
    genuinely without fuel. Reporting the gap keeps absence legible instead
    of letting a caller read it as a verified fact about the world.
    """

    status: str = Field(..., description="'success'")
    total_results: int = Field(..., description="Number of stations in the response")
    data_source: str = Field(..., description="Provider the stations came from")
    route: dict = Field(..., description="origin, destination, distance_km, duration_h")
    corridor_radius_m: int = Field(..., description="Corridor half-width used for this search")
    largest_gap_km: Optional[float] = Field(
        default=None,
        description="Longest stretch of the route with no returned station, in km. Null when fewer than two stations.",
    )
    results: List[FuelStationResult]