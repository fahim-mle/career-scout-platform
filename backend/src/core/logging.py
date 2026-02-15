"""Centralized Loguru configuration for backend services."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import settings

LOG_DIR = Path("logs")
MAX_LOG_FILE_BYTES = 500 * 1024 * 1024


def _daily_or_size_rotation(message: Any, file: Any) -> bool:
    """Rotate when date changes or file exceeds 500MB.

    Args:
        message: Loguru message object.
        file: Active file handle managed by Loguru.

    Returns:
        ``True`` when the sink should rotate.
    """
    record_time = message.record["time"]
    current_file_date = Path(file.name).stem.split("_")[-1]
    if record_time.strftime("%Y-%m-%d") != current_file_date:
        return True
    return file.tell() >= MAX_LOG_FILE_BYTES


def setup_logging(log_level: str = "INFO") -> None:
    """Configure console and file logging for all environments.

    Args:
        log_level: Minimum level for application logs.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.configure(
        extra={
            "request_id": "-",
            "method": "-",
            "path": "-",
            "status_code": "-",
        }
    )

    effective_level = "DEBUG" if settings.DEBUG else log_level.upper()

    logger.add(
        sys.stdout,
        level=effective_level,
        colorize=True,
        enqueue=True,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "req=<magenta>{extra[request_id]}</magenta> "
            "method=<cyan>{extra[method]}</cyan> "
            "path=<cyan>{extra[path]}</cyan> "
            "status=<cyan>{extra[status_code]}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    logger.add(
        LOG_DIR / "app_{time:YYYY-MM-DD}.log",
        level=effective_level,
        rotation=_daily_or_size_rotation,
        retention="30 days",
        compression="zip",
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | "
            "request_id={extra[request_id]} method={extra[method]} "
            "path={extra[path]} status={extra[status_code]} - {message}"
        ),
    )

    logger.add(
        LOG_DIR / "errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation="100 MB",
        retention="90 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=settings.DEBUG,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | "
            "request_id={extra[request_id]} method={extra[method]} "
            "path={extra[path]} status={extra[status_code]} - {message}"
        ),
    )


__all__ = ["setup_logging"]
