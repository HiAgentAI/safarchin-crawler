from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from app.api.deps import verify_api_key
from app.db.models import APIKey
from app.schemas.flight import FlightSearchQuery, FlightResult
from app.crawlers.orchestrator import CrawlerOrchestrator
from app.core.redis import resolve_cache_params
from app.core.config import settings

router = APIRouter(prefix="/flights", tags=["Flights"])

@router.get("/search", response_model=dict)
async def search_flights(
    origin: str = Query(..., description="Origin city code or name (e.g. THR, Mashhad)"),
    destination: str = Query(..., description="Destination city code or name (e.g. MHD, Kish)"),
    depart_date: str = Query(..., description="Departure date (YYYY-MM-DD or Jalali)"),
    return_date: Optional[str] = Query(default=None, description="Return date for round-trip"),
    adults: int = Query(default=1, ge=1, le=9),
    children: int = Query(default=0, ge=0, le=9),
    infants: int = Query(default=0, ge=0, le=9),
    cabin_class: Optional[str] = Query(default="economy"),
    providers: Optional[str] = Query(default=None, description="Comma-separated provider names, e.g. alibaba,flytoday"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live scrape"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    provider_list = [p.strip().lower() for p in providers.split(",")] if providers else None
    query = FlightSearchQuery(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        return_date=return_date,
        adults=adults,
        children=children,
        infants=infants,
        cabin_class=cabin_class,
        providers=provider_list,
    )

    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=settings.REDIS_CACHE_TTL_SECONDS,
    )

    orchestrator = CrawlerOrchestrator()
    results = await orchestrator.search_flights(query, use_cache=use_cache, ttl_seconds=ttl_seconds)

    return {
        "status": "success",
        "total_results": len(results),
        "results": [r.model_dump() for r in results],
    }

@router.get("/calendar", response_model=dict)
async def get_flight_calendar(
    origin: str = Query(..., description="Origin city code or name (e.g. THR, Tehran)"),
    destination: str = Query(..., description="Destination city code or name (e.g. MHD, Mashhad)"),
    page: int = Query(default=0, ge=0, description="Page offset for 15-day chunks (0=first 15 days, 1=next 15 days)"),
    no_cache: bool = Query(default=False, description="Bypass cache and force live scrape"),
    cache_ttl: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (defined by caller)"),
    cache_time: Optional[int] = Query(default=None, ge=0, description="Cache time-to-live in seconds (alias for cache_ttl)"),
    key: APIKey = Depends(verify_api_key),
):
    use_cache, ttl_seconds = resolve_cache_params(
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        cache_time=cache_time,
        default_ttl=settings.REDIS_CACHE_TTL_SECONDS,
    )
    orchestrator = CrawlerOrchestrator()
    try:
        calendar_data = await orchestrator.get_flight_calendar(
            origin=origin,
            destination=destination,
            page=page,
            use_cache=use_cache,
            ttl_seconds=ttl_seconds,
        )
        return {
            "status": "success",
            "data": calendar_data,
        }
    except Exception as e:
        return {"status": "error", "message": f"Safarchin calendar service not available: {str(e)}"}

@router.get("/airports", response_model=dict)
async def list_airports(
    query: Optional[str] = Query(default=None, description="Optional search filter by city or code"),
    key: APIKey = Depends(verify_api_key),
):
    from app.crawlers.safarchin.airports import AIRPORTS
    results = []
    q_lower = query.lower().strip() if query else None
    
    for ap in AIRPORTS:
        if q_lower:
            match = (
                q_lower in ap.english_name.lower()
                or q_lower in ap.persian_name
                or (ap.iata and q_lower in ap.iata.lower())
                or q_lower in ap.id
            )
            if not match:
                continue
        results.append({
            "id": ap.id,
            "slug": ap.slug,
            "iata": ap.iata if ap.iata != "همه" else None,
            "persian_name": ap.persian_name,
            "english_name": ap.english_name,
        })
        
    return {
        "status": "success",
        "total": len(results),
        "airports": results,
    }
