"""Prometheus metrics definitions and helpers."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, cast

from loguru import logger
from prometheus_client import REGISTRY, Counter, Histogram

_METRICS_CACHE: dict[str, Counter | Histogram] = globals().get("_METRICS_CACHE", {})


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
        existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
        if existing is not None:
            counter = cast(Counter, existing)
            logger.debug("Reused existing counter collector", metric=name)
        else:
            raise exc

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
        existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
        if existing is not None:
            histogram = cast(Histogram, existing)
            logger.debug("Reused existing histogram collector", metric=name)
        else:
            raise exc

    _METRICS_CACHE[name] = histogram
    return histogram


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


def increment_jobs_created(platform: str) -> None:
    """Increment job creation counter for a platform.

    Args:
        platform: Source platform for the created job.

    Raises:
        ValueError: If platform label is empty.
    """
    if not platform:
        raise ValueError("platform label must be a non-empty string.")

    jobs_created_total.labels(platform=platform).inc()


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
    if duration_seconds < 0:
        raise ValueError("duration_seconds cannot be negative.")

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
    "db_query_duration_seconds",
    "db_query_timer",
    "increment_jobs_created",
    "jobs_created_total",
    "observe_db_query_duration",
]
