from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.common import PriceInfo, ProviderInfo

class AccommodationSearchQuery(BaseModel):
    city: str = Field(..., description="Destination city or region name (e.g. 'سوادکوه', 'Savadkuh', 'رامسر', 'Ramsar', 'تهران')")
    checkin_date: str = Field(..., description="Check-in date (Gregorian 'YYYY-MM-DD' or Jalali '1405-07-24')")
    checkout_date: str = Field(..., description="Check-out date (Gregorian 'YYYY-MM-DD' or Jalali '1405-07-26')")
    guests: int = Field(default=2, ge=1, le=50, description="Minimum guest capacity required")
    property_type: Optional[str] = Field(
        default=None,
        description="Filter by type: villa, cottage, wooden_cottage, swiss_cottage, apartment, suite, ruralhome, ecolog, apartmenthotel, motel"
    )
    min_price: Optional[int] = Field(default=None, description="Minimum price per night in Tomans (IRT)")
    max_price: Optional[int] = Field(default=None, description="Maximum price per night in Tomans (IRT)")
    amenities: Optional[List[str]] = Field(
        default=None,
        description="Amenities list: pool, pool-outdoor, pool-indoor, pool-hot, jacuzzi, sauna, billiard, foosball, parking, heating, cooler, wifi, elevator, furniture"
    )
    sort_by: Optional[str] = Field(
        default="popularity",
        description="Sort order: popularity (default), low_price (cheapest), high_price (expensive), rating, newest, books, discount"
    )
    page: int = Field(default=1, ge=1, description="Page number for pagination (starts at 1)")
    providers: Optional[List[str]] = Field(default=None, description="Target providers (e.g. jajiga, karnaval, alibaba)")

class AccommodationResult(BaseModel):
    id: str
    provider: ProviderInfo
    title: str
    property_type: str = "villa"
    city: str
    capacity_standard: int = 2
    capacity_max: int = 4
    bedrooms: int = 1
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    price_per_night: PriceInfo
    thumbnail_url: Optional[str] = None
    amenities: List[str] = []

class PaginationMeta(BaseModel):
    current_page: int = Field(default=1, description="Current page index")
    per_page: int = Field(default=18, description="Items per page")
    total_count: int = Field(default=0, description="Total matching accommodations")
    total_pages: int = Field(default=1, description="Total pages available")
    has_next_page: bool = Field(default=False, description="Whether more pages are available")
    has_prev_page: bool = Field(default=False, description="Whether previous pages exist")

class PaginatedAccommodationResponse(BaseModel):
    status: str = "success"
    pagination: PaginationMeta
    results: List[AccommodationResult]

class ProvinceItem(BaseModel):
    id: str = Field(..., description="Province ID (e.g. 'p24')")
    slug: str = Field(..., description="URL slug (e.g. 'gilan')")
    name: str = Field(..., description="Persian province name (e.g. 'گیلان')")
    rooms_count: Optional[int] = Field(default=None, description="Number of active listings")

class ProvincesResponse(BaseModel):
    status: str = "success"
    provider: str
    total: int
    provinces: List[ProvinceItem]

class CityItem(BaseModel):
    id: str = Field(..., description="City or district ID (e.g. '305', '368')")
    slug: Optional[str] = Field(default=None, description="URL slug (e.g. 'savadkuh', 'kish')")
    name: str = Field(..., description="Persian city name (e.g. 'سوادکوه', 'کیش')")
    province_id: Optional[str] = Field(default=None, description="Parent province ID")
    rooms_count: Optional[int] = Field(default=None, description="Number of active listings")

class CitiesResponse(BaseModel):
    status: str = "success"
    provider: str
    province_id: Optional[str] = None
    total: int
    cities: List[CityItem]

