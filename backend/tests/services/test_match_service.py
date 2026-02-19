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
from src.repositories.job_enrichment import JobEnrichmentRepository
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

    async def get_first(self) -> SimpleNamespace | None:
        """Fetch the first profile ordered by id.

        Returns:
            First profile object when present, otherwise ``None``.
        """
        if not self.profiles:
            return None
        first_id = min(self.profiles.keys())
        return self.profiles[first_id]


@dataclass
class FakeMatchScoreRepository:
    """In-memory async repository stub for match scores."""

    scores_by_key: dict[tuple[int, int], SimpleNamespace] = field(default_factory=dict)
    scored_jobs: list[tuple[SimpleNamespace, int]] = field(default_factory=list)
    fail_upsert_ids: set[int] = field(default_factory=set)
    upsert_calls: list[tuple[int, int, dict[str, Any]]] = field(default_factory=list)
    get_jobs_by_score_calls: list[tuple[int, int, int, str | None, bool]] = field(
        default_factory=list
    )
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

    async def get_jobs_by_score(
        self,
        profile_id: int,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
    ) -> list[tuple[SimpleNamespace, int]]:
        """List scored jobs for assertions in relevance listing tests.

        Args:
            profile_id: Target profile id.
            skip: Pagination offset.
            limit: Pagination cap.
            platform: Optional platform filter.
            is_active: Active status filter.

        Returns:
            Filtered scored job tuples.
        """
        self.get_jobs_by_score_calls.append(
            (profile_id, skip, limit, platform, is_active)
        )
        rows = [
            row
            for row in self.scored_jobs
            if row[0].is_active is is_active
            and (platform is None or row[0].platform == platform)
        ]
        return rows[skip : skip + limit]


