"""Prometheus metrics definitions and helpers."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, cast

from loguru import logger
from prometheus_client import Counter, Gauge, Histogram

_METRICS_CACHE: dict[str, Counter | Gauge | Histogram] = globals().get(
    "_METRICS_CACHE", {}
)


def _get_or_create_counter(
    name: str,
    documentation: str,
    labelnames: tuple[str, ...],
) -> Counter:
    """Return an existing counter or create one.

    Args:
        name: Metric name.
        documentation: Metric help text.
        labelnames: Ordered metric label names.

    Returns:
        Prometheus counter metric.
    """
    cached = _METRICS_CACHE.get(name)
    if cached is not None:
        return cast(Counter, cached)

    try:
        counter = Counter(name=name, documentation=documentation, labelnames=labelnames)
    except ValueError as exc:
        logger.debug(
            "Failed to initialize counter collector", metric=name, error=str(exc)
        )
        raise

    _METRICS_CACHE[name] = counter
    return counter


def _get_or_create_histogram(
    name: str,
    documentation: str,
    labelnames: tuple[str, ...],
) -> Histogram:
    """Return an existing histogram or create one.

    Args:
        name: Metric name.
        documentation: Metric help text.
        labelnames: Ordered metric label names.

    Returns:
        Prometheus histogram metric.
    """
    cached = _METRICS_CACHE.get(name)
    if cached is not None:
        return cast(Histogram, cached)

    try:
        histogram = Histogram(
            name=name, documentation=documentation, labelnames=labelnames
        )
    except ValueError as exc:
        logger.debug(
            "Failed to initialize histogram collector",
            metric=name,
            error=str(exc),
        )
        raise

    _METRICS_CACHE[name] = histogram
    return histogram


def _get_or_create_gauge(
    name: str,
    documentation: str,
    labelnames: tuple[str, ...],
) -> Gauge:
    """Return an existing gauge or create one.

    Args:
        name: Metric name.
        documentation: Metric help text.
        labelnames: Ordered metric label names.

    Returns:
        Prometheus gauge metric.
    """
    cached = _METRICS_CACHE.get(name)
    if cached is not None:
        return cast(Gauge, cached)

    try:
        gauge = Gauge(name=name, documentation=documentation, labelnames=labelnames)
    except ValueError as exc:
        logger.debug(
            "Failed to initialize gauge collector", metric=name, error=str(exc)
        )
        raise

    _METRICS_CACHE[name] = gauge
    return gauge


def _validate_platform(platform: str) -> None:
    """Validate metric platform label.

    Args:
        platform: Platform metric label.

    Raises:
        ValueError: If platform label is empty.
    """
    if not platform or not platform.strip():
        raise ValueError("platform label must be a non-empty string.")


def _validate_status(status: str) -> None:
    """Validate metric scraper status label.

    Args:
        status: Scraper status label.

    Raises:
        ValueError: If status is not one of the supported values.
    """
    allowed_statuses = {"success", "failure", "skipped"}
    if status not in allowed_statuses:
        raise ValueError("status label must be one of: success, failure, skipped.")


def _validate_non_negative(value: float, field_name: str) -> None:
    """Validate non-negative numeric metric values.

    Args:
        value: Metric value to validate.
        field_name: Name of the validated field.

    Raises:
        ValueError: If the value is negative.
    """
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")


jobs_created_total: Counter = _get_or_create_counter(
    name="jobs_created_total",
    documentation="Total number of jobs created, labeled by platform.",
    labelnames=("platform",),
)

db_query_duration_seconds: Histogram = _get_or_create_histogram(
    name="db_query_duration_seconds",
    documentation="Database query duration in seconds, labeled by query type.",
    labelnames=("query_type",),
)

scraper_runs_total: Counter = _get_or_create_counter(
    name="scraper_runs_total",
    documentation="Total scraper runs labeled by platform and status.",
    labelnames=("platform", "status"),
)

scraper_duration_seconds: Histogram = _get_or_create_histogram(
    name="scraper_duration_seconds",
    documentation="Scraper task duration in seconds labeled by platform.",
    labelnames=("platform",),
)

jobs_scraped_total: Counter = _get_or_create_counter(
    name="jobs_scraped_total",
    documentation="Total number of jobs scraped, labeled by platform.",
    labelnames=("platform",),
)

jobs_duplicates_total: Counter = _get_or_create_counter(
    name="jobs_duplicates_total",
    documentation="Total duplicate jobs encountered, labeled by platform.",
    labelnames=("platform",),
)

jobs_errors_total: Counter = _get_or_create_counter(
    name="jobs_errors_total",
    documentation="Total job processing errors, labeled by platform.",
    labelnames=("platform",),
)

jobs_updated_total: Counter = _get_or_create_counter(
    name="jobs_updated_total",
    documentation="Total existing jobs updated, labeled by platform.",
    labelnames=("platform",),
)

enrichment_runs_total: Counter = _get_or_create_counter(
    name="enrichment_runs_total",
    documentation="Total enrichment task runs labeled by platform and status.",
    labelnames=("platform", "status"),
)

enrichment_duration_seconds: Histogram = _get_or_create_histogram(
    name="enrichment_duration_seconds",
    documentation="Enrichment task duration in seconds labeled by platform.",
    labelnames=("platform",),
)

jobs_enriched_total: Counter = _get_or_create_counter(
    name="jobs_enriched_total",
    documentation="Total number of jobs enriched, labeled by platform.",
    labelnames=("platform",),
)

enrichment_errors_total: Counter = _get_or_create_counter(
    name="enrichment_errors_total",
    documentation="Total enrichment task errors, labeled by platform.",
    labelnames=("platform",),
)

jobs_in_database_total: Gauge = _get_or_create_gauge(
    name="jobs_in_database_total",
    documentation="Current known jobs in database for a platform.",
    labelnames=("platform",),
)


def increment_jobs_created(platform: str) -> None:
    """Increment job creation counter for a platform.

    Args:
        platform: Source platform for the created job.

    Raises:
        ValueError: If platform label is empty.
    """
    _validate_platform(platform)

    jobs_created_total.labels(platform=platform).inc()


def increment_scraper_runs(platform: str, status: str) -> None:
    """Increment scraper run counter.

    Args:
        platform: Source platform label.
        status: Run status label, one of success/failure/skipped.

    Raises:
        ValueError: If platform or status labels are invalid.
    """
    _validate_platform(platform)
    _validate_status(status)

    scraper_runs_total.labels(platform=platform, status=status).inc()


def observe_scraper_duration(platform: str, duration_seconds: float) -> None:
    """Observe scraper task duration.

    Args:
        platform: Source platform label.
        duration_seconds: Task runtime in seconds.

    Raises:
        ValueError: If labels or metric values are invalid.
    """
    _validate_platform(platform)
    _validate_non_negative(duration_seconds, "duration_seconds")

    scraper_duration_seconds.labels(platform=platform).observe(duration_seconds)


def increment_jobs_scraped(platform: str, count: int = 1) -> None:
    """Increment scraped jobs counter.

    Args:
        platform: Source platform label.
        count: Number of scraped jobs to add.

    Raises:
        ValueError: If platform label is invalid or count is negative.
    """
    _validate_platform(platform)
    _validate_non_negative(float(count), "count")

    jobs_scraped_total.labels(platform=platform).inc(count)


def increment_jobs_duplicates(platform: str, count: int = 1) -> None:
    """Increment duplicate jobs counter.

    Args:
        platform: Source platform label.
        count: Number of duplicate jobs to add.

    Raises:
        ValueError: If platform label is invalid or count is negative.
    """
    _validate_platform(platform)
    _validate_non_negative(float(count), "count")

    jobs_duplicates_total.labels(platform=platform).inc(count)


def increment_jobs_errors(platform: str, count: int = 1) -> None:
    """Increment jobs error counter.

    Args:
        platform: Source platform label.
        count: Number of failed job writes to add.

    Raises:
        ValueError: If platform label is invalid or count is negative.
    """
    _validate_platform(platform)
    _validate_non_negative(float(count), "count")

    jobs_errors_total.labels(platform=platform).inc(count)


def increment_jobs_updated(platform: str, count: int = 1) -> None:
    """Increment updated jobs counter.

    Args:
        platform: Source platform label.
        count: Number of updated jobs to add.

    Raises:
        ValueError: If platform label is invalid or count is negative.
    """
    _validate_platform(platform)
    _validate_non_negative(float(count), "count")

    jobs_updated_total.labels(platform=platform).inc(count)


def increment_enrichment_runs(platform: str, status: str) -> None:
    """Increment enrichment run counter.

    Args:
        platform: Source platform label.
        status: Run status label, one of success/failure/skipped.

    Raises:
        ValueError: If platform or status labels are invalid.
    """
    _validate_platform(platform)
    _validate_status(status)

    enrichment_runs_total.labels(platform=platform, status=status).inc()


def observe_enrichment_duration(platform: str, duration_seconds: float) -> None:
    """Observe enrichment task duration.

    Args:
        platform: Source platform label.
        duration_seconds: Task runtime in seconds.

    Raises:
        ValueError: If labels or metric values are invalid.
    """
    _validate_platform(platform)
    _validate_non_negative(duration_seconds, "duration_seconds")

    enrichment_duration_seconds.labels(platform=platform).observe(duration_seconds)


def increment_jobs_enriched(platform: str, count: int = 1) -> None:
    """Increment enriched jobs counter.

    Args:
        platform: Source platform label.
        count: Number of enriched jobs to add.

    Raises:
        ValueError: If platform label is invalid or count is negative.
    """
    _validate_platform(platform)
    _validate_non_negative(float(count), "count")

    jobs_enriched_total.labels(platform=platform).inc(count)


def increment_enrichment_errors(platform: str, count: int = 1) -> None:
    """Increment enrichment error counter.

    Args:
        platform: Source platform label.
        count: Number of enrichment errors to add.

    Raises:
        ValueError: If platform label is invalid or count is negative.
    """
    _validate_platform(platform)
    _validate_non_negative(float(count), "count")

    enrichment_errors_total.labels(platform=platform).inc(count)


def set_jobs_in_database(platform: str, total: int) -> None:
    """Set jobs-in-database gauge for platform.

    Args:
        platform: Source platform label.
        total: Known number of jobs currently in database for this scrape run.

    Raises:
        ValueError: If platform label is invalid or total is negative.
    """
    _validate_platform(platform)
    _validate_non_negative(float(total), "total")

    jobs_in_database_total.labels(platform=platform).set(total)


def observe_db_query_duration(query_type: str, duration_seconds: float) -> None:
    """Observe one database query duration value.

    Args:
        query_type: Query category label (example: "insert", "select").
        duration_seconds: Duration in seconds.

    Raises:
        ValueError: If query type is empty or duration is negative.
    """
    if not query_type:
        raise ValueError("query_type label must be a non-empty string.")
    _validate_non_negative(duration_seconds, "duration_seconds")

    db_query_duration_seconds.labels(query_type=query_type).observe(duration_seconds)


@contextmanager
def db_query_timer(query_type: str) -> Iterator[None]:
    """Context manager to track DB query duration.

    Args:
        query_type: Query category label (example: "insert", "select").

    Yields:
        None.
    """
    started_at = time.perf_counter()
    try:
        yield
    finally:
        duration_seconds = time.perf_counter() - started_at
        try:
            observe_db_query_duration(
                query_type=query_type,
                duration_seconds=duration_seconds,
            )
        except ValueError as exc:
            logger.warning(
                "Skipped db query duration metric",
                query_type=query_type,
                duration_seconds=duration_seconds,
                error=str(exc),
            )


__all__ = [
    "enrichment_duration_seconds",
    "enrichment_errors_total",
    "enrichment_runs_total",
    "db_query_duration_seconds",
    "db_query_timer",
    "increment_enrichment_errors",
    "increment_enrichment_runs",
    "increment_jobs_duplicates",
    "increment_jobs_errors",
    "increment_jobs_enriched",
    "increment_jobs_created",
    "increment_jobs_scraped",
    "increment_jobs_updated",
    "increment_scraper_runs",
    "jobs_duplicates_total",
    "jobs_enriched_total",
    "jobs_errors_total",
    "jobs_created_total",
    "jobs_in_database_total",
    "jobs_scraped_total",
    "jobs_updated_total",
    "observe_enrichment_duration",
    "observe_db_query_duration",
    "observe_scraper_duration",
    "scraper_duration_seconds",
    "scraper_runs_total",
    "set_jobs_in_database",
]
