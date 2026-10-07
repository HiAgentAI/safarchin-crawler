import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from app.api.deps import verify_api_key
from app.db.models import APIKey
from app.schemas.restaurant import RestaurantSearchQuery, RestaurantResult
from app.crawlers.orchestrator import CrawlerOrchestrator
from app.core.redis import resolve_cache_params
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/restaurants", tags=["Restaurants"])

@router.get("/search", response_model=dict)
async def search_restaurants(
    city: str = Query(..., description="City name (e.g. Tehran, Isfahan, Shiraz, اصفهان)"),
    cuisine: Optional[str] = Query(default=None, description="Cuisine type (e.g. iranian, italian, kebab, fast_food)"),
    name: Optional[str] = Query(default=None, description="Filter by restaurant name"),
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=50, ge=1, le=500, description="Items per page"),
    providers: Optional[str] = Query(default=None, description="Comma-separated provider names (e.g. openstreetmap)"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live query"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache TTL in seconds"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Alias for cache_ttl"),
    key: APIKey = Depends(verify_api_key),
):
    """
    Search restaurants within city boundaries using OpenStreetMap (Nominatim + Overpass).
    """
    provider_list = [p.strip().lower() for p in providers.split(",")] if providers else None
    query = RestaurantSearchQuery(
        city=city,
        cuisine=cuisine,
        name=name,
        page=page,
        limit=limit,
        providers=provider_list,
    )

    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=settings.REDIS_CACHE_TTL_SECONDS,
    )

    orchestrator = CrawlerOrchestrator()
    try:
        results = await orchestrator.search_restaurants(query, use_cache=use_cache, ttl_seconds=ttl_seconds)
    except Exception as e:
        logger.error(f"Error querying restaurants for city '{city}': {e}")
        raise HTTPException(status_code=502, detail=f"Failed to retrieve restaurants: {str(e)}")

    return {
        "status": "success",
        "city": city,
        "total_results": len(results),
        "page": page,
        "limit": limit,
        "results": [r.model_dump() for r in results],
    }
