from fastapi import APIRouter
from app.crawlers.registry import crawler_registry

router = APIRouter(tags=["System & Providers"])

@router.get("/providers", response_model=dict)
async def list_providers():
    """List all registered crawler providers and the services they support."""
    providers = crawler_registry.list_providers()
    return {
        "status": "success",
        "count": len(providers),
        "providers": providers,
    }

@router.get("/health", response_model=dict)
async def health_status():
    """Overall system health check."""
    return {
        "status": "healthy",
        "service": "safarchin_crawler",
        "version": "1.0.0",
    }
