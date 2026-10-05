from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure crawlers are imported and self-registered in CrawlerRegistry
import app.crawlers
from app.api.v1.api import api_v1_router
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application startup logic
    yield
    # Application shutdown logic

app = FastAPI(
    title="Safarchin Travel Crawler API",
    description="Online real-time crawler engine aggregating flights, hotels, accommodations, buses, and trains across Alibaba, FlyToday, and Karnaval.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API V1 Router
app.include_router(api_v1_router)

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to Safarchin Travel Crawler API",
        "docs": "/docs",
        "status": "healthy",
        "providers_endpoint": "/api/v1/providers",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)

