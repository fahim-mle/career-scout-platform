# Test Templates

Copy, paste, and adjust these minimal templates.

## Repository test template

```python
import pytest

from src.repositories.job import JobRepository
from src.core.exceptions import DuplicateJobError


@pytest.mark.asyncio
async def test_create_job_duplicate_raises(db_session, job_factory):
    # Arrange
    await job_factory.create(external_id="dup-1", platform="linkedin")
    repo = JobRepository(db_session)

    payload = {
        "external_id": "dup-1",
        "platform": "linkedin",
        "url": "https://linkedin.com/jobs/dup-1",
        "title": "Platform Engineer",
        "company": "Career Scout",
        "location": "Brisbane",
    }

    # Act / Assert
    with pytest.raises(DuplicateJobError):
        await repo.create(payload)
```

## Service test template

```python
import pytest

from src.core.exceptions import BusinessLogicError
from src.repositories.job import JobRepository
from src.schemas.job import JobCreate
from src.services.job_service import JobService


@pytest.mark.asyncio
async def test_create_job_rejects_future_date(db_session):
    # Arrange
    service = JobService(JobRepository(db_session))
    payload = JobCreate(
        external_id="future-1",
        platform="linkedin",
        url="https://linkedin.com/jobs/future-1",
        title="Future Job",
        company="Career Scout",
        location="Brisbane",
        posted_date="2100-01-01",
    )

    # Act / Assert
    with pytest.raises(BusinessLogicError, match="future"):
        await service.create_job(payload)
```

## API test template

```python
import pytest


@pytest.mark.asyncio
async def test_create_job_returns_201(client):
    # Arrange
    payload = {
        "external_id": "api-1",
        "platform": "linkedin",
        "url": "https://linkedin.com/jobs/api-1",
        "title": "Backend Engineer",
        "company": "Career Scout",
        "location": "Brisbane",
    }

    # Act
    response = await client.post("/api/v1/jobs", json=payload)

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["external_id"] == "api-1"
```
