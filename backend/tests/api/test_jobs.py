"""Integration tests for Jobs API endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, get_job_service
from src.core.exceptions import BusinessLogicError
from src.main import app
from src.models.job_enrichment import JobEnrichment
from src.models.match_score import MatchScore
from src.models.profile import Profile


ENRICHED_REQUIRED_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "external_id",
    "platform",
    "url",
    "title",
    "company",
    "location",
    "description_short",
    "description_full",
    "scraped_jobs",
    "metadata",
    "posted_date",
    "scraped_at",
    "is_active",
    "skills",
    "job_type",
    "salary_range",
    "enrichment_status",
    "enrichment_version",
    "enrichment_updated_at",
    "description_sections",
    "relevance_score",
}


def assert_enriched_job_shape(payload: dict[str, Any]) -> None:
    """Assert API response contains enriched jobs contract fields."""
    assert ENRICHED_REQUIRED_FIELDS.issubset(payload.keys())


def build_job_payload(
    external_id: str,
    *,
    platform: str = "linkedin",
    title: str = "Backend Engineer",
    company: str = "Career Scout",
    location: str = "Brisbane",
) -> dict[str, Any]:
    """Build a valid job payload for API create calls."""
    domain_map = {
        "linkedin": "linkedin.com",
        "seek": "seek.com.au",
        "indeed": "indeed.com",
    }
    return {
        "external_id": external_id,
        "platform": platform,
        "url": f"https://{domain_map[platform]}/jobs/{external_id}",
        "title": title,
        "company": company,
        "location": location,
    }


@pytest_asyncio.fixture
async def client(db_session: Any) -> AsyncClient:
    """Provide an API client with test DB dependency override."""

    async def override_get_db() -> Any:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client

    app.dependency_overrides.clear()


class TestJobsAPI:
    """Covers Jobs endpoint integration behavior."""

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/jobs")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_job_success(self, client: AsyncClient) -> None:
        payload = build_job_payload("api-create-1")

        response = await client.post("/api/v1/jobs", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["external_id"] == payload["external_id"]
        assert body["title"] == payload["title"]
        assert body["is_active"] is True

        list_response = await client.get("/api/v1/jobs")
        listed_job = list_response.json()[0]
        assert_enriched_job_shape(listed_job)
        assert listed_job["enrichment_status"] is None
        assert listed_job["enrichment_version"] is None
        assert listed_job["enrichment_updated_at"] is None
        assert listed_job["description_sections"] is None

    @pytest.mark.asyncio
    async def test_create_job_accepts_generic_metadata(
        self, client: AsyncClient
    ) -> None:
        payload = build_job_payload("api-create-meta-1")
        payload["scraped_jobs"] = "<div id='job-details'><p>Role Overview</p></div>"
        payload["metadata"] = {
            "platform": "linkedin",
            "posted_date_text": "1 day ago",
            "number_of_applicants": "Over 100 applicants",
            "promoted_by_hirer": True,
            "actively_reviewing_applicants": True,
        }

        response = await client.post("/api/v1/jobs", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["scraped_jobs"] == payload["scraped_jobs"]
        assert body["metadata"] == payload["metadata"]

    @pytest.mark.asyncio
    async def test_jobs_endpoints_keep_existing_fields_with_metadata_payload(
        self, client: AsyncClient
    ) -> None:
        """Metadata additions should not remove existing response contract fields."""
        payload = build_job_payload("api-contract-meta-1")
        payload["description_short"] = "Short summary"
        payload["description_full"] = "Long description"
        payload["scraped_jobs"] = "<main><p>raw html</p></main>"
        payload["metadata"] = {
            "platform": "linkedin",
            "location": "Brisbane",
            "date_posted": "1 day ago",
        }

        create_response = await client.post("/api/v1/jobs", json=payload)

        assert create_response.status_code == 201
        created = create_response.json()
        job_id = created["id"]
        for legacy_field in (
            "external_id",
            "platform",
            "url",
            "title",
            "company",
            "location",
            "description_short",
            "description_full",
            "is_active",
        ):
            assert legacy_field in created

        enriched_response = await client.get(f"/api/v1/jobs/{job_id}")
        raw_response = await client.get(f"/api/v1/scraped_raw_jobs/{job_id}")

        assert enriched_response.status_code == 200
        assert raw_response.status_code == 200
        enriched_body = enriched_response.json()
        raw_body = raw_response.json()
        assert_enriched_job_shape(enriched_body)
        assert raw_body["external_id"] == payload["external_id"]
        assert raw_body["description_short"] == "Short summary"
        assert raw_body["description_full"] == "Long description"
        assert raw_body["metadata"] == payload["metadata"]

    @pytest.mark.asyncio
    async def test_jobs_endpoints_roundtrip_seek_payload_without_contract_regression(
        self, client: AsyncClient
    ) -> None:
        """Seek-flavored payload should persist and return existing API contract fields."""
        payload = build_job_payload(
            "api-seek-roundtrip-1",
            platform="seek",
            location="Sydney NSW",
        )
        payload["description_short"] = "Work on backend platform services"
        payload["description_full"] = "Lead API delivery with Python and PostgreSQL"
        payload["job_type"] = "Full time"
        payload["salary_range"] = {
            "min": 140000,
            "max": 170000,
            "currency": "AUD",
            "raw": "$140k - $170k + super",
        }
        payload["scraped_jobs"] = (
            '<div data-automation="jobAdDetails"><p>Seek details</p></div>'
        )
        payload["metadata"] = {
            "platform": "seek",
            "location": "Sydney NSW",
            "work_type": "Full time",
            "classification": "Engineering",
            "subclassification": "Software Engineering",
            "salary_text": "$140k - $170k + super",
        }

        create_response = await client.post("/api/v1/jobs", json=payload)

        assert create_response.status_code == 201
        created = create_response.json()
        job_id = created["id"]
        assert created["platform"] == "seek"
        assert created["scraped_jobs"] == payload["scraped_jobs"]
        assert created["metadata"] == payload["metadata"]
        assert created["salary_range"] == payload["salary_range"]

        enriched_response = await client.get(f"/api/v1/jobs/{job_id}")
        raw_response = await client.get(f"/api/v1/scraped_raw_jobs/{job_id}")

        assert enriched_response.status_code == 200
        assert raw_response.status_code == 200
        enriched_body = enriched_response.json()
        raw_body = raw_response.json()

        assert_enriched_job_shape(enriched_body)
        assert enriched_body["platform"] == "seek"
        assert "metadata" in enriched_body
        assert raw_body["platform"] == "seek"
        assert raw_body["salary_range"] == payload["salary_range"]
        assert raw_body["scraped_jobs"] == payload["scraped_jobs"]
        assert raw_body["metadata"] == payload["metadata"]

    @pytest.mark.asyncio
    async def test_jobs_endpoints_roundtrip_indeed_payload_without_contract_regression(
        self, client: AsyncClient
    ) -> None:
        """Indeed-flavored payload should preserve API contract and metadata fields."""
        payload = build_job_payload(
            "api-indeed-roundtrip-1",
            platform="indeed",
            location="Brisbane QLD",
        )
        payload["description_short"] = "Own backend integrations"
        payload["description_full"] = "Build resilient async services for job ingestion"
        payload["job_type"] = "Full-Time"
        payload["salary_range"] = {
            "min": 125000,
            "max": 155000,
            "currency": "AUD",
            "raw": "$125k - $155k per year",
        }
        payload["scraped_jobs"] = (
            '<div id="jobDescriptionText"><p>Indeed details</p></div>'
        )
        payload["metadata"] = {
            "platform": "indeed",
            "location": "Brisbane QLD",
            "date_posted": "Posted today",
            "work_type": "Full-Time",
            "salary_text": "$125k - $155k per year",
            "company_rating": "4.4/5",
            "benefits": ["Work from home", "Gym membership"],
        }

        create_response = await client.post("/api/v1/jobs", json=payload)

        assert create_response.status_code == 201
        created = create_response.json()
        job_id = created["id"]
        assert created["platform"] == "indeed"
        assert created["scraped_jobs"] == payload["scraped_jobs"]
        assert created["metadata"] == payload["metadata"]
        assert created["salary_range"] == payload["salary_range"]

        enriched_response = await client.get(f"/api/v1/jobs/{job_id}")
        raw_response = await client.get(f"/api/v1/scraped_raw_jobs/{job_id}")

        assert enriched_response.status_code == 200
        assert raw_response.status_code == 200
        enriched_body = enriched_response.json()
        raw_body = raw_response.json()

        assert_enriched_job_shape(enriched_body)
        assert enriched_body["platform"] == "indeed"
        assert "metadata" in enriched_body
        assert raw_body["platform"] == "indeed"
        assert raw_body["salary_range"] == payload["salary_range"]
        assert raw_body["scraped_jobs"] == payload["scraped_jobs"]
        assert raw_body["metadata"] == payload["metadata"]

    @pytest.mark.asyncio
    async def test_list_jobs_with_data(self, client: AsyncClient) -> None:
        await client.post("/api/v1/jobs", json=build_job_payload("api-list-1"))
        await client.post("/api/v1/jobs", json=build_job_payload("api-list-2"))

        response = await client.get("/api/v1/jobs")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["external_id"] == "api-list-2"
        assert body[1]["external_id"] == "api-list-1"
        assert_enriched_job_shape(body[0])
        assert_enriched_job_shape(body[1])
        assert body[0]["skills"] is None
        assert body[0]["job_type"] is None
        assert body[0]["salary_range"] is None
        assert body[0]["enrichment_status"] is None
        assert body[0]["enrichment_version"] is None
        assert body[0]["enrichment_updated_at"] is None
        assert body[0]["description_sections"] is None

    @pytest.mark.asyncio
    async def test_scraped_raw_jobs_returns_raw_schema(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/v1/jobs", json=build_job_payload("api-raw-list-1"))

        response = await client.get("/api/v1/scraped_raw_jobs")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["external_id"] == "api-raw-list-1"
        assert "enrichment_status" not in body[0]
        assert "enrichment_version" not in body[0]
        assert "enrichment_updated_at" not in body[0]

    @pytest.mark.asyncio
    async def test_list_jobs_pagination(self, client: AsyncClient) -> None:
        await client.post("/api/v1/jobs", json=build_job_payload("api-page-1"))
        await client.post("/api/v1/jobs", json=build_job_payload("api-page-2"))
        await client.post("/api/v1/jobs", json=build_job_payload("api-page-3"))

        response = await client.get("/api/v1/jobs?skip=1&limit=1")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["external_id"] == "api-page-2"

    @pytest.mark.asyncio
    async def test_list_jobs_filter_platform(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/jobs",
            json=build_job_payload("api-platform-1", platform="linkedin"),
        )
        await client.post(
            "/api/v1/jobs", json=build_job_payload("api-platform-2", platform="seek")
        )

        response = await client.get("/api/v1/jobs?platform=seek")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["platform"] == "seek"

    @pytest.mark.asyncio
    async def test_list_jobs_filter_inactive(self, client: AsyncClient) -> None:
        active_payload = build_job_payload("api-active-1")
        inactive_payload = build_job_payload("api-inactive-1")
        inactive_payload["is_active"] = False

        await client.post("/api/v1/jobs", json=active_payload)
        await client.post("/api/v1/jobs", json=inactive_payload)

        response = await client.get("/api/v1/jobs?is_active=false")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["external_id"] == "api-inactive-1"

    @pytest.mark.asyncio
    async def test_list_jobs_invalid_platform_returns_400(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/jobs?platform=monster")

        assert response.status_code == 400
        assert "invalid platform" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_jobs_sort_relevance_returns_scored_jobs(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        first_job_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-sort-relevance-1")
        )
        second_job_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-sort-relevance-2")
        )

        profile = Profile(
            name="Sort Tester",
            location="Brisbane",
            experience_years=5,
            skills=["Python", "FastAPI"],
            preferences={"remote": True},
        )
        db_session.add(profile)
        await db_session.commit()
        await db_session.refresh(profile)

        first_job_id = first_job_response.json()["id"]
        second_job_id = second_job_response.json()["id"]
        db_session.add_all(
            [
                MatchScore(
                    job_id=first_job_id,
                    profile_id=profile.id,
                    relevance_score=72,
                    category="Relevant",
                    explanation="Good fit",
                    scored_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
                MatchScore(
                    job_id=second_job_id,
                    profile_id=profile.id,
                    relevance_score=94,
                    category="Most Relevant",
                    explanation="Excellent fit",
                    scored_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
            ]
        )
        db_session.add_all(
            [
                JobEnrichment(
                    job_id=first_job_id,
                    extractor_version="v1",
                    status="completed",
                    skills=["Python", "SQL"],
                    job_type="Contract",
                    salary_min=110000.0,
                    salary_max=140000.0,
                    salary_currency="AUD",
                    salary_period="year",
                    salary_raw="$110k-$140k",
                    location_normalized="Brisbane, AU",
                    enriched_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
                JobEnrichment(
                    job_id=second_job_id,
                    extractor_version="v2",
                    status="completed",
                    skills=["Python", "FastAPI", "PostgreSQL"],
                    job_type="Full-time",
                    salary_min=150000.0,
                    salary_max=190000.0,
                    salary_currency="AUD",
                    salary_period="year",
                    salary_raw="$150k-$190k",
                    location_normalized="Sydney, AU",
                    enriched_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
                ),
            ]
        )
        await db_session.commit()

        response = await client.get("/api/v1/jobs?sort=relevance")

        assert response.status_code == 200
        body = response.json()
        assert_enriched_job_shape(body[0])
        assert_enriched_job_shape(body[1])
        assert [item["id"] for item in body] == [second_job_id, first_job_id]
        assert [item["relevance_score"] for item in body] == [94, 72]
        assert body[0]["skills"] == ["Python", "FastAPI", "PostgreSQL"]
        assert body[0]["job_type"] == "Full-time"
        assert body[0]["location"] == "Sydney, AU"
        assert body[0]["salary_range"] == {
            "min": 150000.0,
            "max": 190000.0,
            "currency": "AUD",
            "period": "year",
            "raw": "$150k-$190k",
        }
        assert body[0]["enrichment_status"] == "completed"
        assert body[0]["enrichment_version"] == "v2"
        assert body[0]["enrichment_updated_at"] is not None

    @pytest.mark.asyncio
    async def test_list_jobs_sort_relevance_without_profile_returns_400(
        self, client: AsyncClient
    ) -> None:
        await client.post(
            "/api/v1/jobs", json=build_job_payload("api-sort-no-profile-1")
        )

        response = await client.get("/api/v1/jobs?sort=relevance")

        assert response.status_code == 400
        assert "create a profile first" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_jobs_sort_relevance_applies_filters(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        matching_payload = build_job_payload(
            "api-sort-filter-1",
            platform="seek",
            title="Senior Python Engineer",
            company="Acme",
            location="Brisbane",
        )
        matching_payload["job_type"] = "Full-time (Permanent)"

        wrong_job_type = build_job_payload(
            "api-sort-filter-2",
            platform="seek",
            title="Python Engineer",
            company="Acme",
            location="Brisbane",
        )
        wrong_job_type["job_type"] = "Contract"

        wrong_platform = build_job_payload(
            "api-sort-filter-3",
            platform="linkedin",
            title="Senior Python Engineer",
            company="Acme",
            location="Brisbane",
        )
        wrong_platform["job_type"] = "Full-time"

        create_responses = [
            await client.post("/api/v1/jobs", json=payload)
            for payload in [matching_payload, wrong_job_type, wrong_platform]
        ]
        assert all(response.status_code == 201 for response in create_responses)

        profile = Profile(
            name="Filter Tester",
            location="Brisbane",
            experience_years=5,
            skills=["Python", "FastAPI"],
            preferences={"remote": True},
        )
        db_session.add(profile)
        await db_session.commit()
        await db_session.refresh(profile)

        created_ids = [response.json()["id"] for response in create_responses]
        db_session.add_all(
            [
                MatchScore(
                    job_id=created_ids[0],
                    profile_id=profile.id,
                    relevance_score=95,
                    category="Most Relevant",
                    explanation="Excellent fit",
                    scored_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
                MatchScore(
                    job_id=created_ids[1],
                    profile_id=profile.id,
                    relevance_score=90,
                    category="Most Relevant",
                    explanation="Strong fit",
                    scored_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
                MatchScore(
                    job_id=created_ids[2],
                    profile_id=profile.id,
                    relevance_score=88,
                    category="Relevant",
                    explanation="Good fit",
                    scored_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
            ]
        )
        await db_session.commit()

        response = await client.get(
            "/api/v1/jobs",
            params={
                "sort": "relevance",
                "platform": "seek",
                "job_type": "full-time",
                "search": "python",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == created_ids[0]

    @pytest.mark.asyncio
    async def test_list_jobs_relevance_invalid_platform_returns_400(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/jobs?sort=relevance&platform=monster")

        assert response.status_code == 400
        assert "invalid platform" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_job_by_id_success(self, client: AsyncClient) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-get-1")
        )
        job_id = create_response.json()["id"]

        response = await client.get(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == job_id
        assert_enriched_job_shape(body)
        assert body["enrichment_status"] is None

    @pytest.mark.asyncio
    async def test_get_job_by_id_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/jobs/999999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_job_business_error_returns_400(
        self, client: AsyncClient
    ) -> None:
        class BrokenGetService:
            async def get_enriched_job(self, job_id: int) -> dict[str, Any]:
                raise BusinessLogicError("service failure")

        app.dependency_overrides[get_job_service] = lambda: BrokenGetService()
        response = await client.get("/api/v1/jobs/1")
        app.dependency_overrides.pop(get_job_service, None)

        assert response.status_code == 400
        assert "service failure" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_scraped_raw_job_by_id_success(self, client: AsyncClient) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-raw-get-1")
        )
        job_id = create_response.json()["id"]

        response = await client.get(f"/api/v1/scraped_raw_jobs/{job_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == job_id
        assert body["external_id"] == "api-raw-get-1"
        assert "enrichment_status" not in body
        assert "enrichment_version" not in body
        assert "enrichment_updated_at" not in body

    @pytest.mark.asyncio
    async def test_get_scraped_raw_job_by_id_not_found(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/scraped_raw_jobs/999999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_job_duplicate_conflict(self, client: AsyncClient) -> None:
        payload = build_job_payload("api-dup-1")

        first = await client.post("/api/v1/jobs", json=payload)
        second = await client.post("/api/v1/jobs", json=payload)

        assert first.status_code == 201
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_create_job_validation_error_missing_field(
        self, client: AsyncClient
    ) -> None:
        payload = build_job_payload("api-invalid-1")
        payload.pop("title")

        response = await client.post("/api/v1/jobs", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_job_rejects_oversized_scraped_jobs_payload(
        self, client: AsyncClient
    ) -> None:
        payload = build_job_payload("api-invalid-scraped-jobs-1")
        payload["scraped_jobs"] = "x" * 100_001

        response = await client.post("/api/v1/jobs", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_job_future_date_rejected(self, client: AsyncClient) -> None:
        payload = build_job_payload("api-future-1")
        payload["posted_date"] = (date.today() + timedelta(days=1)).isoformat()

        response = await client.post("/api/v1/jobs", json=payload)

        assert response.status_code == 400
        assert "future" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_job_url_domain_mismatch_rejected(
        self, client: AsyncClient
    ) -> None:
        payload = build_job_payload("api-domain-1", platform="linkedin")
        payload["url"] = "https://indeed.com/jobs/api-domain-1"

        response = await client.post("/api/v1/jobs", json=payload)

        assert response.status_code == 400
        assert "does not match platform" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_job_success(self, client: AsyncClient) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-update-1", title="Old title")
        )
        job_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"title": "New title"},
        )

        assert response.status_code == 200
        assert response.json()["title"] == "New title"

    @pytest.mark.asyncio
    async def test_update_job_not_found(self, client: AsyncClient) -> None:
        response = await client.patch("/api/v1/jobs/999999", json={"title": "Nope"})

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_job_rejects_immutable_external_id(
        self, client: AsyncClient
    ) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-immutable-1")
        )
        job_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"external_id": "api-immutable-2"},
        )

        assert response.status_code == 400
        assert "external_id cannot be changed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_job_rejects_immutable_platform(
        self, client: AsyncClient
    ) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-platform-change-1")
        )
        job_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"platform": "seek"},
        )

        assert response.status_code == 400
        assert "platform cannot be changed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_job_rejects_shorter_description(
        self, client: AsyncClient
    ) -> None:
        payload = build_job_payload("api-desc-1")
        payload["description_full"] = "This is a much longer description for baseline."
        create_response = await client.post("/api/v1/jobs", json=payload)
        job_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"description_full": "short"},
        )

        assert response.status_code == 400
        assert "must be longer" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_job_duplicate_conflict_returns_409(
        self, client: AsyncClient
    ) -> None:
        class BrokenUpdateService:
            async def update_job(
                self, job_id: int, payload: dict[str, Any]
            ) -> dict[str, Any]:
                raise BusinessLogicError("job already exists")

        app.dependency_overrides[get_job_service] = lambda: BrokenUpdateService()
        response = await client.patch("/api/v1/jobs/1", json={"title": "updated"})
        app.dependency_overrides.pop(get_job_service, None)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_job_success_and_soft_delete_verified(
        self, client: AsyncClient
    ) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-delete-1")
        )
        job_id = create_response.json()["id"]

        delete_response = await client.delete(f"/api/v1/jobs/{job_id}")
        get_response = await client.get(f"/api/v1/jobs/{job_id}")

        assert delete_response.status_code == 204
        assert get_response.status_code == 200
        assert get_response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_job_not_found(self, client: AsyncClient) -> None:
        response = await client.delete("/api/v1/jobs/999999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job_idempotent(self, client: AsyncClient) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-delete-repeat-1")
        )
        job_id = create_response.json()["id"]

        first = await client.delete(f"/api/v1/jobs/{job_id}")
        second = await client.delete(f"/api/v1/jobs/{job_id}")

        assert first.status_code == 204
        assert second.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_job_business_error_returns_400(
        self, client: AsyncClient
    ) -> None:
        class BrokenDeleteService:
            async def delete_job(self, job_id: int) -> bool:
                raise BusinessLogicError("cannot delete now")

        app.dependency_overrides[get_job_service] = lambda: BrokenDeleteService()
        response = await client.delete("/api/v1/jobs/1")
        app.dependency_overrides.pop(get_job_service, None)

        assert response.status_code == 400
        assert "cannot delete now" in response.json()["detail"].lower()


# ── New filter / search tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_jobs_filters_by_job_type(client: AsyncClient) -> None:
    """GET /jobs?job_type=Full-time should return only matching jobs."""
    fulltime_payload = build_job_payload(
        "jt-ft-1", platform="seek", title="Full-time Role"
    )
    fulltime_payload["job_type"] = "Full-time"
    contract_payload = build_job_payload(
        "jt-ct-1", platform="seek", title="Contract Role"
    )
    contract_payload["job_type"] = "Contract"

    r1 = await client.post("/api/v1/jobs", json=fulltime_payload)
    r2 = await client.post("/api/v1/jobs", json=contract_payload)
    assert r1.status_code == 201
    assert r2.status_code == 201

    response = await client.get("/api/v1/jobs", params={"job_type": "Full-time"})

    assert response.status_code == 200
    titles = [j["title"] for j in response.json()]
    assert "Full-time Role" in titles
    assert "Contract Role" not in titles


@pytest.mark.asyncio
async def test_list_jobs_search_filters_by_title(client: AsyncClient) -> None:
    """GET /jobs?search=<keyword> should return only jobs matching title/company/location."""
    eng_payload = build_job_payload(
        "srch-api-1", platform="linkedin", title="Python Engineer"
    )
    des_payload = build_job_payload(
        "srch-api-2", platform="linkedin", title="UX Designer"
    )

    r1 = await client.post("/api/v1/jobs", json=eng_payload)
    r2 = await client.post("/api/v1/jobs", json=des_payload)
    assert r1.status_code == 201
    assert r2.status_code == 201

    response = await client.get("/api/v1/jobs", params={"search": "python"})

    assert response.status_code == 200
    titles = [j["title"] for j in response.json()]
    assert "Python Engineer" in titles
    assert "UX Designer" not in titles


@pytest.mark.asyncio
async def test_list_jobs_search_empty_result(client: AsyncClient) -> None:
    """GET /jobs?search=<no match> should return empty list."""
    response = await client.get(
        "/api/v1/jobs", params={"search": "xyzzy-guaranteed-no-match-api"}
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_jobs_combined_job_type_and_search(client: AsyncClient) -> None:
    """Combining job_type and search should apply both filters (AND logic)."""
    match_payload = build_job_payload(
        "comb-1", platform="seek", title="Contract Python Dev"
    )
    match_payload["job_type"] = "Contract"

    no_match_fulltime = build_job_payload(
        "comb-2", platform="seek", title="Full-time Python Dev"
    )
    no_match_fulltime["job_type"] = "Full-time"

    no_match_contract = build_job_payload(
        "comb-3", platform="seek", title="Contract Java Dev"
    )
    no_match_contract["job_type"] = "Contract"

    for p in [match_payload, no_match_fulltime, no_match_contract]:
        r = await client.post("/api/v1/jobs", json=p)
        assert r.status_code == 201

    response = await client.get(
        "/api/v1/jobs", params={"job_type": "Contract", "search": "python"}
    )

    assert response.status_code == 200
    titles = [j["title"] for j in response.json()]
    assert "Contract Python Dev" in titles
    assert "Full-time Python Dev" not in titles
    assert "Contract Java Dev" not in titles
