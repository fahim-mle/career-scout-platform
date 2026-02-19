"""Celery application configuration for background tasks."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready
from loguru import logger
from prometheus_client import start_http_server

from src.core.config import settings

_metrics_server_started = False

celery_app = Celery(
    "career_scout",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["src.tasks.scraper_tasks", "src.tasks.enrichment_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=30 * 60,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "daily-linkedin-scrape": {
            "task": "src.tasks.scraper_tasks.scrape_linkedin_profile_set",
            "schedule": crontab(hour=9, minute=0),
        },
        "daily-linkedin-enrichment-backup": {
            "task": "src.tasks.enrichment_tasks.enrich_unstructured_jobs_task",
            "schedule": crontab(hour=10, minute=0),
            "kwargs": {"platform": "linkedin"},
        },
    },
)


@worker_ready.connect
def start_worker_metrics_server(**_: object) -> None:
    """Start Prometheus metrics endpoint once per worker process lifecycle."""
    global _metrics_server_started

    if _metrics_server_started:
        return

    metrics_port = int(os.getenv("SCRAPER_METRICS_PORT", "9101"))
    start_http_server(metrics_port)
    _metrics_server_started = True
    logger.info("Started Celery metrics server", port=metrics_port)


__all__ = ["celery_app"]
