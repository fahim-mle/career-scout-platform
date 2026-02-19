"""API router aggregation for all versioned endpoints."""

from fastapi import APIRouter

from src.api.v1 import health_router, jobs_router, profile_router, raw_jobs_router

v1_router = APIRouter()
v1_router.include_router(health_router, prefix="/health", tags=["health"])
v1_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
v1_router.include_router(raw_jobs_router, tags=["jobs"])
v1_router.include_router(profile_router, prefix="/profile", tags=["profile"])

api_router = APIRouter()


@api_router.get("/", tags=["root"])
async def api_root() -> dict[str, str]:
    """Return API root metadata for the mounted version.

    Returns:
        A simple readiness payload for API root checks.
    """
    return {"status": "ok", "message": "Career Scout API"}


api_router.include_router(v1_router)

__all__ = ["api_router", "v1_router"]
