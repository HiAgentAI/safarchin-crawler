from fastapi import APIRouter
from app.api.v1.flights import router as flights_router
from app.api.v1.hotels import router as hotels_router
from app.api.v1.accommodations import router as accommodations_router
from app.api.v1.transport import router as transport_router
from app.api.v1.restaurants import router as restaurants_router
from app.api.v1.system import router as system_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(system_router)
api_v1_router.include_router(flights_router)
api_v1_router.include_router(hotels_router)
api_v1_router.include_router(accommodations_router)
api_v1_router.include_router(transport_router)
api_v1_router.include_router(restaurants_router)

