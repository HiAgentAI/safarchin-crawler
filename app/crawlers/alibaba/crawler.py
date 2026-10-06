import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.crawlers.alibaba.locations import to_alibaba_city_code
from app.crawlers.alibaba.normalize import (
    collect_departing,
    is_bookable,
    normalize_aircraft,
    normalize_cabin_class,
    split_timestamp,
)
from app.crawlers.alibaba.protocol import (
    AlibabaSearchError,
    extract_encoded_handle,
    two_phase_search,
)
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.flight import FlightResult, FlightSearchQuery, FlightSegment
from app.schemas.transport import TransportResult, TransportSearchQuery
from app.schemas.common import Currency, PriceInfo, ProviderInfo
from app.utils.http_client import ResilientHttpClient
from app.utils.calendar import to_gregorian

logger = logging.getLogger(__name__)


@register_crawler(name="alibaba", services={"flight", "train"})
class AlibabaCrawler(BaseCrawler):
    """
    Alibaba travel provider.

    Flights and trains both use a two-phase search: criteria are POSTed, then the
    handle from that response is used to GET the results. See
    ``app/crawlers/alibaba/protocol.py``.

    Prices are in the unit Alibaba quotes for each service, which differs between
    them: flights are Rial, trains are Toman.
    """

    provider_name = "alibaba"
    supported_services = {"flight", "train"}

    BASE_URL = "https://ws.alibaba.ir"
    FLIGHTS_PATH = "/api/v1/flights/domestic/available"
    TRAIN_PATH = "/api/v1/train/available"

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        self.client = client or ResilientHttpClient()

    # ------------------------------------------------------------------ flights

    async def search_flights(self, query: FlightSearchQuery) -> List[FlightResult]:
        """
        Search Alibaba domestic flights.

        The endpoint requires POST; a GET is answered with 405 Method Not Allowed.
        """
        payload = {
            "origin": to_alibaba_city_code(query.origin, field="origin"),
            "destination": to_alibaba_city_code(query.destination, field="destination"),
            "departureDate": to_gregorian(query.depart_date),
            "adult": query.adults,
            "child": query.children,
            "infant": query.infants,
        }

        body = await two_phase_search(
            self.client, f"{self.BASE_URL}{self.FLIGHTS_PATH}", payload
        )
        return self._parse_flights(body, query)

    def _parse_flights(self, body: Dict[str, Any], query: FlightSearchQuery) -> List[FlightResult]:
        results: List[FlightResult] = []
        scraped_at = datetime.utcnow().isoformat()

        for item in collect_departing(body):
            # Cancelled and full flights are still present in the feed with a
            # placeholder fare, so they are excluded rather than returned.
            if not is_bookable(item):
                continue

            departure_date, departure_time = split_timestamp(item.get("leaveDateTime"))
            arrival_date, arrival_time = split_timestamp(item.get("arrivalDateTime"))
            price = self._parse_price(item.get("priceAdult"))

            segment = FlightSegment(
                airline_name=item.get("airlineName"),
                airline_code=item.get("airlineCode"),
                flight_number=str(item.get("flightNumber", "")),
                aircraft=normalize_aircraft(item.get("aircraft")),
                origin_code=item.get("origin") or item.get("originCode") or query.origin.upper(),
                destination_code=item.get("destination") or item.get("destinationCode") or query.destination.upper(),
                departure_time=departure_time,
                arrival_time=arrival_time,
                departure_date=departure_date or query.depart_date,
                arrival_date=arrival_date,
                cabin_class=normalize_cabin_class(item.get("classType")),
            )

            results.append(
                FlightResult(
                    id=str(item.get("uniqueKey") or f"alibaba_{item.get('proposalId', '')}"),
                    provider=ProviderInfo(
                        name=self.provider_name,
                        deep_link=self._flight_deep_link(query),
                        scraped_at=scraped_at,
                    ),
                    is_charter=bool(item.get("isCharter", False)),
                    price=price,
                    available_seats=item.get("seat"),
                    outbound=[segment],
                )
            )

        return results

    # ------------------------------------------------------------------- trains

    async def search_transport(self, query: TransportSearchQuery) -> List[TransportResult]:
        """
        Search Alibaba domestic passenger train departures.

        Alibaba rejects a train search whose origin equals its destination, and
        requires a passenger count; both surface as an error rather than as an
        empty departure list.
        """
        transport_type = query.transport_type.lower()
        if transport_type != "train":
            raise NotImplementedError(
                f"Alibaba does not provide {transport_type} search; only train is integrated"
            )

        payload = {
            "origin": to_alibaba_city_code(query.origin, field="origin"),
            "destination": to_alibaba_city_code(query.destination, field="destination"),
            "departureDate": to_gregorian(query.depart_date),
            "passengerCount": query.passengers,
        }

        body = await two_phase_search(
            self.client,
            f"{self.BASE_URL}{self.TRAIN_PATH}",
            payload,
            extract_handle=extract_encoded_handle,
        )
        return self._parse_trains(body, query)

    def _parse_trains(self, body: Dict[str, Any], query: TransportSearchQuery) -> List[TransportResult]:
        results: List[TransportResult] = []
        scraped_at = datetime.utcnow().isoformat()

        for item in collect_departing(body):
            max_passengers = item.get("maxPassengerCount")
            # Zero purchasable seats means the departure cannot be booked.
            if max_passengers is not None and int(max_passengers) <= 0:
                continue

            departure_date, departure_time = split_timestamp(item.get("departureDateTime"))
            arrival_date, arrival_time = split_timestamp(item.get("arrivalDateTime"))

            results.append(
                TransportResult(
                    id=str(item.get("proposalId")),
                    provider=ProviderInfo(
                        name=self.provider_name,
                        deep_link=self._train_deep_link(query),
                        scraped_at=scraped_at,
                    ),
                    transport_type="train",
                    company_name=item.get("companyName"),
                    service_class=item.get("wagonName") or item.get("wagonClass"),
                    origin_terminal=item.get("originName") or item.get("originCode") or query.origin,
                    destination_terminal=(
                        item.get("destinationName") or item.get("destinationCode") or query.destination
                    ),
                    departure_date=departure_date or query.depart_date,
                    departure_time=departure_time,
                    # A journey crossing midnight must not look like it arrives
                    # before it departs, so the arrival date is reported too.
                    arrival_time=self._arrival_with_date(arrival_date, arrival_time, departure_date),
                    price=self._parse_price(item.get("cost"), currency=Currency.IRT),
                    available_seats=max_passengers,
                )
            )

        return results

    # ------------------------------------------------------------------ helpers

    def _parse_price(self, amount: Any, currency: Currency = Currency.IRR) -> PriceInfo:
        """
        Build a price in the unit Alibaba quotes for the service.

        Flights are quoted in Rial and trains in Toman; the two differ by a
        factor of ten and must not be conflated.
        """
        try:
            value = float(amount) if amount is not None else 0.0
        except (TypeError, ValueError):
            value = 0.0

        unit = "ریال" if currency == Currency.IRR else "تومان"
        return PriceInfo(
            amount=value,
            currency=currency,
            formatted=f"{int(value):,} {unit}",
        )

    @staticmethod
    def _arrival_with_date(arrival_date: Optional[str], arrival_time: str, departure_date: Optional[str]) -> str:
        """Prefix the arrival time with its date when it differs from departure."""
        if arrival_date and departure_date and arrival_date != departure_date:
            return f"{arrival_date} {arrival_time}"
        return arrival_time

    @staticmethod
    def _flight_deep_link(query: FlightSearchQuery) -> str:
        return (
            "https://www.alibaba.ir/flights/"
            f"{query.origin.lower()}-{query.destination.lower()}"
        )

    @staticmethod
    def _train_deep_link(query: TransportSearchQuery) -> str:
        return (
            "https://www.alibaba.ir/train/"
            f"{query.origin.lower()}-{query.destination.lower()}"
        )