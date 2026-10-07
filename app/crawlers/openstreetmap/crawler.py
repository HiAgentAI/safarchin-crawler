import asyncio
import logging
import urllib.parse
from typing import List, Optional, Dict, Any
import httpx

from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.restaurant import RestaurantSearchQuery, RestaurantResult
from app.crawlers.openstreetmap.normalize import (
    extract_restaurant_result,
    deduplicate_restaurants,
    normalize_text,
)
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

NOMINATIM_DEFAULT_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

@register_crawler(name="openstreetmap", services={"restaurant"})
class OpenStreetMapCrawler(BaseCrawler):
    """
    Crawler adapter for OpenStreetMap (Nominatim + Overpass API).
    Fetches administrative boundaries and retrieves all restaurants within that area.
    """

    provider_name: str = "openstreetmap"
    supported_services = {"restaurant"}
    is_cacheable: bool = True

    def __init__(
        self,
        nominatim_url: str = NOMINATIM_DEFAULT_URL,
        overpass_mirrors: Optional[List[str]] = None,
        timeout: float = 25.0,
    ):
        self.nominatim_url = nominatim_url
        self.overpass_mirrors = overpass_mirrors or DEFAULT_OVERPASS_MIRRORS
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
        )

    async def resolve_boundary(self, city: str) -> Optional[int]:
        """
        Resolve city administrative boundary via Nominatim.
        Caches area ID in Redis for 30 days to respect OSM usage policy.
        """
        norm_city = normalize_text(city)
        cache_key = f"osm:boundary:{norm_city}"

        # 1. Try Redis cache
        try:
            r = get_redis_client()
            cached = await r.get(cache_key)
            if cached:
                logger.info(f"OSM boundary for '{city}' resolved from cache: area_id={cached}")
                return int(cached)
        except Exception as e:
            logger.debug(f"Redis boundary lookup failed: {e}")

        # 2. Query Nominatim
        headers = {
            "User-Agent": "SafarchinApp/1.0 (contact@safarchin.ir)",
            "Accept": "application/json",
        }

        # First attempt: structured search
        params = {"city": city, "country": "Iran", "format": "json", "limit": "1"}
        try:
            resp = await self.client.get(self.nominatim_url, params=params, headers=headers)
            data = resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.warning(f"Nominatim structured query failed for {city}: {e}")
            data = []

        # Second attempt: free-form query fallback
        if not data:
            params = {"q": f"{city}, Iran", "format": "json", "limit": "1"}
            try:
                resp = await self.client.get(self.nominatim_url, params=params, headers=headers)
                data = resp.json() if resp.status_code == 200 else []
            except Exception as e:
                logger.warning(f"Nominatim free-form query failed for {city}: {e}")
                data = []

        if not data or not isinstance(data, list):
            logger.warning(f"No boundary found on Nominatim for '{city}'")
            return None

        first = data[0]
        osm_id = first.get("osm_id")
        osm_type = first.get("osm_type")

        if not osm_id:
            return None

        # Convert to Overpass area ID
        if osm_type == "relation":
            area_id = 3600000000 + int(osm_id)
        elif osm_type == "way":
            area_id = 2400000000 + int(osm_id)
        else:
            logger.warning(f"Unsupported OSM boundary type: {osm_type} for '{city}'")
            return None

        # Store in Redis with 30-day TTL (2592000s)
        try:
            r = get_redis_client()
            await r.set(cache_key, str(area_id), ex=2592000)
        except Exception as e:
            logger.debug(f"Failed to cache boundary in Redis: {e}")

        logger.info(f"Resolved OSM boundary for '{city}': area_id={area_id} ({osm_type} {osm_id})")
        return area_id

    async def _query_overpass(self, area_id: int) -> Dict[str, Any]:
        """
        Execute Overpass QL query with multi-mirror rotation and retry.
        Optimized to search nodes and ways within the boundary.
        """
        query_str = f"""[out:json][timeout:{int(self.timeout)}];
area({area_id})->.searchArea;
(
  node["amenity"="restaurant"](area.searchArea);
  way["amenity"="restaurant"](area.searchArea);
);
out center tags;
"""
        headers = {
            "User-Agent": "SafarchinApp/1.0 (contact@safarchin.ir)",
        }
        data = {"data": query_str}


        last_error = None

        for mirror_url in self.overpass_mirrors:
            try:
                logger.info(f"Querying Overpass mirror: {mirror_url} for area {area_id}")
                resp = await self.client.post(
                    mirror_url,
                    data=data,
                    headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"Overpass mirror {mirror_url} returned status {resp.status_code}")
            except Exception as e:
                last_error = e
                logger.warning(f"Overpass mirror {mirror_url} failed: {e}")

        raise RuntimeError(f"All Overpass mirrors failed or timed out. Last error: {last_error}")

    async def search_restaurants(self, query: RestaurantSearchQuery) -> List[RestaurantResult]:
        """
        Fetch and parse restaurants in the requested city from OpenStreetMap.
        """
        area_id = await self.resolve_boundary(query.city)
        if not area_id:
            logger.info(f"Cannot resolve boundary for city '{query.city}'. Returning empty list.")
            return []

        payload = await self._query_overpass(area_id)
        elements = payload.get("elements", [])

        # Parse elements
        results: List[RestaurantResult] = []
        for el in elements:
            parsed = extract_restaurant_result(el, query.city)
            if parsed:
                results.append(parsed)

        # Collapse duplicate node/way records
        results = deduplicate_restaurants(results)

        # Filter by cuisine if specified
        if query.cuisine:
            norm_cuisine = query.cuisine.strip().lower()
            results = [
                r for r in results
                if r.cuisine and norm_cuisine in r.cuisine.lower()
            ]

        # Filter by name if specified
        if query.name:
            norm_name = normalize_text(query.name)
            results = [
                r for r in results
                if norm_name in normalize_text(r.name) or (r.name_en and norm_name in r.name_en.lower())
            ]

        # Apply pagination
        start = (query.page - 1) * query.limit
        end = start + query.limit
        return results[start:end]

    async def close(self):
        if hasattr(self, "client") and not self.client.is_closed:
            await self.client.aclose()
