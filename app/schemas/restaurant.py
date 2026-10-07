from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.common import ProviderInfo

class RestaurantSearchQuery(BaseModel):
    city: str = Field(..., description="Target city name (e.g. Tehran, Isfahan, Shiraz, اصفهان)")
    cuisine: Optional[str] = Field(default=None, description="Cuisine filter (e.g. iranian, italian, fast_food)")
    name: Optional[str] = Field(default=None, description="Restaurant name search filter")
    page: int = Field(default=1, ge=1, description="Page number for pagination")
    limit: int = Field(default=50, ge=1, le=500, description="Items per page")
    providers: Optional[List[str]] = Field(default=None, description="Provider filter (default: openstreetmap)")

class RestaurantResult(BaseModel):
    id: str = Field(..., description="Unique provider ID (e.g. osm:node:12345)")
    provider: ProviderInfo
    name: str = Field(..., description="Restaurant name (Persian or localized)")
    name_en: Optional[str] = Field(default=None, description="English name if available")
    city: str = Field(..., description="City name")
    cuisine: Optional[str] = Field(default=None, description="Cuisine type if tagged")
    amenity: str = Field(default="restaurant", description="OSM amenity tag, e.g. restaurant")
    latitude: float = Field(..., description="Geographic latitude")
    longitude: float = Field(..., description="Geographic longitude")
    address: Optional[str] = Field(default=None, description="Street address if mapped")
    phone: Optional[str] = Field(default=None, description="Contact phone number")
    website: Optional[str] = Field(default=None, description="Website or social page")
    opening_hours: Optional[str] = Field(default=None, description="Opening hours string")
    last_edited: Optional[str] = Field(default=None, description="ISO timestamp of last OSM modification")
    tags: Dict[str, Any] = Field(default_factory=dict, description="Raw OSM tags")
