"""Infrastructure health checks for core dependencies."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Literal

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.db.session import engine

ServiceStatus = Literal["healthy", "unhealthy"]


class HealthService:
    """Run health checks for backend infrastructure dependencies."""

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        """Initialize health service settings.

        Args:
            timeout_seconds: Max time to wait for each dependency check.
        """
        self.timeout_seconds = timeout_seconds

    async def get_health_payload(self) -> dict[str, Any]:
        """Build aggregated health status for API responses.

        Returns:
            Dictionary containing overall status, timestamp, and per-service details.
        """
        database_status, redis_status = await asyncio.gather(
            self._check_database(),
            self._check_redis(),
        )
        api_status = self._check_api()
        overall_status: ServiceStatus = (
            "healthy"
            if database_status["status"] == "healthy"
            and redis_status["status"] == "healthy"
            and api_status["status"] == "healthy"
            else "unhealthy"
        )

        return {
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {
                "database": database_status,
                "redis": redis_status,
                "api": api_status,
            },
        }

    @staticmethod
    def _check_api() -> dict[str, Any]:
        """Return API status metadata for health payload."""
        return {
            "status": "healthy",
            "version": settings.VERSION,
        }

    async def _check_database(self) -> dict[str, Any]:
        """Validate database connectivity and measure response time.

        Returns:
            Dictionary with status, response time in milliseconds, and optional error.
        """
        started_at = perf_counter()

        try:
            await asyncio.wait_for(self._ping_database(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            response_time_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.error(
                "Database health check timed out",
                timeout_seconds=self.timeout_seconds,
                response_time_ms=response_time_ms,
            )
            return {
                "status": "unhealthy",
                "response_time_ms": response_time_ms,
                "error": f"timeout after {self.timeout_seconds}s",
            }
        except SQLAlchemyError as exc:
            response_time_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.error(
                "Database health check failed",
                response_time_ms=response_time_ms,
                error=str(exc),
            )
            return {
                "status": "unhealthy",
                "response_time_ms": response_time_ms,
                "error": str(exc),
            }

        response_time_ms = round((perf_counter() - started_at) * 1000, 2)
        return {
            "status": "healthy",
            "response_time_ms": response_time_ms,
        }

    async def _check_redis(self) -> dict[str, Any]:
        """Validate Redis connectivity and measure response time.

        Returns:
            Dictionary with status, response time in milliseconds, and optional error.
        """
        started_at = perf_counter()
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

        try:
            await asyncio.wait_for(redis_client.ping(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            response_time_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.error(
                "Redis health check timed out",
                timeout_seconds=self.timeout_seconds,
                response_time_ms=response_time_ms,
                redis_url=settings.REDIS_URL,
            )
            return {
                "status": "unhealthy",
                "response_time_ms": response_time_ms,
                "error": f"timeout after {self.timeout_seconds}s",
            }
        except RedisError as exc:
            response_time_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.error(
                "Redis health check failed",
                response_time_ms=response_time_ms,
                redis_url=settings.REDIS_URL,
                error=str(exc),
            )
            return {
                "status": "unhealthy",
                "response_time_ms": response_time_ms,
                "error": str(exc),
            }
        finally:
            await redis_client.aclose()

        response_time_ms = round((perf_counter() - started_at) * 1000, 2)
        return {
            "status": "healthy",
            "response_time_ms": response_time_ms,
        }

    @staticmethod
    async def _ping_database() -> None:
        """Execute lightweight query to validate database availability.

        Returns:
            None.

        Raises:
            SQLAlchemyError: If the query cannot be executed.
        """
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
