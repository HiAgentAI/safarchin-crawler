from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.api.deps import verify_api_key
from app.db.models import APIKey
from app.schemas.transport import TransportSearchQuery
from app.crawlers.orchestrator import CrawlerOrchestrator
from app.core.redis import resolve_cache_params
from app.core.config import settings

router = APIRouter(prefix="/transport", tags=["Ground Transport (Bus & Train)"])

@router.get("/buses", response_model=dict)
async def search_buses(
    origin: str = Query(..., description="Origin city (e.g. Tehran, Isfahan)"),
    destination: str = Query(..., description="Destination city (e.g. Shiraz, Tabriz)"),
    depart_date: str = Query(..., description="Departure date (YYYY-MM-DD or Jalali)"),
    passengers: int = Query(default=1, ge=1, le=20),
    providers: Optional[str] = Query(default=None, description="Comma-separated provider names, e.g. flytoday"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live scrape"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    provider_list = [p.strip().lower() for p in providers.split(",")] if providers else None
    query = TransportSearchQuery(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        transport_type="bus",
        passengers=passengers,
        providers=provider_list,
    )

    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=settings.REDIS_CACHE_TTL_SECONDS,
    )

    orchestrator = CrawlerOrchestrator()
    results = await orchestrator.search_transport(query, use_cache=use_cache, ttl_seconds=ttl_seconds)

    return {
        "status": "success",
        "total_results": len(results),
        "results": [r.model_dump() for r in results],
    }

@router.get("/trains", response_model=dict)
async def search_trains(
    origin: str = Query(..., description="Origin city (e.g. Tehran, Mashhad)"),
    destination: str = Query(..., description="Destination city (e.g. Tabriz, Isfahan)"),
    depart_date: str = Query(..., description="Departure date (YYYY-MM-DD or Jalali)"),
    passengers: int = Query(default=1, ge=1, le=20),
    providers: Optional[str] = Query(default=None, description="Comma-separated provider names, e.g. flytoday"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live scrape"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    provider_list = [p.strip().lower() for p in providers.split(",")] if providers else None
    query = TransportSearchQuery(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        transport_type="train",
        passengers=passengers,
        providers=provider_list,
    )

    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=settings.REDIS_CACHE_TTL_SECONDS,
    )

    orchestrator = CrawlerOrchestrator()
    results = await orchestrator.search_transport(query, use_cache=use_cache, ttl_seconds=ttl_seconds)

    return {
        "status": "success",
        "total_results": len(results),
        "results": [r.model_dump() for r in results],
    }
