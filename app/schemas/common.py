from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class Currency(str, Enum):
    IRR = "IRR"      # Iranian Rial
    IRT = "IRT"      # Iranian Toman
    USD = "USD"
    EUR = "EUR"

class PriceInfo(BaseModel):
    amount: float = Field(..., description="Numeric price amount")
    currency: Currency = Field(default=Currency.IRT, description="Currency denomination")
    formatted: Optional[str] = Field(default=None, description="Human readable formatted price")

class ProviderInfo(BaseModel):
    name: str = Field(..., description="Provider name, e.g. alibaba, flytoday, karnaval")
    deep_link: Optional[str] = Field(default=None, description="Direct URL to offer on provider site")
    scraped_at: Optional[str] = Field(default=None, description="ISO timestamp of crawl")

class Location(BaseModel):
    city_name: str
    city_code: Optional[str] = None
    terminal_or_airport: Optional[str] = None
