"""Tests for Celery beat schedule configuration."""

from celery.schedules import crontab

from src.celery_app import celery_app


def test_linkedin_scrape_schedule_runs_on_the_hour_every_four_hours() -> None:
    """LinkedIn beat schedule remains at minute 00 every four hours."""
    beat_schedule = celery_app.conf.beat_schedule
    linkedin_entry = beat_schedule["linkedin-scrape-every-4h"]

    assert (
        linkedin_entry["task"] == "src.tasks.scraper_tasks.scrape_linkedin_profile_set"
    )
    assert linkedin_entry["schedule"] == crontab(hour="*/4", minute=0)


def test_seek_scrape_schedule_uses_four_hour_cadence_with_15_minute_offset() -> None:
    """Seek beat schedule runs every four hours, 15 minutes after LinkedIn."""
    beat_schedule = celery_app.conf.beat_schedule
    seek_entry = beat_schedule["seek-scrape-every-4h"]

    assert seek_entry["task"] == "src.tasks.scraper_tasks.scrape_seek_profile_set"
    assert seek_entry["schedule"] == crontab(hour="*/4", minute=15)

    assert seek_entry["schedule"] != crontab(hour="*/4", minute=0)
    assert seek_entry["schedule"] != crontab(hour="*/4", minute=30)


def test_indeed_scrape_schedule_uses_four_hour_cadence_with_15_minute_offset() -> None:
    """Indeed beat schedule runs every four hours, 15 minutes after Seek."""
    beat_schedule = celery_app.conf.beat_schedule
    indeed_entry = beat_schedule["indeed-scrape-every-4h"]

    assert indeed_entry["task"] == "src.tasks.scraper_tasks.scrape_indeed_profile_set"
    assert indeed_entry["schedule"] == crontab(hour="*/4", minute=30)

    assert indeed_entry["schedule"] != crontab(hour="*/4", minute=0)
    assert indeed_entry["schedule"] != crontab(hour="*/4", minute=15)
