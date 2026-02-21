"""Tests for Celery beat schedule configuration."""

from celery.schedules import crontab

from src.celery_app import celery_app


def test_seek_scrape_schedule_uses_four_hour_cadence_without_overlap() -> None:
    """Seek beat schedule runs every four hours in its own minute window."""
    beat_schedule = celery_app.conf.beat_schedule
    seek_entry = beat_schedule["seek-scrape-every-4h"]

    assert seek_entry["task"] == "src.tasks.scraper_tasks.scrape_seek_jobs"
    assert seek_entry["schedule"] == crontab(hour="*/4", minute=50)
    assert seek_entry["kwargs"] == {
        "query": "Software Engineer",
        "location": "Brisbane QLD",
        "limit": 10,
    }

    assert seek_entry["schedule"] != crontab(hour="*/4", minute=0)
    assert seek_entry["schedule"] != crontab(hour="*/4", minute=20)
    assert seek_entry["schedule"] != crontab(hour="*/4", minute=40)
