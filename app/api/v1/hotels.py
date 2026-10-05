import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from app.api.deps import verify_api_key
from app.db.models import APIKey
from app.schemas.hotel import HotelSearchQuery, RoomOffer
from app.schemas.accommodation import ProvincesResponse, CitiesResponse
from app.crawlers.orchestrator import CrawlerOrchestrator
from app.crawlers.registry import crawler_registry
from app.core.redis import resolve_cache_params
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hotels", tags=["Hotels"])

@router.get("/search", response_model=dict)
async def search_hotels(
    city: str = Query(..., description="Destination city name or code (e.g. Tehran, Kish, Shiraz, mashhad)"),
    checkin_date: str = Query(..., description="Check-in date (YYYY-MM-DD or Jalali YYYY/MM/DD)"),
    checkout_date: str = Query(..., description="Check-out date (YYYY-MM-DD or Jalali YYYY/MM/DD)"),
    rooms: int = Query(default=1, ge=1, le=10),
    adults: int = Query(default=2, ge=1, le=20),
    stars: Optional[int] = Query(default=None, ge=1, le=5, description="Filter by star rating (1 to 5)"),
    min_price: Optional[int] = Query(default=None, description="Minimum price per night in IRR"),
    max_price: Optional[int] = Query(default=None, description="Maximum price per night in IRR"),
    sort_by: Optional[str] = Query(default=None, description="Sort criteria (e.g. price_asc, price_desc, rate)"),
    page: int = Query(default=1, ge=1, description="Page number for pagination"),
    providers: Optional[str] = Query(default=None, description="Comma-separated provider names (e.g. iranhotel,alibaba,flytoday)"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live scrape"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    """
    Search hotels across aggregated providers with date range, guest capacity, and star filtering.
    """
    provider_list = [p.strip().lower() for p in providers.split(",")] if providers else None
    query = HotelSearchQuery(
        city=city,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        rooms=rooms,
        adults=adults,
        stars=stars,
        min_price=min_price,
        max_price=max_price,
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
    results = await orchestrator.search_hotels(query, use_cache=use_cache, ttl_seconds=ttl_seconds)

    return {
        "status": "success",
        "total_results": len(results),
        "results": [r.model_dump() for r in results],
    }


@router.get("/rooms", response_model=dict)
async def get_hotel_rooms(
    hotel_id: int = Query(..., description="Hotel ID (e.g. 149 for Parsian Azadi, 465 for Toranj Kish)"),
    checkin_date: str = Query(..., description="Check-in date (YYYY-MM-DD or Jalali YYYY/MM/DD)"),
    checkout_date: str = Query(..., description="Check-out date (YYYY-MM-DD or Jalali YYYY/MM/DD)"),
    provider: str = Query(default="iranhotel", description="Provider name (default: iranhotel)"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live scrape"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    """
    Fetch real-time room types, bed capacities, meal plans, cancellation policies, and discounted rates.
    Note: Real-time inventory from providers like Iran Hotel is never cached.
    """
    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=settings.REDIS_CACHE_TTL_SECONDS,
    )
    orchestrator = CrawlerOrchestrator()
    try:
        rooms = await orchestrator.get_hotel_rooms(
            hotel_id=hotel_id,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            provider=provider,
            use_cache=use_cache,
            ttl_seconds=ttl_seconds,
        )
        return {
            "status": "success",
            "provider": provider,
            "hotel_id": hotel_id,
            "total_rooms": len(rooms),
            "rooms": [r.model_dump() for r in rooms],
        }
    except NotImplementedError:
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' does not support direct room inventory queries")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch hotel rooms for {provider}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch hotel rooms from {provider}: {str(e)}")


@router.get("/provinces", response_model=ProvincesResponse)
async def get_hotel_provinces(
    provider: str = Query(default="iranhotel", description="Target provider (default: iranhotel)"),
    no_cache: bool = Query(default=False, description="Bypass Redis cache"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    """
    Fetch list of provinces supported by the hotel provider.
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
        logger.error(f"Failed to fetch hotel provinces for {provider}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch provinces from {provider}: {str(e)}")


@router.get("/cities", response_model=CitiesResponse)
async def get_hotel_cities(
    provider: str = Query(default="iranhotel", description="Target provider (default: iranhotel)"),
    province_id: Optional[str] = Query(default=None, description="Optional parent province ID (e.g. 8 for Tehran, 11 for Khorasan)"),
    no_cache: bool = Query(default=False, description="Bypass Redis cache"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    """
    Fetch list of cities (optionally filtered by province ID) for the hotel provider.
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
        logger.error(f"Failed to fetch hotel cities for {provider}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch cities from {provider}: {str(e)}")
