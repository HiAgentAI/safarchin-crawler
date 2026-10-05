from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.common import PriceInfo, ProviderInfo

class FlightSearchQuery(BaseModel):
    origin: str = Field(..., description="Origin city code or name (e.g. THR, Mashhad)")
    destination: str = Field(..., description="Destination city code or name (e.g. MHD, Kish)")
    depart_date: str = Field(..., description="Departure date (YYYY-MM-DD or 1403-07-25)")
    return_date: Optional[str] = Field(default=None, description="Return date for round-trip")
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=9)
    infants: int = Field(default=0, ge=0, le=9)
    cabin_class: Optional[str] = Field(default="economy", description="economy, business, first")
    providers: Optional[List[str]] = Field(default=None, description="Filter specific providers")

class FlightSegment(BaseModel):
    airline_name: str
    airline_code: Optional[str] = None
    flight_number: str
    aircraft: Optional[str] = None
    origin_code: str
    destination_code: str
    departure_time: str
    arrival_time: str
    departure_date: str
    arrival_date: Optional[str] = None
    cabin_class: str = "economy"
    baggage: Optional[str] = None

class FlightResult(BaseModel):
    id: str
    provider: ProviderInfo
    is_charter: bool = False
    price: PriceInfo
    available_seats: Optional[int] = None
    outbound: List[FlightSegment]
    inbound: Optional[List[FlightSegment]] = None

class CalendarItem(BaseModel):
    shamsi_date: Optional[str] = None
    gregorian_date: Optional[str] = None
    day_of_week: Optional[str] = None
    min_price_tomans: Optional[float] = None
    formatted_price: str
    is_available: bool = True
    booking_link: Optional[str] = None

class CalendarResponse(BaseModel):
    origin: str
    destination: str
    from_title: Optional[str] = None
    to_title: Optional[str] = None
    has_next_page: bool = False
    next_page: Optional[int] = None
    prev_page: Optional[int] = None
    calendar: List[CalendarItem]