@dataclass
class FakeJobEnrichmentRepository:
    """In-memory async repository stub for job enrichments."""

    enrichments_by_job_id: dict[int, list[SimpleNamespace]] = field(
        default_factory=dict
    )
    get_latest_calls: list[int] = field(default_factory=list)
    list_by_job_ids_calls: list[list[int]] = field(default_factory=list)

    async def get_latest_by_job_id(self, job_id: int) -> SimpleNamespace | None:
        """Fetch latest enrichment for one job id.

        Args:
            job_id: Target job identifier.

        Returns:
            Newest enrichment row when present, otherwise ``None``.
        """
        self.get_latest_calls.append(job_id)
        rows = self.enrichments_by_job_id.get(job_id, [])
        if not rows:
            return None
        return max(rows, key=lambda row: (row.enriched_at, row.id))

    async def list_by_job_ids(self, job_ids: list[int]) -> list[SimpleNamespace]:
        """List all enrichment rows for provided job ids.

        Args:
            job_ids: Job ids filter.

        Returns:
            Flattened enrichment rows for matching job ids.
        """
        self.list_by_job_ids_calls.append(job_ids.copy())
        rows: list[SimpleNamespace] = []
        for job_id in job_ids:
            rows.extend(self.enrichments_by_job_id.get(job_id, []))
        return rows


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
    enrichment_repo: FakeJobEnrichmentRepository | None = None,
) -> MatchService:
    """Create MatchService with casted test doubles.

    Args:
        job_repo: Fake jobs repository.
        profile_repo: Fake profiles repository.
        match_repo: Fake match score repository.
        llm: Fake LLM client.
        enrichment_repo: Optional fake enrichment repository.

    Returns:
        Configured MatchService instance for unit tests.
    """
    return MatchService(
        job_repo=cast(JobRepository, job_repo),
        profile_repo=cast(ProfileRepository, profile_repo),
        match_repo=cast(MatchScoreRepository, match_repo),
        enrichment_repo=cast(JobEnrichmentRepository, enrichment_repo)
        if enrichment_repo is not None
        else None,
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
async def test_score_job_prompt_prefers_enrichment_fields_with_raw_fallback() -> None:
    job_repo = FakeJobRepository(
        jobs={
            1: make_job(
                id=1,
                skills=["Python"],
                job_type="Contract",
                salary_range={"min": 90000, "max": 130000, "currency": "AUD"},
                location="Brisbane",
            )
        }
    )
    profile_repo = FakeProfileRepository(profiles={1: make_profile(id=1)})
    match_repo = FakeMatchScoreRepository()
    enrichment_repo = FakeJobEnrichmentRepository(
        enrichments_by_job_id={
            1: [
                SimpleNamespace(
                    id=11,
                    job_id=1,
                    skills=["Go", "Kubernetes"],
                    job_type=None,
                    salary_min=120000.0,
                    salary_max=160000.0,
                    salary_currency="AUD",
                    salary_period="year",
                    salary_raw="$120k-$160k",
                    location_normalized=None,
                    status="completed",
                    extractor_version="v2",
                    enriched_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
                )
            ]
        }
    )
    llm = FakeLLMClient(
        responses=[
            {
                "score": 84,
                "category": "Relevant",
                "explanation": "Good alignment.",
            }
        ]
    )
    service = make_service(job_repo, profile_repo, match_repo, llm, enrichment_repo)

    await service.score_job(job_id=1, profile_id=1)

    prompt = llm.generate_json_calls[0][0]
    assert '"skills": ["Go", "Kubernetes"]' in prompt
    assert '"job_type": "Contract"' in prompt
    assert '"location": "Brisbane"' in prompt
    assert (
        '"salary_range": {"currency": "AUD", "max": 160000.0, "min": 120000.0, '
        '"period": "year", "raw": "$120k-$160k"}'
    ) in prompt
    assert enrichment_repo.get_latest_calls == [1]


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


@pytest.mark.asyncio
async def test_list_jobs_by_relevance_requires_profile() -> None:
    service = make_service(
        FakeJobRepository(),
        FakeProfileRepository(),
        FakeMatchScoreRepository(),
        FakeLLMClient(responses=[]),
    )

    with pytest.raises(BusinessLogicError, match="Create a profile first"):
        await service.list_jobs_by_relevance()


@pytest.mark.asyncio
async def test_list_jobs_by_relevance_returns_scored_jobs_sorted() -> None:
    profile_repo = FakeProfileRepository(profiles={7: make_profile(id=7)})
    match_repo = FakeMatchScoreRepository(
        scored_jobs=[
            (make_job(id=2, external_id="relevance-2"), 95),
            (make_job(id=1, external_id="relevance-1"), 82),
        ]
    )
    service = make_service(
        FakeJobRepository(),
        profile_repo,
        match_repo,
        FakeLLMClient(responses=[]),
    )

    results = await service.list_jobs_by_relevance(skip=0, limit=10)

    assert [row.id for row in results] == [2, 1]
    assert [row.relevance_score for row in results] == [95, 82]
    assert match_repo.get_jobs_by_score_calls[0] == (7, 0, 10, None, True)


@pytest.mark.asyncio
async def test_list_jobs_by_relevance_merges_latest_enrichment_metadata() -> None:
    profile_repo = FakeProfileRepository(profiles={7: make_profile(id=7)})
    match_repo = FakeMatchScoreRepository(
        scored_jobs=[
            (
                make_job(
                    id=2,
                    external_id="relevance-2",
                    location="Raw Sydney",
                    skills=["Python"],
                    job_type="Contract",
                    salary_range={"min": 100000, "currency": "AUD"},
                ),
                95,
            ),
        ]
    )
    enrichment_repo = FakeJobEnrichmentRepository(
        enrichments_by_job_id={
            2: [
                SimpleNamespace(
                    id=22,
                    job_id=2,
                    skills=["Python", "FastAPI"],
                    job_type="Full-time",
                    salary_min=150000.0,
                    salary_max=190000.0,
                    salary_currency="AUD",
                    salary_period="year",
                    salary_raw="$150k-$190k",
                    location_normalized="Sydney, AU",
                    status="completed",
                    extractor_version="v3",
                    enriched_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
                )
            ]
        }
    )
    service = make_service(
        FakeJobRepository(),
        profile_repo,
        match_repo,
        FakeLLMClient(responses=[]),
        enrichment_repo,
    )

    results = await service.list_jobs_by_relevance(skip=0, limit=10)

    assert len(results) == 1
    assert results[0].id == 2
    assert results[0].relevance_score == 95
    assert results[0].skills == ["Python", "FastAPI"]
    assert results[0].job_type == "Full-time"
    assert results[0].location == "Sydney, AU"
    assert results[0].salary_range == {
        "min": 150000.0,
        "max": 190000.0,
        "currency": "AUD",
        "period": "year",
        "raw": "$150k-$190k",
    }
    assert results[0].enrichment_status == "completed"
    assert results[0].enrichment_version == "v3"
    assert results[0].enrichment_updated_at == datetime(
        2026, 1, 10, tzinfo=timezone.utc
    )
    assert enrichment_repo.list_by_job_ids_calls == [[2]]
