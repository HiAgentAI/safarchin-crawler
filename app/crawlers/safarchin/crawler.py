import asyncio
import logging
from typing import List, Optional, Dict, Any
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.crawlers.safarchin.airports import resolve_route, find_airport, AirportInfo
from app.crawlers.safarchin.parser import parse_flights_html, parse_calendar_json
from app.schemas.flight import FlightSearchQuery, FlightResult
from app.schemas.transport import TransportSearchQuery, TransportResult
from app.schemas.common import PriceInfo, Currency, ProviderInfo, Location
from app.utils.http_client import ResilientHttpClient
from app.utils.calendar import to_jalali, to_gregorian

logger = logging.getLogger(__name__)

@register_crawler(name="safarchin", services={"flight", "transport"})
class SafarchinCrawler(BaseCrawler):
    """
    Crawler adapter for Safarchin.ir (Charter724 / Agent724 white-label engine).
    Supports:
    - Real-time flight search with server-side filtering
    - 15-day paginated low-price calendar matrix
    - Intercity train queries (where offered)
    - Automatic retries & resilient TLS fingerprinting
    """

    provider_name: str = "safarchin"
    supported_services = {"flight", "transport"}
    BASE_URL: str = "http://safarchin.ir"

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        # Configure client with 3 retries and chrome impersonation for anti-bot resilience
        self.client = client or ResilientHttpClient(
            impersonate="chrome120",
            timeout=15.0,
            retries=3,
        )

    async def search_flights(self, query: FlightSearchQuery) -> List[FlightResult]:
        """
        Searches one-way or round-trip flights on Safarchin.
        """
        orig_ap, dest_ap = resolve_route(query.origin, query.destination)
        depart_jalali = to_jalali(query.depart_date)
        
        url = f"{self.BASE_URL}/Ticket-{orig_ap.slug}-{dest_ap.slug}.html"
        params = {"t": depart_jalali}
        
        post_data: Dict[str, Any] = {
            "ajax_load": "1",
            "sort": "p",  # Sort by lowest price
        }
        
        if query.adults > 1:
            post_data["capacity"] = str(min(query.adults, 9))
            
        headers = {
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            logger.info(f"Querying Safarchin flights: {orig_ap.slug} -> {dest_ap.slug} ({depart_jalali})")
            resp = await self.client.post(
                url=f"{url}?t={depart_jalali}",
                data=post_data,
                headers=headers
            )
            html = resp.text if hasattr(resp, "text") else str(resp)
            outbound_results = parse_flights_html(
                html=html,
                query=query,
                orig_slug=orig_ap.slug,
                dest_slug=dest_ap.slug,
                depart_jalali=depart_jalali,
                provider_name=self.provider_name,
                base_url=self.BASE_URL
            )
            
            # Handle return trip if requested
            if query.return_date:
                return_jalali = to_jalali(query.return_date)
                return_url = f"{self.BASE_URL}/Ticket-{dest_ap.slug}-{orig_ap.slug}.html?t={return_jalali}"
                resp_return = await self.client.post(
                    url=return_url,
                    data=post_data,
                    headers=headers
                )
                html_return = resp_return.text if hasattr(resp_return, "text") else str(resp_return)
                inbound_results = parse_flights_html(
                    html=html_return,
                    query=query,
                    orig_slug=dest_ap.slug,
                    dest_slug=orig_ap.slug,
                    depart_jalali=return_jalali,
                    provider_name=self.provider_name,
                    base_url=self.BASE_URL
                )
                
                # Pair outbound and inbound segments
                if inbound_results and outbound_results:
                    for out_res in outbound_results:
                        out_res.inbound = inbound_results[0].outbound
                        
            return outbound_results

        except Exception as e:
            logger.error(f"Safarchin flight search failed for {query.origin} -> {query.destination}: {e}")
            raise

    async def search_calendar(
        self,
        origin: str,
        destination: str,
        page: int = 0
    ) -> Dict[str, Any]:
        """
        Retrieves the 15-day low-price calendar matrix for a route.
        Supports pagination via page offset (0 for first 15 days, 1 for next 15 days, etc.).
        """
        orig_ap, dest_ap = resolve_route(origin, destination)
        url = f"{self.BASE_URL}/get_query.html"
        
        post_data = {
            "from": orig_ap.id,
            "to": dest_ap.id,
            "ajax_load": "1",
            "pdate": str(page),
        }
        
        headers = {
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            logger.info(f"Querying Safarchin calendar: {orig_ap.persian_name} -> {dest_ap.persian_name} (page {page})")
            resp = await self.client.post(url=url, data=post_data, headers=headers)
            raw_json = resp.json() if hasattr(resp, "json") else {}
            if asyncio.iscoroutine(raw_json):
                raw_json = await raw_json
                
            return parse_calendar_json(raw_json, origin=orig_ap.slug, destination=dest_ap.slug)
            
        except Exception as e:
            logger.error(f"Safarchin calendar query failed: {e}")
            raise

    async def search_transport(self, query: TransportSearchQuery) -> List[TransportResult]:
        """
        Retrieves train transport options if available.
        """
        if query.transport_type.lower() != "train":
            return []
            
        orig_ap, dest_ap = resolve_route(query.origin, query.destination)
        depart_jalali = to_jalali(query.depart_date)
        depart_gregorian = to_gregorian(depart_jalali)
        
        # Safarchin train query uses serialized base64 param or direct Train.html
        url = f"{self.BASE_URL}/Train.html"
        post_data = {"ajax_load": "1"}
        
        try:
            resp = await self.client.post(url, data=post_data)
            html = resp.text if hasattr(resp, "text") else str(resp)
            
            # If train records exist, parse them
            results: List[TransportResult] = []
            if 'class="resu ' in html:
                # Same resu block structure
                flight_items = parse_flights_html(
                    html=html,
                    query=FlightSearchQuery(
                        origin=query.origin,
                        destination=query.destination,
                        depart_date=query.depart_date,
                    ),
                    orig_slug=orig_ap.slug,
                    dest_slug=dest_ap.slug,
                    depart_jalali=depart_jalali,
                    provider_name=self.provider_name,
                )
                for f in flight_items:
                    for seg in f.outbound:
                        results.append(TransportResult(
                            id=f"safarchin_train_{f.id}",
                            provider=f.provider,
                            transport_type="train",
                            company_name=seg.airline_name,
                            service_class=seg.cabin_class,
                            origin_terminal=orig_ap.persian_name,
                            destination_terminal=dest_ap.persian_name,
                            departure_date=depart_gregorian,
                            departure_time=seg.departure_time,
                            arrival_time=seg.arrival_time,
                            price=f.price,
                            available_seats=f.available_seats,
                        ))
            return results
        except Exception as e:
            logger.warning(f"Safarchin train transport search returned no data: {e}")
            return []

    async def health_check(self) -> bool:
        """
        Pings Safarchin homepage to verify connectivity.
        """
        try:
            resp = await self.client.get(f"{self.BASE_URL}/")
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Safarchin health check failed: {e}")
            return False

    async def close(self):
        """Clean up HTTP client session."""
        if self.client:
            await self.client.close()
