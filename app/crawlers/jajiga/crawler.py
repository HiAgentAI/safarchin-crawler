import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.accommodation import (
    AccommodationSearchQuery,
    AccommodationResult,
    PaginationMeta,
    ProvinceItem,
    CityItem,
)
from app.schemas.common import PriceInfo, Currency, ProviderInfo
from app.utils.http_client import ResilientHttpClient
from app.utils.calendar import to_gregorian
from app.core.credentials import get_provider_token, rotate_provider_token

logger = logging.getLogger(__name__)

# Pre-cached location IDs for prominent regions
KNOWN_LOCATIONS: Dict[str, str] = {
    "savadkuh": "305",
    "سوادکوه": "305",
    "ramsar": "201",
    "رامسر": "201",
    "kish": "368",
    "کیش": "368",
    "tehran": "22",
    "تهران": "22",
    "chalus": "197",
    "چالوس": "197",
    "masuleh": "183",
    "ماسوله": "183",
    "lafur": "d148",
    "لفور": "d148",
}

# Type mappings from Safarchin standard types to Jajiga internal types
TYPE_MAPPING: Dict[str, str] = {
    "villa": "villa",
    "cottage": "cottage",
    "swiss_cottage": "swiss_cottage",
    "wooden_cottage": "wooden_cottage",
    "apartment": "apartment",
    "suite": "suite",
    "ruralhome": "ruralhome",
    "rural_home": "ruralhome",
    "ecolog": "ecolog",
    "ecotourism": "ecolog",
    "apartmenthotel": "apartmenthotel",
    "apartment_hotel": "apartmenthotel",
    "motel": "motel",
}

# Sort order mappings
SORT_MAPPING: Dict[str, str] = {
    "cheapest": "low_price",
    "low_price": "low_price",
    "expensive": "high_price",
    "high_price": "high_price",
    "popular": "popularity",
    "popularity": "popularity",
    "rating": "rating",
    "newest": "newest",
    "books": "books",
    "discount": "discount",
}

