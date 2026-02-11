"""FastAPI application entry point."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.core.config import settings


def _load_api_router() -> APIRouter:
    """Load the API router, defaulting to an empty router.

    Returns:
        APIRouter: Router instance for versioned API.
    """
    try:
        from src.api import api_router

        return api_router
    except ImportError:
        logger.warning("API router not found; using empty router")
        return APIRouter()
    except Exception:
        logger.exception(
            "Unexpected error loading API router; falling back to empty router"
        )
        return APIRouter()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI app instance.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        debug=settings.DEBUG,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    )

    if settings.CORS_ORIGINS:
        allow_credentials = "*" not in settings.CORS_ORIGINS
        if not allow_credentials:
            logger.warning(
                "CORS_ORIGINS contains wildcard '*'; disabling credentialed CORS for security"
            )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    api_router = _load_api_router()
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    logger.info(
        f"Application configured (env={settings.ENVIRONMENT}, prefix={settings.API_V1_PREFIX})"
    )
    return app


app = create_app()
