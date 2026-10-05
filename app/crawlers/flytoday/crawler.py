import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.flight import FlightSearchQuery, FlightResult, FlightSegment
from app.schemas.hotel import HotelSearchQuery, HotelResult, RoomOffer
from app.schemas.accommodation import AccommodationSearchQuery, AccommodationResult
from app.schemas.transport import TransportSearchQuery, TransportResult
from app.schemas.common import PriceInfo, Currency, ProviderInfo
from app.utils.http_client import ResilientHttpClient
from app.utils.calendar import to_gregorian

logger = logging.getLogger(__name__)

@register_crawler(name="flytoday", services={"flight", "hotel", "bus", "train"})
class FlyTodayCrawler(BaseCrawler):
    provider_name = "flytoday"
    supported_services = {"flight", "hotel", "bus", "train"}


    BASE_URL = "https://flight.flytoday.ir"

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        self.client = client or ResilientHttpClient()

    async def search_flights(self, query: FlightSearchQuery) -> List[FlightResult]:
        """
        Search FlyToday domestic & international flights.
        """
        gregorian_date = to_gregorian(query.depart_date)
        url = f"{self.BASE_URL}/api/v1/flight/search"
        payload = {
            "origin": query.origin.upper(),
            "destination": query.destination.upper(),
            "departureDate": gregorian_date,
            "adults": query.adults,
            "children": query.children,
            "infants": query.infants,
            "cabinClass": query.cabin_class or "Economy",
        }

        try:
            resp = await self.client.post(url, json_data=payload)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data
            return self._parse_flights(data, query)
        except Exception as e:
            logger.error(f"FlyToday flight search failed: {e}")
            raise

    def _parse_flights(self, data: dict, query: FlightSearchQuery) -> List[FlightResult]:
        results: List[FlightResult] = []
        itineraries = data.get("data", {}).get("pricedItineraries", [])

        for item in itineraries:
            item_id = item.get("id") or f"ft_fl_{len(results)}"
            pricing = item.get("pricingInfo", {})
            fare = float(pricing.get("totalFare", 0))

            segments: List[FlightSegment] = []
            options = item.get("originDestinationOptions", [])
            for opt in options:
                for seg in opt.get("flightSegments", []):
                    airline = seg.get("airline", {})
                    airline_name = airline.get("englishName") or airline.get("persianName", "Unknown")
                    airline_code = airline.get("code")

                    dep_dt = seg.get("departureDateTime", "")
                    arr_dt = seg.get("arrivalDateTime", "")
                    dep_time = dep_dt.split("T")[1][:5] if "T" in dep_dt else ""
                    arr_time = arr_dt.split("T")[1][:5] if "T" in arr_dt else ""
                    dep_date = dep_dt.split("T")[0] if "T" in dep_dt else query.depart_date

                    segments.append(
                        FlightSegment(
                            airline_name=airline_name,
                            airline_code=airline_code,
                            flight_number=str(seg.get("flightNumber", "")),
                            aircraft=seg.get("aircraft"),
                            origin_code=seg.get("departureAirport", query.origin),
                            destination_code=seg.get("arrivalAirport", query.destination),
                            departure_time=dep_time,
                            arrival_time=arr_time,
                            departure_date=dep_date,
                            cabin_class=seg.get("cabinClass", "Economy"),
                        )
                    )

            flight = FlightResult(
                id=str(item_id),
                provider=ProviderInfo(
                    name=self.provider_name,
                    deep_link=f"https://www.flytoday.ir/flight/search?origin={query.origin}&dest={query.destination}",
                    scraped_at=datetime.utcnow().isoformat(),
                ),
                is_charter=bool(item.get("isCharter", False)),
                price=PriceInfo(
                    amount=fare,
                    currency=Currency.IRR,
                    formatted=f"{int(fare):,} ریال",
                ),
                outbound=segments,
            )
            results.append(flight)

        return results

    async def search_hotels(self, query: HotelSearchQuery) -> List[HotelResult]:
        """Search FlyToday hotels."""
        url = "https://hotel.flytoday.ir/api/v1/hotels/search"
        payload = {
            "city": query.city,
            "checkIn": to_gregorian(query.checkin_date),
            "checkOut": to_gregorian(query.checkout_date),
            "rooms": query.rooms,
            "adults": query.adults,
        }
        try:
            resp = await self.client.post(url, json_data=payload)
            data = resp.json() if hasattr(resp, "json") else resp
            return self._parse_hotels(data, query)
        except Exception as e:
            logger.error(f"FlyToday hotel search failed: {e}")
            return []

    def _parse_hotels(self, data: dict, query: HotelSearchQuery) -> List[HotelResult]:
        results = []
        hotels = data.get("data", {}).get("hotels", [])
        for h in hotels:
            hotel = HotelResult(
                id=f"flytoday_hotel_{h.get('id', '')}",
                provider=ProviderInfo(name=self.provider_name, scraped_at=datetime.utcnow().isoformat()),
                hotel_name=h.get("name", ""),
                hotel_name_en=h.get("englishName"),
                stars=h.get("stars"),
                user_rating=h.get("rating"),
                address=h.get("address"),
                thumbnail_url=h.get("image"),
                min_price_per_night=PriceInfo(amount=float(h.get("minPrice", 0)), currency=Currency.IRR),
                rooms=[],
            )
            results.append(hotel)
        return results

    async def search_accommodations(self, query: AccommodationSearchQuery) -> List[AccommodationResult]:
        """Search FlyToday villas."""
        url = "https://villa.flytoday.ir/api/v1/villas/search"
        payload = {
            "city": query.city,
            "checkIn": to_gregorian(query.checkin_date),
            "checkOut": to_gregorian(query.checkout_date),
            "guests": query.guests,
        }
        try:
            resp = await self.client.post(url, json_data=payload)
            data = resp.json() if hasattr(resp, "json") else resp
            return self._parse_accommodations(data, query)
        except Exception as e:
            logger.error(f"FlyToday villa search failed: {e}")
            return []

    def _parse_accommodations(self, data: dict, query: AccommodationSearchQuery) -> List[AccommodationResult]:
        results = []
        items = data.get("data", {}).get("items", [])
        for item in items:
            residence = AccommodationResult(
                id=f"flytoday_villa_{item.get('id', '')}",
                provider=ProviderInfo(name=self.provider_name, scraped_at=datetime.utcnow().isoformat()),
                title=item.get("title", ""),
                property_type=item.get("type", "villa"),
                city=query.city,
                capacity_standard=item.get("capacity", 2),
                capacity_max=item.get("maxCapacity", 4),
                bedrooms=item.get("bedrooms", 1),
                rating=item.get("rate"),
                price_per_night=PriceInfo(amount=float(item.get("price", 0)), currency=Currency.IRT),
                thumbnail_url=item.get("image"),
                amenities=item.get("facilities", []),
            )
            results.append(residence)
        return results

    async def search_transport(self, query: TransportSearchQuery) -> List[TransportResult]:
        """
        Search FlyToday Bus or Train tickets.
        """
        endpoint = "bus" if query.transport_type.lower() == "bus" else "train"
        url = f"https://{endpoint}.flytoday.ir/api/v1/{endpoint}/search"
        payload = {
            "origin": query.origin,
            "destination": query.destination,
            "date": to_gregorian(query.depart_date),
            "passengers": query.passengers,
        }

        try:
            resp = await self.client.post(url, json_data=payload)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data
            return self._parse_transport(data, query)
        except Exception as e:
            logger.error(f"FlyToday {query.transport_type} search failed: {e}")
            raise

    def _parse_transport(self, data: dict, query: TransportSearchQuery) -> List[TransportResult]:
        results = []
        trips = data.get("data", {}).get("trips", [])
        for trip in trips:
            res = TransportResult(
                id=str(trip.get("id")),
                provider=ProviderInfo(name=self.provider_name, scraped_at=datetime.utcnow().isoformat()),
                transport_type=query.transport_type.lower(),
                company_name=trip.get("company", "Unknown"),
                service_class=trip.get("busType") or trip.get("trainType", "Standard"),
                origin_terminal=trip.get("originTerminal", query.origin),
                destination_terminal=trip.get("destinationTerminal", query.destination),
                departure_date=trip.get("departureDate", query.depart_date),
                departure_time=trip.get("departureTime", ""),
                arrival_time=trip.get("arrivalTime"),
                price=PriceInfo(
                    amount=float(trip.get("price", 0)),
                    currency=Currency.IRR,
                    formatted=f"{int(trip.get('price', 0)):,} ریال",
                ),
                available_seats=trip.get("availableSeats"),
            )
            results.append(res)
        return results
