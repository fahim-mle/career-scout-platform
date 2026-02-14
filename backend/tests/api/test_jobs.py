"""Integration tests for Jobs API endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_db_session, get_job_service
from src.core.exceptions import BusinessLogicError
from src.main import app


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
    async def test_get_job_by_id_success(self, client: AsyncClient) -> None:
        create_response = await client.post(
            "/api/v1/jobs", json=build_job_payload("api-get-1")
        )
        job_id = create_response.json()["id"]

        response = await client.get(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 200
        assert response.json()["id"] == job_id

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
            async def get_job(self, job_id: int) -> dict[str, Any]:
                raise BusinessLogicError("service failure")

        app.dependency_overrides[get_job_service] = lambda: BrokenGetService()
        response = await client.get("/api/v1/jobs/1")
        app.dependency_overrides.pop(get_job_service, None)

        assert response.status_code == 400
        assert "service failure" in response.json()["detail"].lower()

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
