"""Business logic service for LLM-powered job/profile relevance scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.ai.llm_client import BaseLLMClient, get_llm_client
from src.ai.prompts import job_scoring_prompt
from src.core.exceptions import BusinessLogicError, NotFoundError, RepositoryError
from src.repositories.job import JobRepository
from src.repositories.job_enrichment import JobEnrichmentRepository
from src.repositories.match_score import MatchScoreRepository
from src.repositories.profile import ProfileRepository
from src.schemas.job import EnrichedJobResponse, JobResponse
from src.schemas.match_score import MatchScoreResponse
from src.schemas.profile import ProfileResponse

MAX_BATCH_LIMIT = 1000


class MatchService:
    """Service layer for scoring job relevance against a candidate profile."""

    def __init__(
        self,
        job_repo: JobRepository,
        profile_repo: ProfileRepository,
        match_repo: MatchScoreRepository,
        enrichment_repo: JobEnrichmentRepository | None = None,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        """Initialize MatchService.

        Args:
            job_repo: Repository used for job read operations.
            profile_repo: Repository used for profile read operations.
            match_repo: Repository used for match score upsert operations.
            enrichment_repo: Optional repository used for processed enrichment reads.
            llm_client: Optional LLM client override for tests.
        """
        self.job_repo = job_repo
        self.profile_repo = profile_repo
        self.match_repo = match_repo
        self.enrichment_repo = enrichment_repo
        self.llm_client = llm_client or get_llm_client()

    async def score_job(self, job_id: int, profile_id: int) -> MatchScoreResponse:
        """Score one job against one profile and persist the result.

        Args:
            job_id: Job identifier to score.
            profile_id: Profile identifier used as scoring context.

        Returns:
            Persisted match score response.

        Raises:
            NotFoundError: If the job or profile does not exist.
            BusinessLogicError: If repository, LLM, or validation operations fail.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="score_job",
            job_id=job_id,
            profile_id=profile_id,
        )
        log.info("Starting job score")

        try:
            job = await self.job_repo.get_by_id(job_id)
            profile = await self.profile_repo.get_by_id(profile_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job/profile for scoring")
            raise BusinessLogicError(
                "Failed to fetch data required for scoring."
            ) from exc

        if job is None:
            log.warning("Job not found for scoring")
            raise NotFoundError(f"Job {job_id} not found.")
        if profile is None:
            log.warning("Profile not found for scoring")
            raise NotFoundError(f"Profile {profile_id} not found.")

        enrichment: object | None = None
        if self.enrichment_repo is not None:
            try:
                enrichment = await self.enrichment_repo.get_latest_by_job_id(job_id)
            except RepositoryError as exc:
                log.bind(error=str(exc)).error("Failed to fetch enrichment for scoring")
                raise BusinessLogicError(
                    "Failed to fetch data required for scoring."
                ) from exc

        try:
            raw_job_data = JobResponse.model_validate(job).model_dump(mode="json")
            job_data = self._build_scoring_job_data(
                raw_job_data=raw_job_data,
                enrichment=enrichment,
            )
            profile_data = ProfileResponse.model_validate(profile).model_dump(
                mode="json"
            )
            prompt = job_scoring_prompt(job_data=job_data, profile_data=profile_data)
            llm_payload = await self.llm_client.generate_json(prompt, temperature=0.3)
        except (TypeError, ValueError, RuntimeError) as exc:
            log.bind(error=str(exc)).error("Failed to generate scoring output from LLM")
            raise BusinessLogicError(
                "Failed to generate score from LLM output."
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive wrapper
            log.bind(error=str(exc)).error("Unexpected LLM scoring failure")
            raise BusinessLogicError("Unexpected error while scoring job.") from exc

        try:
            score = self._validate_score(llm_payload)
            explanation = self._validate_explanation(llm_payload)
            category = self._determine_category(score)
            record = await self.match_repo.upsert_by_job_and_profile(
                job_id=job_id,
                profile_id=profile_id,
                payload={
                    "relevance_score": score,
                    "category": category,
                    "explanation": explanation,
                    "scored_at": datetime.now(timezone.utc),
                },
            )
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to persist match score")
            raise BusinessLogicError("Failed to persist match score.") from exc
        except ValueError as exc:
            log.bind(error=str(exc), llm_payload=llm_payload).error(
                "Invalid LLM score payload"
            )
            raise BusinessLogicError("Invalid score payload returned by LLM.") from exc

        log.bind(score=score, category=category).info("Completed job score")
        return MatchScoreResponse.model_validate(record)

    async def score_all_unscored_jobs(self, profile_id: int) -> int:
        """Score all active jobs that do not yet have a match score.

        Args:
            profile_id: Profile identifier used as scoring context.

        Returns:
            Number of newly scored jobs.

        Raises:
            NotFoundError: If the profile does not exist.
            BusinessLogicError: If active jobs cannot be fetched.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="score_all_unscored_jobs",
            profile_id=profile_id,
        )
        log.info("Starting batch scoring")

        try:
            profile = await self.profile_repo.get_by_id(profile_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch profile for batch scoring")
            raise BusinessLogicError(
                "Failed to fetch profile for batch scoring."
            ) from exc

        if profile is None:
            log.warning("Profile not found for batch scoring")
            raise NotFoundError(f"Profile {profile_id} not found.")

        scored_count = 0
        skip = 0

        while True:
            try:
                jobs = await self.job_repo.get_all(
                    skip=skip,
                    limit=MAX_BATCH_LIMIT,
                    is_active=True,
                )
            except (RepositoryError, ValueError) as exc:
                log.bind(error=str(exc), skip=skip).error(
                    "Failed to fetch active jobs for batch scoring"
                )
                raise BusinessLogicError(
                    "Failed to fetch active jobs for scoring."
                ) from exc

            if not jobs:
                break

            for job in jobs:
                job_id = getattr(job, "id", None)
                if not isinstance(job_id, int):
                    logger.bind(
                        service=self.__class__.__name__,
                        operation="score_all_unscored_jobs",
                        profile_id=profile_id,
                    ).warning("Skipping active job with invalid id")
                    continue

                try:
                    existing = await self.match_repo.get_by_job_and_profile(
                        job_id=job_id,
                        profile_id=profile_id,
                    )
                except RepositoryError as exc:
                    logger.bind(
                        service=self.__class__.__name__,
                        operation="score_all_unscored_jobs",
                        profile_id=profile_id,
                        job_id=job_id,
                        error=str(exc),
                    ).error("Failed to check existing score; skipping job")
                    continue

                if existing is not None:
                    logger.bind(
                        service=self.__class__.__name__,
                        operation="score_all_unscored_jobs",
                        profile_id=profile_id,
                        job_id=job_id,
                    ).debug("Skipping already scored job")
                    continue

                try:
                    await self.score_job(job_id=job_id, profile_id=profile_id)
                    scored_count += 1
                except (BusinessLogicError, NotFoundError) as exc:
                    logger.bind(
                        service=self.__class__.__name__,
                        operation="score_all_unscored_jobs",
                        profile_id=profile_id,
                        job_id=job_id,
                        error=str(exc),
                    ).error("Failed to score job in batch")
                    continue

            if len(jobs) < MAX_BATCH_LIMIT:
                break
            skip += len(jobs)

        log.bind(scored_count=scored_count).info("Completed batch scoring")
        return scored_count

    async def list_jobs_by_relevance(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
        profile_id: int | None = None,
    ) -> list[EnrichedJobResponse]:
        """List jobs ordered by relevance score for one profile.

        Args:
            skip: Number of rows to offset.
            limit: Maximum rows to return.
            platform: Optional platform filter.
            is_active: Active status filter.
            profile_id: Optional profile id; falls back to the first profile.

        Returns:
            Enriched job responses including ``relevance_score``.

        Raises:
            BusinessLogicError: If profile resolution or repository calls fail.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="list_jobs_by_relevance",
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
            profile_id=profile_id,
        )
        log.info("Listing jobs by relevance")

        resolved_profile_id = profile_id
        if resolved_profile_id is None:
            try:
                profile = await self.profile_repo.get_first()
            except RepositoryError as exc:
                log.bind(error=str(exc)).error("Failed to fetch profile for relevance")
                raise BusinessLogicError(
                    "Failed to fetch profile for relevance sorting."
                ) from exc

            if profile is None:
                log.warning("Cannot list jobs by relevance without a profile")
                raise BusinessLogicError(
                    "Create a profile first before sorting jobs by relevance."
                )
            resolved_profile_id = profile.id

        try:
            rows = await self.match_repo.get_jobs_by_score(
                profile_id=resolved_profile_id,
                skip=skip,
                limit=limit,
                platform=platform,
                is_active=is_active,
            )
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to list jobs by relevance")
            raise BusinessLogicError("Failed to list jobs by relevance.") from exc

        if not rows:
            return []

        latest_by_job_id: dict[int, object] = {}
        if self.enrichment_repo is not None:
            job_ids = [getattr(job, "id", 0) for job, _ in rows]
            try:
                enrichments = await self.enrichment_repo.list_by_job_ids(job_ids)
            except RepositoryError as exc:
                log.bind(error=str(exc)).error("Failed to list enrichments by job ids")
                raise BusinessLogicError("Failed to list jobs by relevance.") from exc
            latest_by_job_id = self._latest_enrichment_by_job_id(enrichments)

        responses: list[EnrichedJobResponse] = []
        for job, relevance_score in rows:
            raw_job = JobResponse.model_validate(job).model_copy(
                update={"relevance_score": relevance_score}
            )
            response = self._build_enriched_job_response(
                raw_job=raw_job,
                enrichment=latest_by_job_id.get(raw_job.id),
            )
            responses.append(response)

        log.bind(count=len(responses)).info("Listed jobs by relevance")
        return responses

    def _build_scoring_job_data(
        self,
        raw_job_data: dict[str, Any],
        enrichment: object | None,
    ) -> dict[str, Any]:
        """Build LLM job payload with processed-first enrichment fallbacks.

        Args:
            raw_job_data: Raw job payload derived from persisted job fields.
            enrichment: Optional latest enrichment row for the job.

        Returns:
            Job payload for prompt construction.
        """
        job_data = raw_job_data.copy()
        if enrichment is None:
            return job_data

        enriched_salary = self._build_salary_range_from_enrichment(enrichment)
        if enriched_salary is not None:
            job_data["salary_range"] = enriched_salary

        job_data["skills"] = getattr(enrichment, "skills", None) or raw_job_data.get(
            "skills"
        )
        job_data["job_type"] = getattr(
            enrichment, "job_type", None
        ) or raw_job_data.get("job_type")
        job_data["location"] = getattr(
            enrichment, "location_normalized", None
        ) or raw_job_data.get("location")
        return job_data

    def _build_enriched_job_response(
        self,
        raw_job: JobResponse,
        enrichment: object | None,
    ) -> EnrichedJobResponse:
        """Merge raw job plus optional enrichment into enriched response schema.

        Args:
            raw_job: Raw job response generated from repository row.
            enrichment: Optional enrichment row matched by job id.

        Returns:
            Enriched job response for API output.
        """
        salary_range = self._build_salary_range_from_enrichment(enrichment)
        if salary_range is None:
            salary_range = raw_job.salary_range

        return EnrichedJobResponse(
            id=raw_job.id,
            created_at=raw_job.created_at,
            updated_at=raw_job.updated_at,
            external_id=raw_job.external_id,
            platform=raw_job.platform,
            url=raw_job.url,
            title=raw_job.title,
            company=raw_job.company,
            location=getattr(enrichment, "location_normalized", None)
            or raw_job.location,
            description_short=raw_job.description_short,
            description_full=raw_job.description_full,
            posted_date=raw_job.posted_date,
            scraped_at=raw_job.scraped_at,
            is_active=raw_job.is_active,
            skills=getattr(enrichment, "skills", None) or raw_job.skills,
            job_type=getattr(enrichment, "job_type", None) or raw_job.job_type,
            salary_range=salary_range,
            enrichment_status=getattr(enrichment, "status", None),
            enrichment_version=getattr(enrichment, "extractor_version", None),
            enrichment_updated_at=self._as_datetime(
                getattr(enrichment, "enriched_at", None)
            ),
            relevance_score=raw_job.relevance_score,
        )

    def _build_salary_range_from_enrichment(
        self,
        enrichment: object | None,
    ) -> dict[str, Any] | None:
        """Build salary range payload from enrichment salary columns.

        Args:
            enrichment: Optional enrichment row.

        Returns:
            Salary dictionary when any salary field exists, otherwise ``None``.
        """
        if enrichment is None:
            return None

        salary_range = {
            "min": getattr(enrichment, "salary_min", None),
            "max": getattr(enrichment, "salary_max", None),
            "currency": getattr(enrichment, "salary_currency", None),
            "period": getattr(enrichment, "salary_period", None),
            "raw": getattr(enrichment, "salary_raw", None),
        }
        if all(value is None for value in salary_range.values()):
            return None
        return salary_range

    def _latest_enrichment_by_job_id(
        self,
        enrichments: list[object],
    ) -> dict[int, object]:
        """Select the newest enrichment row for each job id.

        Args:
            enrichments: Candidate enrichment rows returned by repository.

        Returns:
            Mapping of job id to latest enrichment row.
        """
        latest: dict[int, object] = {}

        for row in enrichments:
            job_id = getattr(row, "job_id", None)
            if not isinstance(job_id, int):
                continue

            current = latest.get(job_id)
            if current is None:
                latest[job_id] = row
                continue

            if self._is_newer_enrichment(candidate=row, current=current):
                latest[job_id] = row

        return latest

    def _is_newer_enrichment(self, candidate: object, current: object) -> bool:
        """Determine whether candidate enrichment is newer than current.

        Args:
            candidate: Candidate enrichment row.
            current: Existing selected enrichment row.

        Returns:
            ``True`` when candidate should replace current.
        """
        candidate_enriched_at = self._as_datetime(
            getattr(candidate, "enriched_at", None)
        )
        current_enriched_at = self._as_datetime(getattr(current, "enriched_at", None))

        if candidate_enriched_at is not None and current_enriched_at is not None:
            if candidate_enriched_at != current_enriched_at:
                return candidate_enriched_at > current_enriched_at
        elif candidate_enriched_at is not None:
            return True
        elif current_enriched_at is not None:
            return False

        candidate_id = getattr(candidate, "id", 0)
        current_id = getattr(current, "id", 0)
        if isinstance(candidate_id, int) and isinstance(current_id, int):
            return candidate_id > current_id
        return False

    @staticmethod
    def _as_datetime(value: object) -> datetime | None:
        """Safely cast a value to datetime.

        Args:
            value: Candidate datetime object.

        Returns:
            Datetime when value is datetime, otherwise ``None``.
        """
        if isinstance(value, datetime):
            return value
        return None

    def _determine_category(self, score: int) -> str:
        """Map numeric relevance score into canonical category label.

        Args:
            score: Integer relevance score from 0 to 100.

        Returns:
            Matching category label for the score range.
        """
        if score >= 90:
            return "Most Relevant"
        if score >= 70:
            return "Relevant"
        if score >= 50:
            return "Somewhat Relevant"
        return "Not Relevant"

    def _validate_score(self, payload: dict[str, Any]) -> int:
        """Validate score field in LLM response payload.

        Args:
            payload: Parsed JSON payload returned by LLM client.

        Returns:
            Validated integer score.

        Raises:
            ValueError: If score is missing or outside 0-100.
        """
        score = payload.get("score")
        if isinstance(score, bool) or not isinstance(score, int):
            raise ValueError("score must be an integer between 0 and 100")
        if score < 0 or score > 100:
            raise ValueError("score must be an integer between 0 and 100")
        return score

    def _validate_explanation(self, payload: dict[str, Any]) -> str:
        """Validate explanation field in LLM response payload.

        Args:
            payload: Parsed JSON payload returned by LLM client.

        Returns:
            Trimmed explanation string.

        Raises:
            ValueError: If explanation is missing or blank.
        """
        explanation = payload.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError("explanation must be a non-empty string")
        return explanation.strip()


__all__ = ["MatchService"]
