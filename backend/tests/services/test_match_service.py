"""Unit tests for MatchService scoring orchestration and error handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.ai.llm_client import BaseLLMClient
from src.core.exceptions import BusinessLogicError, NotFoundError, RepositoryError
from src.repositories.job import JobRepository
from src.repositories.match_score import MatchScoreRepository
from src.repositories.profile import ProfileRepository
from src.services.match_service import MatchService


def make_job(**overrides: Any) -> SimpleNamespace:
    """Build a job-like object compatible with JobResponse validation.

    Args:
        **overrides: Field overrides for the generated object.

    Returns:
        Job-like namespace with all fields required by schema validation.
    """
    now = datetime.now(timezone.utc)
    data: dict[str, Any] = {
        "id": 1,
        "created_at": now,
        "updated_at": now,
        "external_id": "ext-1",
        "platform": "linkedin",
        "url": "https://linkedin.com/jobs/ext-1",
        "title": "Backend Engineer",
        "company": "Career Scout",
        "location": "Brisbane",
        "job_type": None,
        "description_short": "Build async APIs",
        "description_full": "FastAPI and PostgreSQL role.",
        "posted_date": date.today(),
        "scraped_at": now,
        "is_active": True,
        "skills": ["Python", "FastAPI"],
        "salary_range": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_profile(**overrides: Any) -> SimpleNamespace:
    """Build a profile-like object compatible with ProfileResponse validation.

    Args:
        **overrides: Field overrides for the generated object.

    Returns:
        Profile-like namespace with all fields required by schema validation.
    """
    now = datetime.now(timezone.utc)
    data: dict[str, Any] = {
        "id": 1,
        "created_at": now,
        "updated_at": now,
        "name": "Taylor Dev",
        "location": "Brisbane",
        "experience_years": 6,
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "preferences": {"remote": True},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@dataclass
class FakeJobRepository:
    """In-memory async repository stub for jobs."""

    jobs: dict[int, SimpleNamespace] = field(default_factory=dict)
    fail_get_all: bool = False

    async def get_by_id(self, job_id: int) -> SimpleNamespace | None:
        """Fetch one job by id.

        Args:
            job_id: Target job identifier.

        Returns:
            Job object when found, otherwise ``None``.
        """
        return self.jobs.get(job_id)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
    ) -> list[SimpleNamespace]:
        """Return filtered jobs for batch scoring.

        Args:
            skip: Pagination offset.
            limit: Pagination size.
            platform: Optional platform filter.
            is_active: Active status filter.

        Returns:
            Matching fake jobs.

        Raises:
            RepositoryError: If configured to fail.
        """
        if self.fail_get_all:
            raise RepositoryError("repo get_all failed")

        items = [job for job in self.jobs.values() if job.is_active is is_active]
        if platform is not None:
            items = [job for job in items if job.platform == platform]
        items.sort(key=lambda item: item.id)
        return items[skip : skip + limit]


@dataclass
class FakeProfileRepository:
    """In-memory async repository stub for profiles."""

    profiles: dict[int, SimpleNamespace] = field(default_factory=dict)

    async def get_by_id(self, profile_id: int) -> SimpleNamespace | None:
        """Fetch one profile by id.

        Args:
            profile_id: Target profile identifier.

        Returns:
            Profile object when found, otherwise ``None``.
        """
        return self.profiles.get(profile_id)


@dataclass
class FakeMatchScoreRepository:
    """In-memory async repository stub for match scores."""

    scores_by_key: dict[tuple[int, int], SimpleNamespace] = field(default_factory=dict)
    fail_upsert_ids: set[int] = field(default_factory=set)
    upsert_calls: list[tuple[int, int, dict[str, Any]]] = field(default_factory=list)
    _counter: int = 0

    async def get_by_job_and_profile(
        self, job_id: int, profile_id: int
    ) -> SimpleNamespace | None:
        """Fetch score by unique job/profile key.

        Args:
            job_id: Job identifier.
            profile_id: Profile identifier.

        Returns:
            Persisted score row when found, otherwise ``None``.
        """
        return self.scores_by_key.get((job_id, profile_id))

    async def upsert_by_job_and_profile(
        self,
        job_id: int,
        profile_id: int,
        payload: dict[str, Any],
    ) -> SimpleNamespace:
        """Insert or overwrite score row for test assertions.

        Args:
            job_id: Job identifier.
            profile_id: Profile identifier.
            payload: Score payload from service.

        Returns:
            Persisted score-like object.

        Raises:
            RepositoryError: If configured to fail for the job id.
        """
        self.upsert_calls.append((job_id, profile_id, payload.copy()))
        if job_id in self.fail_upsert_ids:
            raise RepositoryError("repo upsert failed")

        now = datetime.now(timezone.utc)
        existing = self.scores_by_key.get((job_id, profile_id))
        if existing is None:
            self._counter += 1
            record = {
                "id": self._counter,
                "created_at": now,
                "updated_at": now,
                "job_id": job_id,
                "profile_id": profile_id,
                **payload,
            }
            row = SimpleNamespace(**record)
            self.scores_by_key[(job_id, profile_id)] = row
            return row

        merged = existing.__dict__.copy()
        merged.update(payload)
        merged["updated_at"] = now
        row = SimpleNamespace(**merged)
        self.scores_by_key[(job_id, profile_id)] = row
        return row


class FakeLLMClient(BaseLLMClient):
    """Deterministic LLM test double with queued JSON responses."""

    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        """Initialize fake client.

        Args:
            responses: Queue of responses or exceptions to emit per call.
        """
        self.responses = responses
        self.generate_json_calls: list[tuple[str, float, int | None]] = []

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Unused text generation API for abstract compatibility.

        Args:
            prompt: Prompt text.
            temperature: Sampling temperature.
            max_tokens: Optional generation token cap.

        Returns:
            Empty string because tests use JSON generation path only.
        """
        return ""

    async def generate_json(
        self,
        prompt: str,
        temperature: float = 0.5,
        max_tokens: int | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Return the next queued JSON payload.

        Args:
            prompt: Prompt text from service.
            temperature: Sampling temperature.
            max_tokens: Optional generation token cap.
            max_retries: Unused retry setting.

        Returns:
            Next queued JSON dictionary.

        Raises:
            Exception: Re-raises queued exception values.
        """
        del max_retries
        self.generate_json_calls.append((prompt, temperature, max_tokens))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_service(
    job_repo: FakeJobRepository,
    profile_repo: FakeProfileRepository,
    match_repo: FakeMatchScoreRepository,
    llm: FakeLLMClient,
) -> MatchService:
    """Create MatchService with casted test doubles.

    Args:
        job_repo: Fake jobs repository.
        profile_repo: Fake profiles repository.
        match_repo: Fake match score repository.
        llm: Fake LLM client.

    Returns:
        Configured MatchService instance for unit tests.
    """
    return MatchService(
        job_repo=cast(JobRepository, job_repo),
        profile_repo=cast(ProfileRepository, profile_repo),
        match_repo=cast(MatchScoreRepository, match_repo),
        llm_client=llm,
    )


@pytest.mark.asyncio
async def test_score_job_success_creates_score() -> None:
    job_repo = FakeJobRepository(jobs={1: make_job(id=1)})
    profile_repo = FakeProfileRepository(profiles={1: make_profile(id=1)})
    match_repo = FakeMatchScoreRepository()
    llm = FakeLLMClient(
        responses=[
            {
                "score": 86,
                "category": "Relevant",
                "explanation": "Strong skills alignment with minor domain gaps.",
            }
        ]
    )
    service = make_service(job_repo, profile_repo, match_repo, llm)

    result = await service.score_job(job_id=1, profile_id=1)

    assert result.job_id == 1
    assert result.profile_id == 1
    assert result.relevance_score == 86
    assert result.category == "Relevant"
    assert len(match_repo.upsert_calls) == 1
    assert match_repo.upsert_calls[0][2]["explanation"] == (
        "Strong skills alignment with minor domain gaps."
    )
    assert llm.generate_json_calls[0][1] == 0.3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_seed", "profile_seed", "expected_message"),
    [
        ({}, {1: make_profile(id=1)}, "Job 1 not found"),
        ({1: make_job(id=1)}, {}, "Profile 1 not found"),
    ],
)
async def test_score_job_raises_not_found_for_missing_entities(
    job_seed: dict[int, SimpleNamespace],
    profile_seed: dict[int, SimpleNamespace],
    expected_message: str,
) -> None:
    service = make_service(
        FakeJobRepository(jobs=job_seed),
        FakeProfileRepository(profiles=profile_seed),
        FakeMatchScoreRepository(),
        FakeLLMClient(responses=[{"score": 50, "explanation": "placeholder"}]),
    )

    with pytest.raises(NotFoundError, match=expected_message):
        await service.score_job(job_id=1, profile_id=1)


@pytest.mark.asyncio
async def test_score_job_maps_malformed_llm_payload_to_business_logic_error() -> None:
    service = make_service(
        FakeJobRepository(jobs={1: make_job(id=1)}),
        FakeProfileRepository(profiles={1: make_profile(id=1)}),
        FakeMatchScoreRepository(),
        FakeLLMClient(responses=[{"score": "bad", "explanation": "ok"}]),
    )

    with pytest.raises(BusinessLogicError, match="Invalid score payload"):
        await service.score_job(job_id=1, profile_id=1)


@pytest.mark.asyncio
async def test_score_all_unscored_jobs_skips_existing_and_counts_new_scores() -> None:
    job_repo = FakeJobRepository(
        jobs={1: make_job(id=1), 2: make_job(id=2), 3: make_job(id=3)}
    )
    profile_repo = FakeProfileRepository(profiles={1: make_profile(id=1)})
    match_repo = FakeMatchScoreRepository(
        scores_by_key={
            (2, 1): SimpleNamespace(
                id=99,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                job_id=2,
                profile_id=1,
                relevance_score=77,
                category="Relevant",
                explanation="Existing score",
                scored_at=datetime.now(timezone.utc),
            )
        }
    )
    llm = FakeLLMClient(
        responses=[
            {"score": 91, "explanation": "Excellent fit."},
            {"score": 55, "explanation": "Partial fit."},
        ]
    )
    service = make_service(job_repo, profile_repo, match_repo, llm)

    scored = await service.score_all_unscored_jobs(profile_id=1)

    assert scored == 2
    assert len(match_repo.upsert_calls) == 2
    assert len(llm.generate_json_calls) == 2


@pytest.mark.asyncio
async def test_score_all_unscored_jobs_continues_on_per_job_failure() -> None:
    job_repo = FakeJobRepository(
        jobs={1: make_job(id=1), 2: make_job(id=2), 3: make_job(id=3)}
    )
    profile_repo = FakeProfileRepository(profiles={1: make_profile(id=1)})
    match_repo = FakeMatchScoreRepository(fail_upsert_ids={2})
    llm = FakeLLMClient(
        responses=[
            {"score": 88, "explanation": "Good fit."},
            {"score": 75, "explanation": "Still good fit."},
            {"score": 62, "explanation": "Moderate fit."},
        ]
    )
    service = make_service(job_repo, profile_repo, match_repo, llm)

    scored = await service.score_all_unscored_jobs(profile_id=1)

    assert scored == 2
    assert len(match_repo.upsert_calls) == 3


def test_determine_category_boundary_mapping() -> None:
    service = make_service(
        FakeJobRepository(),
        FakeProfileRepository(),
        FakeMatchScoreRepository(),
        FakeLLMClient(responses=[]),
    )

    assert service._determine_category(100) == "Most Relevant"
    assert service._determine_category(90) == "Most Relevant"
    assert service._determine_category(89) == "Relevant"
    assert service._determine_category(70) == "Relevant"
    assert service._determine_category(69) == "Somewhat Relevant"
    assert service._determine_category(50) == "Somewhat Relevant"
    assert service._determine_category(49) == "Not Relevant"
    assert service._determine_category(0) == "Not Relevant"
