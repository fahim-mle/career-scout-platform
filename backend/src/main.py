"""FastAPI application setup for the backend service."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api import api_router
from src.api.deps import get_request_id as _get_request_id
from src.core.config import settings
from src.core.logging import setup_logging

setup_logging(settings.LOG_LEVEL)


async def request_logging_middleware(request: Request, call_next: Any) -> Response:
    """Log inbound requests with unique id and duration.

    Args:
        request: Incoming HTTP request.
        call_next: FastAPI middleware continuation callable.

    Returns:
        Response produced by downstream middleware/route handlers.

    Raises:
        Exception: Re-raises downstream exceptions after logging context.
    """
    request_id = str(uuid4())
    request.state.request_id = request_id
    started_at = time.perf_counter()

    logger.info(
        "Request started",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.error(
            "Request failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            error=str(exc),
        )
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "Request completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Return a clean JSON response for HTTP exceptions.

    Args:
        request: Active incoming request.
        exc: Raised HTTP exception.

    Returns:
        JSONResponse payload with error detail and request id.
    """
    request_id = _get_request_id(request)
    detail = (
        exc.detail if isinstance(exc.detail, (str, list, dict)) else "Request failed"
    )
    logger.warning(
        "HTTP exception raised",
        request_id=request_id,
        status_code=exc.status_code,
        detail=detail,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "request_id": request_id},
        headers=exc.headers,
    )


async def handle_validation_exception(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return standardized JSON for validation errors.

    Args:
        request: Active incoming request.
        exc: Validation error raised by FastAPI.

    Returns:
        JSONResponse payload with validation details and request id.
    """
    request_id = _get_request_id(request)
    sanitized_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        copied_error = deepcopy(error)
        copied_error.pop("input", None)
        sanitized_errors.append(copied_error)

    logger.warning(
        "Validation exception raised",
        request_id=request_id,
        path=request.url.path,
        errors=sanitized_errors,
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation failed",
            "errors": sanitized_errors,
            "request_id": request_id,
        },
    )


async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    """Return standardized JSON for unhandled exceptions.

    Args:
        request: Active incoming request.
        exc: Unhandled exception.

    Returns:
        JSONResponse payload with generic error detail and request id.
    """
    request_id = _get_request_id(request)
    logger.exception(
        "Unhandled exception",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        debug=settings.DEBUG,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    )

    app.middleware("http")(request_logging_middleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_exception)
    app.add_exception_handler(Exception, handle_unexpected_exception)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    logger.info(
        "Application configured",
        environment=settings.ENVIRONMENT,
        api_prefix=settings.API_V1_PREFIX,
    )
    return app


app = create_app()
