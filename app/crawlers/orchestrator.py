import asyncio
import hashlib
import json
import logging
import time
from typing import Any, List, Optional, Set, Dict
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import crawler_registry
from app.core.redis import CacheManager
from app.schemas.flight import FlightSearchQuery, FlightResult
from app.schemas.hotel import HotelSearchQuery, HotelResult, RoomOffer
from app.schemas.accommodation import (
    AccommodationSearchQuery,
    AccommodationResult,
    PaginationMeta,
    ProvinceItem,
    CityItem,
)
from app.schemas.transport import TransportSearchQuery, TransportResult
from app.schemas.common import Currency
import app.crawlers  # noqa: F401 - ensure all crawler providers are registered

logger = logging.getLogger(__name__)

# Providers report prices in different units. Comparing raw amounts across
# providers would rank a Toman amount as ten times cheaper than an equal Rial
# amount. Conversion factors are relative to IRR, which is the comparison unit.
_CURRENCY_TO_IRR_FACTOR: Dict[str, float] = {
    Currency.IRR.value: 1.0,
    Currency.IRT.value: 10.0,
}

def price_sort_key(price: Any) -> float:
    """
    Build a comparable sort key from a PriceInfo-like object.

    Amounts are normalized to IRR so results from providers using different
    units sort by real value. A missing price, or one in a unit with no known
    factor, sorts last rather than being treated as free.
    """
    if price is None:
        return float("inf")
    amount = getattr(price, "amount", None)
    if amount is None:
        return float("inf")
    currency = getattr(price, "currency", None)
    currency_value = getattr(currency, "value", currency)
    factor = _CURRENCY_TO_IRR_FACTOR.get(currency_value)
    if factor is None:
        return float("inf")
    try:
        return float(amount) * factor
    except (TypeError, ValueError):
        return float("inf")

