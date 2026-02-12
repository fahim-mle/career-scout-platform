from typing import Any

from fastapi import APIRouter, Depends, Response, status
from loguru import logger

from src.api.deps import get_health_service
from src.core.health import HealthService

router = APIRouter()


@router.get("")
async def health_check(
    response: Response,
    health_service: HealthService = Depends(get_health_service),
) -> dict[str, Any]:
    """Return aggregated dependency health status.

    Args:
        response: FastAPI response object for setting status code.
        health_service: Service that checks dependency health.

    Returns:
        Health payload with overall and per-service status.
    """
    try:
        payload = await health_service.get_health_payload()
    except Exception as exc:
        logger.error("Health endpoint failed", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "services": {},
            "timestamp": "",
            "error": "health check execution failed",
        }

    if payload["status"] == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return payload
