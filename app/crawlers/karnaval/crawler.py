import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.accommodation import AccommodationSearchQuery, AccommodationResult
from app.schemas.common import PriceInfo, Currency, ProviderInfo
from app.utils.http_client import ResilientHttpClient
from app.utils.calendar import to_gregorian

logger = logging.getLogger(__name__)

# Temporarily disabled until Karnaval accommodation API endpoint is updated
@register_crawler(name="karnaval", services=set())
class KarnavalCrawler(BaseCrawler):
    provider_name = "karnaval"
    supported_services = set()


    BASE_URL = "https://www.karnaval.ir"

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        self.client = client or ResilientHttpClient()

    async def search_accommodations(self, query: AccommodationSearchQuery) -> List[AccommodationResult]:
        """
        Search Karnaval villas and suites.
        """
        url = f"{self.BASE_URL}/api/v1/villas/search"
        params = {
            "city": query.city,
            "checkin": to_gregorian(query.checkin_date),
            "checkout": to_gregorian(query.checkout_date),
            "guests": query.guests,
        }

        try:
            resp = await self.client.get(url, params=params)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data
            return self._parse_accommodations(data, query)
        except Exception as e:
            logger.error(f"Karnaval accommodation search failed: {e}")
            raise

    def _parse_accommodations(self, data: dict, query: AccommodationSearchQuery) -> List[AccommodationResult]:
        results: List[AccommodationResult] = []
        items = data.get("data", {}).get("items", [])

        for item in items:
            price = float(item.get("price", 0))
            images = item.get("images", [])
            thumb = images[0] if images else None

            residence = AccommodationResult(
                id=str(item.get("id")),
                provider=ProviderInfo(
                    name=self.provider_name,
                    deep_link=f"https://www.karnaval.ir/villa/{item.get('id')}",
                    scraped_at=datetime.utcnow().isoformat(),
                ),
                title=item.get("title", ""),
                property_type=item.get("type", "villa"),
                city=item.get("city", query.city),
                capacity_standard=item.get("capacity", 2),
                capacity_max=item.get("maxCapacity", 4),
                bedrooms=item.get("roomsCount", 1),
                rating=item.get("rate"),
                price_per_night=PriceInfo(
                    amount=price,
                    currency=Currency.IRT,
                    formatted=f"{int(price):,} تومان",
                ),
                thumbnail_url=thumb,
                amenities=item.get("facilities", []),
            )
            results.append(residence)

        return results
