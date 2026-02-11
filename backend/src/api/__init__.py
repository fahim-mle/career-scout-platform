from fastapi import APIRouter

from src.api.v1 import health_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