class CrawlerOrchestrator:
    """
    Coordinates multi-provider parallel crawls, caching,
    timeout handling, and partial failure isolation.
    """

    NON_CACHEABLE_PROVIDERS: Set[str] = {"iranhotel"}

    # Providers whose own search protocol costs more than one round trip need a
    # larger budget than the shared default, otherwise they are dropped while
    # faster siblings succeed.
    PROVIDER_TIMEOUT_OVERRIDES: Dict[str, float] = {
        "alibaba": 30.0,
    }

    def __init__(self, cache_manager: Optional[CacheManager] = None, timeout: float = 15.0):
        self.cache = cache_manager or CacheManager()
        self.timeout = timeout
        self.last_pagination: Optional[PaginationMeta] = None

    def _timeout_for(self, provider_name: str) -> float:
        """Resolve the time budget for a single provider call."""
        if not provider_name:
            return self.timeout
        return self.PROVIDER_TIMEOUT_OVERRIDES.get(
            provider_name.strip().lower(), self.timeout
        )

    def is_provider_cacheable(self, provider_name: str, crawler: Optional[BaseCrawler] = None) -> bool:
        """
        Check if a provider is eligible for caching.
        Certain providers (like Iran Hotel) must NEVER be cached to ensure real-time accuracy.
        """
        if not provider_name:
            return True
        clean_name = provider_name.strip().lower()
        if clean_name in self.NON_CACHEABLE_PROVIDERS:
            return False
        c = crawler or crawler_registry.get_crawler(clean_name)
        if c is not None and not getattr(c, "is_cacheable", True):
            return False
        return True

    def _get_item_provider_name(self, item: Any) -> str:
        """Extract provider name from a result item (dict or Pydantic model)."""
        if isinstance(item, dict):
            provider = item.get("provider")
            if isinstance(provider, dict):
                return str(provider.get("name", "")).strip().lower()
            elif isinstance(provider, str):
                return provider.strip().lower()
            return ""
        provider = getattr(item, "provider", None)
        if provider is not None:
            if isinstance(provider, dict):
                return str(provider.get("name", "")).strip().lower()
            return str(getattr(provider, "name", "")).strip().lower()
        return ""

    def _generate_cache_key(self, service: str, query_dict: dict) -> str:
        """Create deterministic SHA256 cache key from query params."""
        clean_dict = {k: v for k, v in sorted(query_dict.items()) if v is not None}
        raw_str = f"{service}:{json.dumps(clean_dict, sort_keys=True)}"
        hashed = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
        return f"search_cache:{service}:{hashed}"

    def _unpack_cache_payload(self, cached: Any) -> tuple[List[Any], Optional[dict], Set[str]]:
        """Unpack cached data supporting legacy lists and new structured dict payloads."""
        items: List[Any] = []
        pagination: Optional[dict] = None
        providers: Set[str] = set()

        if isinstance(cached, dict):
            items = cached.get("results", [])
            pagination = cached.get("pagination")
            if "cached_providers" in cached and isinstance(cached["cached_providers"], list):
                providers = set(p.lower() for p in cached["cached_providers"])
        elif isinstance(cached, list):
            items = cached

        if not providers and items:
            for it in items:
                p_name = self._get_item_provider_name(it)
                if p_name:
                    providers.add(p_name)

        return items, pagination, providers

    async def _orchestrate_search(
        self,
        service_name: str,
        query: Any,
        crawler_method_name: str,
        result_cls: Any,
        sort_key_fn: Any,
        use_cache: bool = True,
        ttl_seconds: int = 600,
        handle_pagination: bool = False,
    ) -> List[Any]:
        cache_key = self._generate_cache_key(service_name, query.model_dump())
        crawlers = crawler_registry.get_crawlers_for_service(service_name, query.providers)

        # Fast path if no crawlers registered (e.g. registry cleared in unit test)
        if not crawlers:
            if use_cache:
                cached = await self.cache.get_json(cache_key)
                if cached:
                    items, pagination, _ = self._unpack_cache_payload(cached)
                    filtered_items = [
                        it for it in items
                        if self.is_provider_cacheable(self._get_item_provider_name(it))
                    ]
                    validated = [result_cls.model_validate(it) for it in filtered_items]
                    if handle_pagination:
                        if pagination:
                            try:
                                self.last_pagination = PaginationMeta.model_validate(pagination)
                            except Exception:
                                self.last_pagination = None
                        if not self.last_pagination:
                            self.last_pagination = PaginationMeta(
                                current_page=getattr(query, "page", 1),
                                per_page=18,
                                total_count=len(validated),
                                total_pages=1,
                                has_next_page=False,
                                has_prev_page=getattr(query, "page", 1) > 1,
                            )
                    return validated

            if handle_pagination:
                self.last_pagination = PaginationMeta(
                    current_page=getattr(query, "page", 1),
                    per_page=18,
                    total_count=0,
                    total_pages=1,
                    has_next_page=False,
                    has_prev_page=False,
                )
            return []

        # Check existing cache
        cached_items: List[Any] = []
        cached_providers: Set[str] = set()
        cached_pagination = None

        if use_cache:
            cached = await self.cache.get_json(cache_key)
            if cached:
                raw_items, cached_pagination, providers = self._unpack_cache_payload(cached)
                # CRITICAL: Exclude any non-cacheable provider results (e.g. iranhotel)
                cached_items = [
                    it for it in raw_items
                    if self.is_provider_cacheable(self._get_item_provider_name(it))
                ]
                cached_providers = {
                    p for p in providers
                    if self.is_provider_cacheable(p)
                }

        # Partition crawlers into live vs cached
        live_crawlers: List[BaseCrawler] = []
        for c in crawlers:
            p_name = c.provider_name.lower()
            if not self.is_provider_cacheable(p_name, c):
                # Non-cacheable providers (e.g. iranhotel) MUST always crawl live
                live_crawlers.append(c)
            elif p_name not in cached_providers:
                # Cacheable provider not yet in cache -> crawl live
                live_crawlers.append(c)

        # Run live crawlers in parallel
        live_flattened: List[Any] = []
        new_cacheable_items: List[Any] = []
        new_cached_providers: Set[str] = set()

        if live_crawlers:
            tasks = [getattr(c, crawler_method_name)(query) for c in live_crawlers]
            live_results = await self._run_parallel(tasks, live_crawlers)

            for c, res_list in live_results:
                if isinstance(res_list, list):
                    live_flattened.extend(res_list)
                    if self.is_provider_cacheable(c.provider_name, c):
                        new_cacheable_items.extend(res_list)
                        new_cached_providers.add(c.provider_name.lower())

        # Determine pagination for accommodations
        pagination = None
        if handle_pagination:
            for c in live_crawlers:
                if hasattr(c, "last_pagination") and c.last_pagination is not None:
                    pagination = c.last_pagination
                    break
            if not pagination and cached_pagination:
                try:
                    pagination = PaginationMeta.model_validate(cached_pagination)
                except Exception:
                    pagination = None

        # Update cache if use_cache is True and we have new cacheable results
        if use_cache and (new_cached_providers or (not cached_items and new_cacheable_items)):
            merged_cacheable = [
                (it if isinstance(it, dict) else it.model_dump())
                for it in cached_items
            ] + [it.model_dump() for it in new_cacheable_items]
            merged_providers = list(cached_providers.union(new_cached_providers))

            cache_payload: Dict[str, Any] = {
                "results": merged_cacheable,
                "cached_providers": merged_providers,
            }
            if handle_pagination and (pagination or self.last_pagination):
                active_pag = pagination or self.last_pagination
                cache_payload["pagination"] = active_pag.model_dump() if active_pag else None

            await self.cache.set_json(cache_key, cache_payload, ttl_seconds=ttl_seconds)

        # Merge cached results + live results
        requested_provider_names = {c.provider_name.lower() for c in crawlers}
        cached_validated = [
            result_cls.model_validate(it)
            for it in cached_items
            if self._get_item_provider_name(it) in requested_provider_names
        ]

        all_results = cached_validated + live_flattened
        all_results.sort(key=sort_key_fn)

        if handle_pagination:
            if not pagination:
                pagination = PaginationMeta(
                    current_page=getattr(query, "page", 1),
                    per_page=18,
                    total_count=len(all_results),
                    total_pages=1,
                    has_next_page=False,
                    has_prev_page=getattr(query, "page", 1) > 1,
                )
            self.last_pagination = pagination

        return all_results

    async def search_flights(
        self,
        query: FlightSearchQuery,
        use_cache: bool = True,
        ttl_seconds: int = 600,
    ) -> List[FlightResult]:
        return await self._orchestrate_search(
            service_name="flight",
            query=query,
            crawler_method_name="search_flights",
            result_cls=FlightResult,
            sort_key_fn=lambda x: price_sort_key(getattr(x, "price", None)),
            use_cache=use_cache,
            ttl_seconds=ttl_seconds,
            handle_pagination=False,
        )

    async def search_hotels(
        self,
        query: HotelSearchQuery,
        use_cache: bool = True,
        ttl_seconds: int = 600,
    ) -> List[HotelResult]:
        return await self._orchestrate_search(
            service_name="hotel",
            query=query,
            crawler_method_name="search_hotels",
            result_cls=HotelResult,
            sort_key_fn=lambda x: price_sort_key(getattr(x, "min_price_per_night", None)),
            use_cache=use_cache,
            ttl_seconds=ttl_seconds,
            handle_pagination=False,
        )

    async def search_accommodations(
        self,
        query: AccommodationSearchQuery,
        use_cache: bool = True,
        ttl_seconds: int = 600,
    ) -> List[AccommodationResult]:
        return await self._orchestrate_search(
            service_name="accommodation",
            query=query,
            crawler_method_name="search_accommodations",
            result_cls=AccommodationResult,
            sort_key_fn=lambda x: price_sort_key(getattr(x, "price_per_night", None)),
            use_cache=use_cache,
            ttl_seconds=ttl_seconds,
            handle_pagination=True,
        )

    async def search_transport(
        self,
        query: TransportSearchQuery,
        use_cache: bool = True,
        ttl_seconds: int = 600,
    ) -> List[TransportResult]:
        service_name = query.transport_type.lower()
        return await self._orchestrate_search(
            service_name=service_name,
            query=query,
            crawler_method_name="search_transport",
            result_cls=TransportResult,
            sort_key_fn=lambda x: price_sort_key(getattr(x, "price", None)),
            use_cache=use_cache,
            ttl_seconds=ttl_seconds,
            handle_pagination=False,
        )

    async def get_hotel_rooms(
        self,
        hotel_id: int,
        checkin_date: str,
        checkout_date: str,
        provider: str = "iranhotel",
        use_cache: bool = True,
        ttl_seconds: int = 600,
    ) -> List[RoomOffer]:
        provider_clean = provider.strip().lower()
        is_cacheable = self.is_provider_cacheable(provider_clean)
        cache_key = f"hotel_rooms:{provider_clean}:{hotel_id}:{checkin_date}:{checkout_date}"

        if use_cache and is_cacheable:
            cached = await self.cache.get_json(cache_key)
            if cached:
                return [RoomOffer.model_validate(r) for r in cached]

        crawler = crawler_registry.get_crawler(provider_clean)
        if not crawler:
            raise ValueError(f"Provider '{provider}' not found")

        if not hasattr(crawler, "fetch_hotel_rooms"):
            raise NotImplementedError(f"Provider '{provider}' does not support direct room inventory queries")

        rooms = await crawler.fetch_hotel_rooms(
            hotel_id=hotel_id,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
        )

        if use_cache and rooms and is_cacheable:
            await self.cache.set_json(
                cache_key,
                [r.model_dump() for r in rooms],
                ttl_seconds=ttl_seconds,
            )
        return rooms

    async def get_flight_calendar(
        self,
        origin: str,
        destination: str,
        page: int = 0,
        provider: str = "safarchin",
        use_cache: bool = True,
        ttl_seconds: int = 600,
    ) -> dict:
        provider_clean = provider.strip().lower()
        is_cacheable = self.is_provider_cacheable(provider_clean)
        cache_key = f"flight_calendar:{provider_clean}:{origin.strip().upper()}:{destination.strip().upper()}:{page}"

        if use_cache and is_cacheable:
            cached = await self.cache.get_json(cache_key)
            if cached:
                return cached

        crawler = crawler_registry.get_crawler(provider_clean)
        if not crawler or not hasattr(crawler, "search_calendar"):
            raise ValueError(f"Provider '{provider}' does not support calendar search")

        calendar_data = await crawler.search_calendar(origin=origin, destination=destination, page=page)
        if use_cache and calendar_data and is_cacheable:
            await self.cache.set_json(
                cache_key,
                calendar_data,
                ttl_seconds=ttl_seconds,
            )
        return calendar_data

    async def get_provinces(
        self,
        provider: str = "jajiga",
        use_cache: bool = True,
        ttl_seconds: int = 86400,  # 24 hours
    ) -> List[ProvinceItem]:
        """Fetch list of supported provinces for a given provider with Redis caching."""
        provider_clean = provider.strip().lower()
        cache_key = f"location_provinces:{provider_clean}"
        is_cacheable = self.is_provider_cacheable(provider_clean)
        if use_cache and is_cacheable:
            cached = await self.cache.get_json(cache_key)
            if cached:
                return [ProvinceItem.model_validate(p) for p in cached]

        crawler = crawler_registry.get_crawler(provider_clean)
        if not crawler:
            raise ValueError(f"Provider '{provider}' not found")

        provinces = await crawler.get_provinces()
        if use_cache and provinces and is_cacheable:
            await self.cache.set_json(
                cache_key,
                [p.model_dump() for p in provinces],
                ttl_seconds=ttl_seconds,
            )
        return provinces

    async def get_cities(
        self,
        provider: str = "jajiga",
        province_id: Optional[str] = None,
        use_cache: bool = True,
        ttl_seconds: int = 86400,  # 24 hours
    ) -> List[CityItem]:
        """Fetch list of cities (optionally filtered by province) for a provider with Redis caching."""
        provider_clean = provider.strip().lower()
        prov_key = province_id or "all"
        cache_key = f"location_cities:{provider_clean}:{prov_key}"
        is_cacheable = self.is_provider_cacheable(provider_clean)
        if use_cache and is_cacheable:
            cached = await self.cache.get_json(cache_key)
            if cached:
                return [CityItem.model_validate(c) for c in cached]

        crawler = crawler_registry.get_crawler(provider_clean)
        if not crawler:
            raise ValueError(f"Provider '{provider}' not found")

        cities = await crawler.get_cities(province_id=province_id)
        if use_cache and cities and is_cacheable:
            await self.cache.set_json(
                cache_key,
                [c.model_dump() for c in cities],
                ttl_seconds=ttl_seconds,
            )
        return cities

    async def _run_parallel(self, tasks: list, crawlers: List[BaseCrawler]) -> List[tuple]:
        """
        Run tasks concurrently with per-provider timeout and error resilience.

        Returns (crawler, results) pairs rather than a positional list, so a
        provider that fails can never shift another provider's results onto the
        wrong crawler during cache attribution.
        """
        if not tasks:
            return []

        async def _run_one(index: int, task) -> tuple:
            crawler = crawlers[index]
            provider_name = crawler.provider_name
            try:
                results = await asyncio.wait_for(task, timeout=self._timeout_for(provider_name))
            except asyncio.TimeoutError:
                logger.error(
                    f"Provider {provider_name} exceeded its {self._timeout_for(provider_name)}s "
                    f"time budget and was dropped"
                )
                return (crawler, None)
            except Exception as e:
                logger.error(f"Provider {provider_name} failed with error: {e}")
                return (crawler, None)
            return (crawler, results)

        gathered = await asyncio.gather(
            *(_run_one(i, t) for i, t in enumerate(tasks)), return_exceptions=True
        )

        paired: List[tuple] = []
        for entry in gathered:
            if isinstance(entry, BaseException):
                # gather itself failed (e.g. cancelled); cannot attribute safely
                logger.error(f"Crawl task failed unexpectedly: {entry}")
                continue
            crawler, results = entry
            if results is None:
                continue
            paired.append((crawler, results))
        return paired
