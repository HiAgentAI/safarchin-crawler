import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from app.api.deps import verify_api_key
from app.db.models import APIKey
from app.schemas.accommodation import (
    AccommodationSearchQuery,
    PaginationMeta,
    ProvincesResponse,
    CitiesResponse,
)
from app.crawlers.orchestrator import CrawlerOrchestrator
from app.core.redis import resolve_cache_params
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accommodations", tags=["Accommodations & Villas"])

@router.get("/search", response_model=dict)
async def search_accommodations(
    city: str = Query(..., description="Destination city or region (e.g. Ramsar, Kish, Tehran, سوادکوه)"),
    checkin_date: str = Query(..., description="Check-in date (YYYY-MM-DD or Jalali 1405-07-24)"),
    checkout_date: str = Query(..., description="Check-out date (YYYY-MM-DD or Jalali 1405-07-26)"),
    guests: int = Query(default=2, ge=1, le=50),
    property_type: Optional[str] = Query(default=None, description="villa, cottage, wooden_cottage, swiss_cottage, apartment, suite, ruralhome, ecolog"),
    min_price: Optional[int] = Query(default=None, description="Minimum price per night in Tomans"),
    max_price: Optional[int] = Query(default=None, description="Maximum price per night in Tomans"),
    amenities: Optional[str] = Query(default=None, description="Comma-separated amenities, e.g. pool,jacuzzi,parking,wifi"),
    sort_by: Optional[str] = Query(default="popularity", description="Sort by: popularity, low_price, high_price, rating, newest"),
    page: int = Query(default=1, ge=1, description="Page number for pagination"),
    providers: Optional[str] = Query(default=None, description="Comma-separated provider names, e.g. jajiga"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live scrape"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    provider_list = [p.strip().lower() for p in providers.split(",")] if providers else None

    amenities_list = [a.strip().lower() for a in amenities.split(",")] if amenities else None
    query = AccommodationSearchQuery(
        city=city,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        guests=guests,
        property_type=property_type,
        min_price=min_price,
        max_price=max_price,
        amenities=amenities_list,
        sort_by=sort_by,
        page=page,
        providers=provider_list,
    )

    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=settings.REDIS_CACHE_TTL_SECONDS,
    )

    orchestrator = CrawlerOrchestrator()
    results = await orchestrator.search_accommodations(query, use_cache=use_cache, ttl_seconds=ttl_seconds)

    pagination = orchestrator.last_pagination or PaginationMeta(
        current_page=page,
        per_page=18,
        total_count=len(results),
        total_pages=1,
        has_next_page=False,
        has_prev_page=page > 1,
    )

    return {
        "status": "success",
        "total_results": len(results),
        "pagination": pagination.model_dump(),
        "results": [r.model_dump() for r in results],
    }


@router.get("/provinces", response_model=ProvincesResponse)
async def get_provinces(
    provider: str = Query(default="jajiga", description="Target provider (e.g. jajiga)"),
    no_cache: bool = Query(default=False, description="Bypass Redis cache"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    """
    Fetch list of provinces with room counts for a specific accommodation provider.
    """
    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=86400,
    )
    orchestrator = CrawlerOrchestrator()
    try:
        provinces = await orchestrator.get_provinces(provider=provider, use_cache=use_cache, ttl_seconds=ttl_seconds)
        return ProvincesResponse(
            status="success",
            provider=provider,
            total=len(provinces),
            provinces=provinces,
        )
    except NotImplementedError:
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' does not support province listing")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch provinces for {provider}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch provinces from {provider}: {str(e)}")


@router.get("/cities", response_model=CitiesResponse)
async def get_cities(
    provider: str = Query(default="jajiga", description="Target provider (e.g. jajiga)"),
    province_id: Optional[str] = Query(default=None, description="Province ID (e.g. 'p24' for Gilan, 'p26' for Mazandaran)"),
    no_cache: bool = Query(default=False, description="Bypass Redis cache"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    """
    Fetch list of cities/districts (optionally filtered by parent province ID) for an accommodation provider.
    """
    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=86400,
    )
    orchestrator = CrawlerOrchestrator()
    try:
        cities = await orchestrator.get_cities(provider=provider, province_id=province_id, use_cache=use_cache, ttl_seconds=ttl_seconds)
        return CitiesResponse(
            status="success",
            provider=provider,
            province_id=province_id,
            total=len(cities),
            cities=cities,
        )
    except NotImplementedError:
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' does not support city listing")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch cities for {provider}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch cities from {provider}: {str(e)}")

