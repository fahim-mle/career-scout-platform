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
from src.models.job_enrichment import JobEnrichment
from src.models.job import Job
from src.repositories.job_enrichment import JobEnrichmentRepository
from src.repositories.job import JobRepository

MAX_EXTRACTED_SKILLS = 20
MAX_BATCH_LIMIT = 1000
JOB_TYPE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfull[\s-]?time\b"), "Full-Time"),
    (re.compile(r"\bpart[\s-]?time\b"), "Part-Time"),
    (re.compile(r"\bcontract\b"), "Contract"),
    (re.compile(r"\bcasual\b"), "Casual"),
    (re.compile(r"\bintern(ship)?\b"), "Internship"),
    (re.compile(r"\btemporar(y|ily)\b"), "Temporary"),
    (re.compile(r"\bfreelance\b"), "Freelance"),
)
SALARY_PERIOD_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:/|per\s+)(hour|hr)\b|\bhourly\b"), "hour"),
    (re.compile(r"(?:/|per\s+)day\b|\bdaily\b"), "day"),
    (re.compile(r"(?:/|per\s+)(year|annum|annual)\b|\bannually\b"), "year"),
)
SALARY_RANGE_PATTERN = re.compile(
    r"(?P<currency1>\$|a\$|aud|usd)?\s*"
    r"(?P<min>\d[\d,]*(?:\.\d+)?)\s*(?:-|to)\s*"
    r"(?P<currency2>\$|a\$|aud|usd)?\s*"
    r"(?P<max>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
SALARY_SINGLE_PATTERN = re.compile(
    r"(?P<currency>\$|a\$|aud|usd)\s*(?P<amount>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)


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


def _parse_amount(amount_text: str) -> float:
    """Parse numeric compensation amount from text.

    Args:
        amount_text: Numeric text that may include commas.

    Returns:
        Parsed float amount.

    Raises:
        ValueError: If amount cannot be parsed.
    """
    return float(amount_text.replace(",", "").strip())


def _normalize_amount(amount: float) -> int | float:
    """Normalize parsed amount to int when value is whole.

    Args:
        amount: Parsed amount.

    Returns:
        Integer for whole values, otherwise float.
    """
    return int(amount) if float(amount).is_integer() else amount


def _extract_period(text: str) -> str | None:
    """Extract compensation period token from text.

    Args:
        text: Text window around matched compensation.

    Returns:
        Normalized period token when found.
    """
    for pattern, period in SALARY_PERIOD_PATTERNS:
        if pattern.search(text):
            return period
    return None


def _infer_period(minimum: float, maximum: float) -> str | None:
    """Infer period token from numeric compensation ranges.

    Args:
        minimum: Lower bound amount.
        maximum: Upper bound amount.

    Returns:
        Inferred period token when the range matches heuristics.
    """
    if 30 <= minimum <= 300 and 30 <= maximum <= 300:
        return "hour"
    if 500 <= minimum <= 2000 and 500 <= maximum <= 2000:
        return "day"
    if 60000 <= minimum <= 500000 and 60000 <= maximum <= 500000:
        return "year"
    return None


def _detect_currency(text_window: str, currency_tokens: list[str]) -> str | None:
    """Detect normalized currency from matched tokens and context.

    Args:
        text_window: Nearby text window for context checks.
        currency_tokens: Currency tokens captured in regex groups.

    Returns:
        ISO-like currency code when detectable.
    """
    normalized_tokens = [token.casefold() for token in currency_tokens if token]
    window = text_window.casefold()

    if "usd" in normalized_tokens or re.search(r"\busd\b", window):
        return "USD"
    if "aud" in normalized_tokens or "a$" in normalized_tokens:
        return "AUD"
    if "$" in normalized_tokens:
        return "AUD"
    return None


class JobEnrichmentService:
    """Service layer for extracting and persisting skills from job descriptions."""

    def __init__(
        self,
        job_repo: JobRepository,
        enrichment_repo: JobEnrichmentRepository,
        extractor_version: str = "heuristic-v1",
    ):
        """Initialize JobEnrichmentService.

        Args:
            job_repo: Repository used for raw job read operations.
            enrichment_repo: Repository used for enrichment persistence operations.
            extractor_version: Version token for this extraction implementation.
        """
        self.job_repo = job_repo
        self.enrichment_repo = enrichment_repo
        self.extractor_version = extractor_version

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

    def extract_job_type_from_text(self, text: str) -> str | None:
        """Extract normalized job type label from job text.

        Args:
            text: Job title and/or description content.

        Returns:
            Normalized job type label when detected, otherwise ``None``.

        Raises:
            BusinessLogicError: If extraction fails unexpectedly.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="extract_job_type_from_text"
        )

        if not text.strip():
            log.debug("Input text is empty; returning no job type")
            return None

        try:
            normalized_text = _normalize_text(text)
            for pattern, label in JOB_TYPE_PATTERNS:
                if pattern.search(normalized_text):
                    log.bind(job_type=label).info("Extracted job type from text")
                    return label

            log.debug("No job type extracted from text")
            return None
        except Exception as exc:  # pragma: no cover - defensive wrapper
            log.bind(error=str(exc)).error(
                "Unexpected failure during job type extraction"
            )
            raise BusinessLogicError(
                "Failed to extract job type from description."
            ) from exc

    def extract_salary_range_from_text(self, text: str) -> dict[str, Any] | None:
        """Extract compensation range payload from job text.

        Args:
            text: Job title and/or description content.

        Returns:
            Salary range payload with ``min``, ``max``, and ``currency`` when extractable.

        Raises:
            BusinessLogicError: If extraction fails unexpectedly.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="extract_salary_range_from_text"
        )

        if not text.strip():
            log.debug("Input text is empty; returning no salary range")
            return None

        try:
            normalized_text = _normalize_text(text)

            range_match = SALARY_RANGE_PATTERN.search(normalized_text)
            if range_match:
                minimum = _parse_amount(range_match.group("min"))
                maximum = _parse_amount(range_match.group("max"))
                if minimum > maximum:
                    minimum, maximum = maximum, minimum

                context_window = normalized_text[
                    max(0, range_match.start() - 24) : min(
                        len(normalized_text),
                        range_match.end() + 36,
                    )
                ]
                currency = _detect_currency(
                    context_window,
                    [
                        range_match.group("currency1") or "",
                        range_match.group("currency2") or "",
                    ],
                )
                if currency is None:
                    log.debug(
                        "Skipping salary range extraction due to missing currency"
                    )
                    return None

                period = _extract_period(context_window) or _infer_period(
                    minimum, maximum
                )
                payload: dict[str, Any] = {
                    "min": _normalize_amount(minimum),
                    "max": _normalize_amount(maximum),
                    "currency": currency,
                    "raw": text[range_match.start() : range_match.end()].strip(),
                }
                if period is not None:
                    payload["period"] = period

                log.bind(
                    currency=currency,
                    period=payload.get("period"),
                    minimum=payload["min"],
                    maximum=payload["max"],
                ).info("Extracted salary range from text")
                return payload

            single_match = SALARY_SINGLE_PATTERN.search(normalized_text)
            if single_match:
                amount = _parse_amount(single_match.group("amount"))
                context_window = normalized_text[
                    max(0, single_match.start() - 24) : min(
                        len(normalized_text),
                        single_match.end() + 36,
                    )
                ]
                period = _extract_period(context_window)
                if period is None:
                    log.debug(
                        "Skipping single salary extraction without explicit period"
                    )
                    return None

                currency = _detect_currency(
                    context_window, [single_match.group("currency")]
                )
                if currency is None:
                    log.debug("Skipping salary extraction due to missing currency")
                    return None

                normalized_amount = _normalize_amount(amount)
                payload = {
                    "min": normalized_amount,
                    "max": normalized_amount,
                    "currency": currency,
                    "period": period,
                    "raw": text[single_match.start() : single_match.end()].strip(),
                }
                log.bind(
                    currency=currency,
                    period=period,
                    minimum=normalized_amount,
                    maximum=normalized_amount,
                ).info("Extracted single salary amount from text")
                return payload

            log.debug("No salary range extracted from text")
            return None
        except ValueError as exc:
            log.bind(error=str(exc)).error(
                "Invalid numeric value during salary extraction"
            )
            raise BusinessLogicError(
                "Failed to extract salary range from description."
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive wrapper
            log.bind(error=str(exc)).error(
                "Unexpected failure during salary extraction"
            )
            raise BusinessLogicError(
                "Failed to extract salary range from description."
            ) from exc

    def build_enrichment_payload(self, job: Job) -> dict[str, Any]:
        """Build processed enrichment payload from raw job text.

        Args:
            job: Job entity candidate for enrichment.

        Returns:
            Processed payload suitable for ``job_enrichments`` persistence.

        Raises:
            BusinessLogicError: If extraction fails.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="build_enrichment_payload",
            job_id=getattr(job, "id", None),
        )

        description_parts = [
            part
            for part in (
                getattr(job, "title", None),
                getattr(job, "description_full", None),
                getattr(job, "description_short", None),
            )
            if isinstance(part, str) and part.strip()
        ]
        combined_text = "\n".join(description_parts)

        if not combined_text:
            log.debug("Skipping payload build because description is missing")
            return {"status": "failed"}

        payload: dict[str, Any] = {}

        skills = self.extract_skills_from_description(combined_text)
        if skills:
            payload["skills"] = skills
        else:
            log.debug("No skills extracted from description")

        job_type = self.extract_job_type_from_text(combined_text)
        if job_type:
            payload["job_type"] = job_type

        salary_range = self.extract_salary_range_from_text(combined_text)
        if salary_range:
            payload.update(self._salary_range_to_enrichment_fields(salary_range))

        payload["status"] = self._determine_status(payload)

        log.bind(fields=sorted(payload.keys())).info("Built enrichment payload")
        return payload

    async def enrich_job(self, job_id: int) -> JobEnrichment | None:
        """Enrich one raw job and persist processed enrichment output.

        Args:
            job_id: Target job identifier.

        Returns:
            Upserted enrichment record, or ``None`` when raw job is not found.

        Raises:
            BusinessLogicError: If repository operations fail.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="enrich_job", job_id=job_id
        )
        log.info("Starting job enrichment")

        try:
            job = await self.job_repo.get_by_id(job_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job for enrichment")
            raise BusinessLogicError("Failed to enrich job.") from exc

        if job is None:
            log.info("Job not found for enrichment")
            return None

        payload = self.build_enrichment_payload(job)

        try:
            enrichment = await self.enrichment_repo.upsert_by_job_and_version(
                job_id=job.id,
                extractor_version=self.extractor_version,
                payload=payload,
            )
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to persist enrichment output")
            raise BusinessLogicError("Failed to enrich job.") from exc

        log.bind(fields=sorted(payload.keys())).info("Job enrichment completed")
        return enrichment

    async def enrich_jobs_with_missing_skills(
        self, limit: int = 200, platform: str | None = None
    ) -> dict[str, int]:
        """Batch-enrich active jobs into processed enrichment rows.

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
            jobs = await self.job_repo.get_all(
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

            try:
                await self.enrichment_repo.upsert_by_job_and_version(
                    job_id=job.id,
                    extractor_version=self.extractor_version,
                    payload=payload,
                )
            except (RepositoryError, ValueError) as exc:
                summary["failed"] += 1
                logger.bind(
                    service=self.__class__.__name__,
                    operation="enrich_jobs_with_missing_skills",
                    job_id=getattr(job, "id", None),
                    error=str(exc),
                ).error("Failed to enrich job in batch")
                continue

            if payload.get("status") == "failed":
                summary["skipped"] += 1
            else:
                summary["enriched"] += 1

        log.bind(**summary).info("Completed batch enrichment")
        return summary

    def _salary_range_to_enrichment_fields(
        self,
        salary_range: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert legacy salary range payload into enrichment columns.

        Args:
            salary_range: Legacy extracted salary range payload.

        Returns:
            Processed salary fields for ``job_enrichments``.
        """
        return {
            "salary_min": salary_range.get("min"),
            "salary_max": salary_range.get("max"),
            "salary_currency": salary_range.get("currency"),
            "salary_period": salary_range.get("period", "unknown"),
            "salary_raw": salary_range.get("raw"),
        }

    def _determine_status(self, payload: dict[str, Any]) -> str:
        """Determine enrichment status based on extracted field coverage.

        Args:
            payload: Built enrichment payload.

        Returns:
            ``success`` when all target field groups were extracted,
            ``partial`` when at least one was extracted, otherwise ``failed``.
        """
        has_skills = isinstance(payload.get("skills"), list) and bool(payload["skills"])
        has_job_type = isinstance(payload.get("job_type"), str) and bool(
            payload["job_type"].strip()
        )
        has_salary = (
            payload.get("salary_min") is not None
            and payload.get("salary_max") is not None
        )

        extracted_groups = int(has_skills) + int(has_job_type) + int(has_salary)
        if extracted_groups == 3:
            return "success"
        if extracted_groups > 0:
            return "partial"
        return "failed"


__all__ = ["JobEnrichmentService"]
