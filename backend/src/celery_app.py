"""Celery application configuration for background tasks."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from src.core.config import settings

celery_app = Celery(
    "career_scout",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["src.tasks.scraper_tasks"],
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
            "task": "src.tasks.scraper_tasks.scrape_linkedin_jobs",
            "schedule": crontab(hour=9, minute=0),
            "args": ("Software Engineer", "Brisbane, Australia", 10),
        }
    },
)

__all__ = ["celery_app"]
