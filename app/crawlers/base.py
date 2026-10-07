from abc import ABC, abstractmethod
from typing import List, Set, Optional
from app.schemas.flight import FlightSearchQuery, FlightResult
from app.schemas.hotel import HotelSearchQuery, HotelResult
from app.schemas.accommodation import AccommodationSearchQuery, AccommodationResult
from app.schemas.transport import TransportSearchQuery, TransportResult
from app.schemas.restaurant import RestaurantSearchQuery, RestaurantResult

class BaseCrawler(ABC):
    """Abstract base class for all travel and accommodation crawler adapters."""

    provider_name: str = ""
    supported_services: Set[str] = set()
    is_cacheable: bool = True

    def supports_service(self, service: str) -> bool:
        """Check if provider supports a given service (flight, hotel, accommodation, bus, train)."""
        return service.lower() in {s.lower() for s in self.supported_services}

    async def search_flights(self, query: FlightSearchQuery) -> List[FlightResult]:
        """Search flights. Subclasses must override if supported."""
        raise NotImplementedError(f"Flight search is not supported by {self.provider_name}")

    async def search_hotels(self, query: HotelSearchQuery) -> List[HotelResult]:
        """Search hotels. Subclasses must override if supported."""
        raise NotImplementedError(f"Hotel search is not supported by {self.provider_name}")

    async def search_accommodations(self, query: AccommodationSearchQuery) -> List[AccommodationResult]:
        """Search accommodations / villas. Subclasses must override if supported."""
        raise NotImplementedError(f"Accommodation search is not supported by {self.provider_name}")

    async def search_transport(self, query: TransportSearchQuery) -> List[TransportResult]:
        """Search ground transport (bus or train). Subclasses must override if supported."""
        raise NotImplementedError(f"Transport search is not supported by {self.provider_name}")

    async def search_restaurants(self, query: "RestaurantSearchQuery") -> List["RestaurantResult"]:
        """Search restaurants. Subclasses must override if supported."""
        raise NotImplementedError(f"Restaurant search is not supported by {self.provider_name}")


    async def get_provinces(self) -> list:
        """Fetch list of supported provinces for this provider."""
        raise NotImplementedError(f"Provinces listing is not supported by {self.provider_name}")

    async def get_cities(self, province_id: Optional[str] = None) -> list:
        """Fetch list of cities (optionally filtered by province)."""
        raise NotImplementedError(f"Cities listing is not supported by {self.provider_name}")

    async def health_check(self) -> bool:
        """Ping provider or check connectivity."""
        return True

    async def close(self):
        """Clean up HTTP client sessions or connections."""
        pass