@register_crawler(name="jajiga", services={"accommodation"})
class JajigaCrawler(BaseCrawler):
    """
    Crawler adapter for Jajiga (https://www.jajiga.com).
    Aggregates villas, cottages, rural homes, and suites across Iran.
    Features multi-token rotation on HTTP 429 and full pagination extraction.
    """
    provider_name = "jajiga"
    supported_services = {"accommodation"}

    BASE_URL = "https://api.jajiga.com/api"
    WEB_URL = "https://www.jajiga.com"
    CDN_URL = "https://storage.jajiga.com/public/pictures/medium"

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        self.client = client or ResilientHttpClient(timeout=20.0)
        self._location_cache: Dict[str, str] = dict(KNOWN_LOCATIONS)
        self.last_pagination: Optional[PaginationMeta] = None

    async def _get_auth_headers(self) -> Dict[str, str]:
        """Obtain authorization headers from the active non-cooldown token in the pool."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": self.WEB_URL,
            "Referer": f"{self.WEB_URL}/",
        }
        token_data = await get_provider_token(self.provider_name)
        if token_data and token_data.get("token"):
            token_val = token_data["token"]
            token_type = token_data.get("token_type", "Bearer")
            headers["Authorization"] = f"{token_type} {token_val}"
        return headers

    async def _execute_with_failover(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 4,
    ) -> Any:
        """
        Execute HTTP GET with automatic multi-token rotation on HTTP 429 Too Many Requests.
        """
        for attempt in range(1, max_retries + 1):
            headers = await self._get_auth_headers()
            try:
                resp = await self.client.get(url, params=params, headers=headers)
                return resp
            except Exception as e:
                err_msg = str(e)
                status_code = getattr(getattr(e, "response", None), "status_code", 0)
                is_429 = "429" in err_msg or status_code == 429

                if is_429 and attempt < max_retries:
                    logger.warning(
                        f"Jajiga returned HTTP 429 on attempt {attempt}/{max_retries}. "
                        "Triggering token pool rotation..."
                    )
                    rotated = await rotate_provider_token(
                        self.provider_name,
                        reason="429_rate_limit",
                        cooldown_seconds=300,
                    )
                    if not rotated:
                        logger.warning("All provider tokens are on cooldown. Retrying unauthenticated...")
                    continue
                raise

    async def _resolve_location_id(self, city: str) -> Optional[str]:
        """
        Resolve city/region string to Jajiga internal location ID.
        Checks known locations -> in-memory cache -> Jajiga autocomplete API.
        """
        clean_city = city.strip().lower()
        if clean_city in self._location_cache:
            return self._location_cache[clean_city]

        # If already an ID (e.g. "305", "368", or "d148")
        if clean_city.isdigit() or (clean_city.startswith("d") and clean_city[1:].isdigit()):
            return clean_city

        url = f"{self.BASE_URL}/autocomplete"
        params = {"phrase": city}

        try:
            resp = await self._execute_with_failover(url, params=params)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data

            items = data.get("items", [])
            if items:
                chosen = items[0]
                for item in items:
                    if item.get("type") in ("city", "district"):
                        chosen = item
                        break
                loc_id = str(chosen.get("id"))
                self._location_cache[clean_city] = loc_id
                return loc_id
        except Exception as e:
            logger.warning(f"Jajiga location autocomplete failed for '{city}': {e}")

        return None

    def _build_search_params(
        self,
        query: AccommodationSearchQuery,
        location_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Translate AccommodationSearchQuery into Jajiga API query parameters."""
        params: Dict[str, Any] = {
            "checkin": to_gregorian(query.checkin_date),
            "checkout": to_gregorian(query.checkout_date),
            "capacity": query.guests,
            "page": query.page or 1,
            "per_page": 18,
        }

        if location_id:
            params["locations[]"] = location_id

        # Property type filter
        if query.property_type:
            pt_clean = query.property_type.strip().lower()
            mapped_type = TYPE_MAPPING.get(pt_clean, pt_clean)
            params["types[]"] = mapped_type

        # Price range filter (Tomans)
        if query.min_price is not None:
            params["min_price"] = query.min_price
        if query.max_price is not None:
            params["max_price"] = query.max_price

        # Amenities / Facilities filter
        if query.amenities:
            params["features[]"] = query.amenities

        # Sort order filter
        if query.sort_by:
            mapped_sort = SORT_MAPPING.get(query.sort_by.lower(), "popularity")
            params["order"] = mapped_sort

        return params

    async def search_accommodations(
        self,
        query: AccommodationSearchQuery,
    ) -> List[AccommodationResult]:
        """Search Jajiga villas, cottages, and suites with full pagination extraction."""
        location_id = await self._resolve_location_id(query.city)
        url = f"{self.BASE_URL}/search"
        params = self._build_search_params(query, location_id=location_id)

        try:
            resp = await self._execute_with_failover(url, params=params)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data

            return self._parse_accommodations(data, query)
        except Exception as e:
            logger.error(f"Jajiga accommodation search failed: {e}")
            raise

    def _parse_accommodations(
        self,
        data: dict,
        query: AccommodationSearchQuery,
    ) -> List[AccommodationResult]:
        """Convert Jajiga API response items into Safarchin AccommodationResult list and record pagination metadata."""
        results: List[AccommodationResult] = []
        rooms_dict = data.get("rooms", {})
        items = rooms_dict.get("items", [])
        pagination_dict = rooms_dict.get("pagination", {})

        # Compute structured pagination metadata
        total = int(pagination_dict.get("total") or len(items))
        per_page = int(pagination_dict.get("per_page") or 18)
        current_page = int(pagination_dict.get("page") or query.page or 1)
        total_pages = max(1, math.ceil(total / per_page)) if per_page > 0 else 1

        self.last_pagination = PaginationMeta(
            current_page=current_page,
            per_page=per_page,
            total_count=total,
            total_pages=total_pages,
            has_next_page=current_page < total_pages,
            has_prev_page=current_page > 1,
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        for item in items:
            room_id = str(item.get("id"))
            price = float(item.get("price_after_discount") or item.get("price", 0))

            # Build thumbnail URL
            pictures = item.get("pictures", {}).get("items", [])
            thumb = None
            if pictures and pictures[0].get("url"):
                thumb = f"{self.CDN_URL}/{pictures[0]['url']}"

            # Rating information
            rating_data = item.get("rating", {})
            rating_val = None
            reviews_count = None
            if isinstance(rating_data, dict):
                rating_val = rating_data.get("total")
                reviews_count = rating_data.get("count")

            deep_link = f"{self.WEB_URL}/room/{room_id}"
            prop_type = query.property_type or "villa"

            residence = AccommodationResult(
                id=room_id,
                provider=ProviderInfo(
                    name=self.provider_name,
                    deep_link=deep_link,
                    scraped_at=now_iso,
                ),
                title=item.get("title", ""),
                property_type=prop_type,
                city=item.get("city_name") or query.city,
                capacity_standard=item.get("guest_number", 2),
                capacity_max=item.get("max_guest_number", item.get("guest_number", 4)),
                bedrooms=item.get("bedrooms") or item.get("room_number") or 1,
                rating=float(rating_val) if rating_val is not None else None,
                reviews_count=reviews_count,
                price_per_night=PriceInfo(
                    amount=price,
                    currency=Currency.IRT,
                    formatted=f"{int(price):,} تومان",
                ),
                thumbnail_url=thumb,
                amenities=item.get("properties", []),
            )
            results.append(residence)

        return results

    async def get_provinces(self) -> List[ProvinceItem]:
        """Fetch list of supported provinces ordered by room count."""
        url = f"{self.BASE_URL}/provinces"
        params = {"order": "rooms_count", "with": "rooms_count"}

        resp = await self._execute_with_failover(url, params=params)
        data = resp.json() if hasattr(resp, "json") else resp
        if asyncio.iscoroutine(data):
            data = await data

        items = data if isinstance(data, list) else data.get("data", [])
        return [
            ProvinceItem(
                id=str(p.get("id")),
                slug=p.get("slug", ""),
                name=p.get("name", ""),
                rooms_count=p.get("rooms_count"),
            )
            for p in items
        ]

    async def get_cities(self, province_id: Optional[str] = None) -> List[CityItem]:
        """Fetch list of cities (optionally filtered by parent province ID, e.g. 'p24' or 'p26')."""
        url = f"{self.BASE_URL}/cities"
        params: Dict[str, Any] = {}
        if province_id:
            params["province"] = province_id
        else:
            params["province"] = "p24"  # Default to Gilan if no province specified

        resp = await self._execute_with_failover(url, params=params)
        data = resp.json() if hasattr(resp, "json") else resp
        if asyncio.iscoroutine(data):
            data = await data

        items = data if isinstance(data, list) else data.get("data", [])
        return [
            CityItem(
                id=str(c.get("id")),
                slug=c.get("url", "").replace("/s/", "") if c.get("url") else c.get("slug"),
                name=c.get("name", ""),
                province_id=province_id,
                rooms_count=c.get("rooms_count"),
            )
            for c in items
        ]

    async def health_check(self) -> bool:
        """Check Jajiga connectivity."""
        try:
            url = f"{self.BASE_URL}/autocomplete"
            resp = await self._execute_with_failover(url, params={"phrase": "tehran"}, max_retries=1)
            return resp.status_code == 200
        except Exception:
            return False
