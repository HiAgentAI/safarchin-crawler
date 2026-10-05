import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.flight import FlightSearchQuery, FlightResult, FlightSegment
from app.schemas.hotel import HotelSearchQuery, HotelResult, RoomOffer
from app.schemas.accommodation import AccommodationSearchQuery, AccommodationResult
from app.schemas.common import PriceInfo, Currency, ProviderInfo
from app.utils.http_client import ResilientHttpClient
from app.utils.calendar import to_gregorian

logger = logging.getLogger(__name__)

@register_crawler(name="alibaba", services={"flight", "hotel"})
class AlibabaCrawler(BaseCrawler):
    provider_name = "alibaba"
    supported_services = {"flight", "hotel"}


    BASE_URL = "https://ws.alibaba.ir"

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        self.client = client or ResilientHttpClient()

    async def search_flights(self, query: FlightSearchQuery) -> List[FlightResult]:
        """
        Search Alibaba domestic flights.
        Endpoint: /api/v1/flights/domestic/available
        """
        gregorian_date = to_gregorian(query.depart_date)
        url = f"{self.BASE_URL}/api/v1/flights/domestic/available"
        params = {
            "origin": query.origin.upper(),
            "destination": query.destination.upper(),
            "departureDate": gregorian_date,
            "adult": query.adults,
            "child": query.children,
            "infant": query.infants,
        }

        try:
            resp = await self.client.get(url, params=params)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data
            return self._parse_flights(data, query)
        except Exception as e:
            logger.error(f"Alibaba flight search failed: {e}")
            raise

    def _parse_flights(self, data: dict, query: FlightSearchQuery) -> List[FlightResult]:
        results: List[FlightResult] = []
        departing = data.get("result", {}).get("departing", [])

        for item in departing:
            unique_key = item.get("uniqueKey") or f"alibaba_fl_{item.get('flightNumber')}"
            airline_data = item.get("airline", {})
            airline_name = airline_data.get("name", "Unknown Airline")
            airline_code = airline_data.get("code")

            segment = FlightSegment(
                airline_name=airline_name,
                airline_code=airline_code,
                flight_number=str(item.get("flightNumber", "")),
                aircraft=item.get("aircraft"),
                origin_code=query.origin.upper(),
                destination_code=query.destination.upper(),
                departure_time=str(item.get("departureTime", ""))[:5],
                arrival_time=str(item.get("arrivalTime", ""))[:5],
                departure_date=item.get("departureDate", query.depart_date),
                cabin_class=item.get("classType", "economy"),
            )

            price_val = float(item.get("priceAdult", 0))

            flight = FlightResult(
                id=str(unique_key),
                provider=ProviderInfo(
                    name=self.provider_name,
                    deep_link=f"https://www.alibaba.ir/flights/{query.origin.lower()}-{query.destination.lower()}",
                    scraped_at=datetime.utcnow().isoformat(),
                ),
                is_charter=bool(item.get("isCharter", False)),
                price=PriceInfo(
                    amount=price_val,
                    currency=Currency.IRR,
                    formatted=f"{int(price_val):,} ریال",
                ),
                available_seats=item.get("seat"),
                outbound=[segment],
            )
            results.append(flight)

        return results

    async def search_hotels(self, query: HotelSearchQuery) -> List[HotelResult]:
        """Search Alibaba hotels."""
        url = f"{self.BASE_URL}/api/v2/hotel/domestic/search"
        params = {
            "city": query.city,
            "checkIn": to_gregorian(query.checkin_date),
            "checkOut": to_gregorian(query.checkout_date),
            "adults": query.adults,
        }
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json() if hasattr(resp, "json") else resp
            return self._parse_hotels(data, query)
        except Exception as e:
            logger.error(f"Alibaba hotel search failed: {e}")
            return []

    def _parse_hotels(self, data: dict, query: HotelSearchQuery) -> List[HotelResult]:
        results = []
        hotels = data.get("result", {}).get("hotels", [])
        for h in hotels:
            min_price = float(h.get("minPrice", 0))
            hotel = HotelResult(
                id=f"alibaba_hotel_{h.get('id', '')}",
                provider=ProviderInfo(name=self.provider_name, scraped_at=datetime.utcnow().isoformat()),
                hotel_name=h.get("hotelName", ""),
                hotel_name_en=h.get("hotelNameEn"),
                stars=h.get("stars"),
                user_rating=h.get("rating"),
                address=h.get("address"),
                thumbnail_url=h.get("thumbnail"),
                min_price_per_night=PriceInfo(amount=min_price, currency=Currency.IRR),
                rooms=[],
            )
            results.append(hotel)
        return results

    async def search_accommodations(self, query: AccommodationSearchQuery) -> List[AccommodationResult]:
        """Search accommodations via Jabama/Alibaba residence."""
        url = "https://tpa.jabama.com/api/v4/places/search"
        params = {
            "city": query.city,
            "checkIn": to_gregorian(query.checkin_date),
            "checkOut": to_gregorian(query.checkout_date),
            "guests": query.guests,
        }
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json() if hasattr(resp, "json") else resp
            return self._parse_accommodations(data, query)
        except Exception as e:
            logger.error(f"Alibaba/Jabama accommodation search failed: {e}")
            return []

    def _parse_accommodations(self, data: dict, query: AccommodationSearchQuery) -> List[AccommodationResult]:
        results = []
        items = data.get("result", {}).get("items", [])
        for item in items:
            price = float(item.get("pricePerNight", 0))
            residence = AccommodationResult(
                id=f"alibaba_res_{item.get('id', '')}",
                provider=ProviderInfo(name=self.provider_name, scraped_at=datetime.utcnow().isoformat()),
                title=item.get("title", ""),
                property_type=item.get("type", "villa"),
                city=query.city,
                capacity_standard=item.get("standardCapacity", 2),
                capacity_max=item.get("maxCapacity", 4),
                bedrooms=item.get("roomsCount", 1),
                rating=item.get("rating"),
                price_per_night=PriceInfo(amount=price, currency=Currency.IRT),
                thumbnail_url=item.get("image"),
                amenities=item.get("amenities", []),
            )
            results.append(residence)
        return results
