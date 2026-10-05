from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.common import PriceInfo, ProviderInfo

class TransportSearchQuery(BaseModel):
    origin: str = Field(..., description="Origin city (e.g. Tehran, Isfahan)")
    destination: str = Field(..., description="Destination city (e.g. Shiraz, Tabriz)")
    depart_date: str = Field(..., description="Date of departure (YYYY-MM-DD or Jalali)")
    transport_type: str = Field(..., description="'bus' or 'train'")
    passengers: int = Field(default=1, ge=1, le=20)
    providers: Optional[List[str]] = Field(default=None)

class TransportResult(BaseModel):
    id: str
    provider: ProviderInfo
    transport_type: str  # "bus" or "train"
    company_name: str
    service_class: str
    origin_terminal: str
    destination_terminal: str
    departure_date: str
    departure_time: str
    arrival_time: Optional[str] = None
    price: PriceInfo
    available_seats: Optional[int] = None
