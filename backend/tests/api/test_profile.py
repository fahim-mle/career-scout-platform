"""Integration tests for Profile API singleton endpoints."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_db_session
from src.main import app


def build_profile_payload() -> dict[str, Any]:
    """Build a valid profile payload for API create calls.

    Returns:
        Valid create payload for profile endpoint tests.
    """
    return {
        "name": "Jane Candidate",
        "location": "Brisbane",
        "experience_years": 5,
        "skills": ["Python", "FastAPI"],
        "preferences": {"remote": True},
    }


@pytest_asyncio.fixture
async def client(db_session: Any) -> AsyncClient:
    """Provide an API client with test DB dependency override.

    Args:
        db_session: Test DB session fixture.

    Returns:
        Async HTTP client bound to the app under test.
    """

    async def override_get_db() -> Any:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client

    app.dependency_overrides.clear()


class TestProfileAPI:
    """Covers profile endpoint integration behavior."""

    @pytest.mark.asyncio
    async def test_create_profile_success(self, client: AsyncClient) -> None:
        payload = build_profile_payload()

        response = await client.post("/api/v1/profile", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == payload["name"]
        assert body["experience_years"] == payload["experience_years"]
        assert body["skills"] == payload["skills"]

    @pytest.mark.asyncio
    async def test_create_profile_duplicate_rejected(self, client: AsyncClient) -> None:
        payload = build_profile_payload()

        first = await client.post("/api/v1/profile", json=payload)
        second = await client.post("/api/v1/profile", json=payload)

        assert first.status_code == 201
        assert second.status_code == 409
        assert "already exists" in second.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_profile_success(self, client: AsyncClient) -> None:
        create_response = await client.post(
            "/api/v1/profile", json=build_profile_payload()
        )

        response = await client.get("/api/v1/profile")

        assert create_response.status_code == 201
        assert response.status_code == 200
        assert response.json()["name"] == "Jane Candidate"

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/profile")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_profile_success(self, client: AsyncClient) -> None:
        await client.post("/api/v1/profile", json=build_profile_payload())

        response = await client.patch(
            "/api/v1/profile",
            json={"location": "Melbourne", "skills": ["Python", "SQLAlchemy"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["location"] == "Melbourne"
        assert body["skills"] == ["Python", "SQLAlchemy"]

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self, client: AsyncClient) -> None:
        response = await client.patch("/api/v1/profile", json={"location": "Sydney"})

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_profile_success(self, client: AsyncClient) -> None:
        await client.post("/api/v1/profile", json=build_profile_payload())

        delete_response = await client.delete("/api/v1/profile")
        get_response = await client.get("/api/v1/profile")

        assert delete_response.status_code == 204
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_profile_not_found(self, client: AsyncClient) -> None:
        response = await client.delete("/api/v1/profile")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_profile_empty_skills_rejected(
        self, client: AsyncClient
    ) -> None:
        payload = build_profile_payload()
        payload["skills"] = []

        response = await client.post("/api/v1/profile", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_profile_negative_experience_rejected(
        self, client: AsyncClient
    ) -> None:
        payload = build_profile_payload()
        payload["experience_years"] = -1

        response = await client.post("/api/v1/profile", json=payload)

        assert response.status_code == 422
