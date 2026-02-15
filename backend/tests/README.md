# Backend Tests Guide

Use this folder for backend unit and integration tests.

## Run tests

From `backend/`:

```bash
make test
make test-cov
```

Quick direct run:

```bash
pytest -v
```

## AAA pattern (Arrange, Act, Assert)

Keep test bodies short and explicit.

```python
@pytest.mark.asyncio
async def test_get_job_returns_data(db_session, job_factory):
    # Arrange
    job = await job_factory.create(title="Backend Engineer")
    repo = JobRepository(db_session)
    service = JobService(repo)

    # Act
    result = await service.get_job(job.id)

    # Assert
    assert result.id == job.id
    assert result.title == "Backend Engineer"
```

## Fixtures vs factories

- Use fixtures (for example `db_session`, `client`) for shared setup and dependency wiring.
- Use factories (for example `job_factory`) to create readable per-test data.
- Prefer factory defaults, then override only fields needed by the test.

## Async test note

- Backend tests are async-first.
- Mark async tests with `@pytest.mark.asyncio`.
- `db_session` and `client` fixtures already handle async setup and cleanup.

## Templates

Copy-paste starter templates live in `backend/tests/TEMPLATES.md`.
