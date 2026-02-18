"""Business logic service for job description skills enrichment."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.exceptions import BusinessLogicError, RepositoryError
from src.models.job import Job
from src.repositories.job import JobRepository

MAX_EXTRACTED_SKILLS = 20
MAX_BATCH_LIMIT = 1000


@lru_cache(maxsize=1)
def _load_skills_dictionary() -> dict[str, list[str]]:
    """Load static skills dictionary configuration from JSON.

    Returns:
        Mapping of canonical skill name to alias list.

    Raises:
        RuntimeError: If the configuration file is missing or invalid.
    """
    config_path = Path(__file__).resolve().parent / "config" / "skills_dictionary.json"

    try:
        raw_payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeError("Invalid skills dictionary configuration.") from exc

    if not isinstance(raw_payload, dict):
        raise RuntimeError("skills_dictionary.json must contain an object.")

    dictionary: dict[str, list[str]] = {}
    for canonical, aliases in raw_payload.items():
        if not isinstance(canonical, str) or not canonical.strip():
            raise RuntimeError("Skill canonical names must be non-empty strings.")
        if not isinstance(aliases, list) or any(
            not isinstance(alias, str) or not alias.strip() for alias in aliases
        ):
            raise RuntimeError(
                f"Aliases for '{canonical}' must be a list of non-empty strings."
            )
        dictionary[canonical.strip()] = [alias.strip() for alias in aliases]

    return dictionary


def _normalize_text(text: str) -> str:
    """Normalize text for deterministic skill pattern matching.

    Args:
        text: Raw text value.

    Returns:
        Lowercased, unicode-normalized, whitespace-collapsed text.
    """
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


@lru_cache(maxsize=1)
def _build_skill_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    """Build cached regex patterns for canonical and alias skill matching.

    Returns:
        Tuple of regex pattern and canonical skill mappings.
    """
    patterns: list[tuple[re.Pattern[str], str]] = []
    boundary_guard = r"[a-z0-9.]"

    for canonical, aliases in _load_skills_dictionary().items():
        candidates = [canonical, *aliases]
        for candidate in candidates:
            normalized_candidate = _normalize_text(candidate)
            escaped = re.escape(normalized_candidate)
            pattern = re.compile(rf"(?<!{boundary_guard}){escaped}(?!{boundary_guard})")
            patterns.append((pattern, canonical))

    return tuple(patterns)


class JobEnrichmentService:
    """Service layer for extracting and persisting skills from job descriptions."""

    def __init__(self, repo: JobRepository):
        """Initialize JobEnrichmentService.

        Args:
            repo: Repository used for job persistence operations.
        """
        self.repo = repo

    def extract_skills_from_description(self, text: str) -> list[str]:
        """Extract canonical skills from free-text job descriptions.

        Args:
            text: Job description text to parse.

        Returns:
            Ordered list of canonical skills with aliases normalized and deduplicated.

        Raises:
            BusinessLogicError: If extraction fails unexpectedly.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="extract_skills_from_description"
        )

        if not text.strip():
            log.debug("Description is empty; returning no skills")
            return []

        try:
            normalized_text = _normalize_text(text)
            matches: list[tuple[int, str]] = []
            for pattern, canonical in _build_skill_patterns():
                for matched in pattern.finditer(normalized_text):
                    matches.append((matched.start(), canonical))

            matches.sort(key=lambda item: item[0])

            ordered: list[str] = []
            seen: set[str] = set()
            for _, canonical in matches:
                if canonical in seen:
                    continue
                seen.add(canonical)
                ordered.append(canonical)
                if len(ordered) >= MAX_EXTRACTED_SKILLS:
                    break

            log.bind(extracted_count=len(ordered)).info(
                "Extracted skills from description"
            )
            return ordered
        except Exception as exc:  # pragma: no cover - defensive wrapper
            log.bind(error=str(exc)).error("Unexpected failure during skill extraction")
            raise BusinessLogicError(
                "Failed to extract skills from description."
            ) from exc

    def build_enrichment_payload(self, job: Job) -> dict[str, Any]:
        """Build update payload for a job if skills enrichment is needed.

        Args:
            job: Job entity candidate for enrichment.

        Returns:
            Update payload with ``skills`` key when enrichment is possible, otherwise empty.

        Raises:
            BusinessLogicError: If extraction fails.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="build_enrichment_payload",
            job_id=getattr(job, "id", None),
        )

        if self._has_non_empty_skills(getattr(job, "skills", None)):
            log.debug("Skipping payload build because job already has skills")
            return {}

        description_parts = [
            part
            for part in (
                getattr(job, "description_full", None),
                getattr(job, "description_short", None),
            )
            if isinstance(part, str) and part.strip()
        ]
        description_text = "\n".join(description_parts)
        if not description_text:
            log.debug("Skipping payload build because description is missing")
            return {}

        skills = self.extract_skills_from_description(description_text)
        if not skills:
            log.debug("No skills extracted from description")
            return {}

        return {"skills": skills}

    async def enrich_job(self, job_id: int) -> Job | None:
        """Enrich one job record with extracted skills when currently missing.

        Args:
            job_id: Target job identifier.

        Returns:
            Updated job, unchanged existing job, or ``None`` when not found.

        Raises:
            BusinessLogicError: If repository operations fail.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="enrich_job", job_id=job_id
        )
        log.info("Starting job enrichment")

        try:
            job = await self.repo.get_by_id(job_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job for enrichment")
            raise BusinessLogicError("Failed to enrich job.") from exc

        if job is None:
            log.info("Job not found for enrichment")
            return None

        payload = self.build_enrichment_payload(job)
        if not payload:
            log.info("Job enrichment skipped")
            return job

        try:
            updated = await self.repo.update(job_id, payload)
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to persist enriched job skills")
            raise BusinessLogicError("Failed to enrich job.") from exc

        if updated is None:
            log.warning("Job disappeared during enrichment update")
            return None

        log.bind(skills_count=len(updated.skills or [])).info(
            "Job enrichment completed"
        )
        return updated

    async def enrich_jobs_with_missing_skills(
        self, limit: int = 200, platform: str | None = None
    ) -> dict[str, int]:
        """Batch-enrich jobs that are missing skills.

        Args:
            limit: Maximum number of jobs to scan.
            platform: Optional source platform filter.

        Returns:
            Summary counters for processed, enriched, skipped, and failed jobs.

        Raises:
            BusinessLogicError: If input validation or initial repository query fails.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="enrich_jobs_with_missing_skills",
            limit=limit,
            platform=platform,
        )
        log.info("Starting batch enrichment")

        if limit < 1 or limit > MAX_BATCH_LIMIT:
            raise BusinessLogicError(f"limit must be between 1 and {MAX_BATCH_LIMIT}.")

        try:
            jobs = await self.repo.get_all(
                skip=0,
                limit=limit,
                platform=platform,
                is_active=True,
            )
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to fetch jobs for batch enrichment")
            raise BusinessLogicError("Failed to enrich jobs.") from exc

        summary = {"processed": 0, "enriched": 0, "skipped": 0, "failed": 0}

        for job in jobs:
            summary["processed"] += 1
            payload = self.build_enrichment_payload(job)

            if not payload:
                summary["skipped"] += 1
                continue

            try:
                updated = await self.repo.update(job.id, payload)
            except (RepositoryError, ValueError) as exc:
                summary["failed"] += 1
                logger.bind(
                    service=self.__class__.__name__,
                    operation="enrich_jobs_with_missing_skills",
                    job_id=getattr(job, "id", None),
                    error=str(exc),
                ).error("Failed to enrich job in batch")
                continue

            if updated is None:
                summary["failed"] += 1
                logger.bind(
                    service=self.__class__.__name__,
                    operation="enrich_jobs_with_missing_skills",
                    job_id=getattr(job, "id", None),
                ).warning("Job disappeared during batch enrichment")
                continue

            summary["enriched"] += 1

        log.bind(**summary).info("Completed batch enrichment")
        return summary

    def _has_non_empty_skills(self, skills: object) -> bool:
        """Determine whether an existing skills payload should be preserved.

        Args:
            skills: Candidate skills value from a job record.

        Returns:
            ``True`` when skills contain at least one non-empty string.
        """
        if not isinstance(skills, list):
            return False

        return any(isinstance(item, str) and item.strip() for item in skills)


__all__ = ["JobEnrichmentService"]
