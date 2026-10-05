from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.common import PriceInfo, ProviderInfo

class HotelSearchQuery(BaseModel):
    city: str = Field(..., description="Destination city name or code (e.g. Tehran, Kish, Shiraz)")
    checkin_date: str = Field(..., description="Check-in date (YYYY-MM-DD or Jalali YYYY/MM/DD)")
    checkout_date: str = Field(..., description="Check-out date (YYYY-MM-DD or Jalali YYYY/MM/DD)")
    rooms: int = Field(default=1, ge=1, le=10)
    adults: int = Field(default=2, ge=1, le=20)
    providers: Optional[List[str]] = Field(default=None)
    stars: Optional[int] = Field(default=None, ge=1, le=5, description="Filter by star rating (1-5)")
    min_price: Optional[int] = Field(default=None, description="Minimum price per night in IRR")
    max_price: Optional[int] = Field(default=None, description="Maximum price per night in IRR")
    sort_by: Optional[str] = Field(default=None, description="Sort order: price_asc, price_desc, rate, popular")
    page: int = Field(default=1, ge=1, description="Page number for pagination")

class RoomOffer(BaseModel):
    room_name: str
    capacity: int = 2
    bed_type: Optional[str] = None
    has_breakfast: bool = False
    is_cancellable: bool = False
    price_per_night: PriceInfo
    total_price: Optional[PriceInfo] = None
    extra_capacity: Optional[int] = 0
    extra_price: Optional[PriceInfo] = None

class HotelResult(BaseModel):
    id: str
    provider: ProviderInfo
    hotel_name: str
    hotel_name_en: Optional[str] = None
    stars: Optional[int] = Field(default=None, ge=1, le=5)
    user_rating: Optional[float] = None
    address: Optional[str] = None
    thumbnail_url: Optional[str] = None
    min_price_per_night: PriceInfo
    rooms: List[RoomOffer] = []
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    reviews_count: Optional[int] = None
    discount_percent: Optional[float] = None
    hotel_url: Optional[str] = None
