# Backend

FastAPI backend for Career Scout — handles job ingestion, enrichment, profile management, CV parsing, and AI-powered job scoring.

## Tech stack

| Layer | Technology |
| --- | --- |
| API framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy (async) + asyncpg |
| Migrations | Alembic |
| Task queue | Celery + Redis |
| LLM integration | Ollama (local) via HTTP |
| CV parsing | pypdf, python-docx |
| Scraping | Playwright (Chromium) |
| Validation | Pydantic v2 |
| Logging | Loguru |
| Metrics | prometheus-fastapi-instrumentator |
| Testing | pytest + pytest-asyncio |

## Features

- **Jobs API** — CRUD with soft delete, immutability rules, and filtering
- **Profile API** — singleton profile with CV upload (PDF/DOCX), LLM-based resume parsing
- **Job enrichment** — heuristic skill/salary/job-type extraction from raw descriptions
- **Match scoring** — LLM scores each job against your profile (0–100) with explanation
- **Scraper** — Playwright-based LinkedIn scraper with Celery task orchestration
- **Observability** — structured Loguru logs, Prometheus metrics endpoint
- **Health checks** — `/api/v1/health` with DB and Redis dependency status

## Running with Docker (recommended)

The backend runs as part of the full platform. From the project root:

```bash
docker compose up -d postgres redis ollama backend
```

Alembic migrations run automatically on startup via `scripts/start-backend.sh`.

## Running locally (without Docker)

### 1. Set up virtualenv

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` (or set env vars directly). You need a running PostgreSQL and Redis instance. Minimum required vars:

```bash
DB_HOST=localhost
DB_NAME=career-scout
DB_USER=postgres
DB_PASSWORD=yourpassword
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:latest
```

### 3. Run migrations

```bash
python -m alembic upgrade head
```

### 4. Start the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API reference

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/health` | Health check (DB + Redis) |
| GET | `/api/v1/jobs` | List jobs with filters |
| GET | `/api/v1/jobs/{id}` | Get single job |
| POST | `/api/v1/jobs` | Create job |
| PATCH | `/api/v1/jobs/{id}` | Update job |
| DELETE | `/api/v1/jobs/{id}` | Soft delete job |
| GET | `/api/v1/profile` | Get profile |
| POST | `/api/v1/profile` | Create profile |
| PATCH | `/api/v1/profile` | Update profile |
| DELETE | `/api/v1/profile` | Delete profile |
| POST | `/api/v1/profile/cv` | Upload CV (PDF/DOCX), parse with LLM |

Interactive docs at <http://localhost:8000/docs>.

## Testing

```bash
make test            # run all tests
make test-cov        # with coverage (min 80%)
make test-fast       # skip slow integration tests
make test-verbose    # verbose output
```

Open the HTML coverage report after `make test-cov`:

```bash
xdg-open htmlcov/index.html   # Linux
open htmlcov/index.html        # macOS
```

## Scraper

The scraper requires `SCRAPER_ENABLED=true` and valid LinkedIn credentials.

```bash
# Trigger a single LinkedIn scrape
docker compose exec celery-worker python -m celery \
  -A src.celery_app.celery_app call \
  src.tasks.scraper_tasks.scrape_linkedin_jobs \
  --kwargs='{"query":"Python Developer","location":"Brisbane, QLD","limit":10}'

# Trigger the full profile-set scrape (reads linkedin_search_profiles.json)
docker compose exec celery-worker python -m celery \
  -A src.celery_app.celery_app call \
  src.tasks.scraper_tasks.scrape_linkedin_profile_set
```

Search profiles are configured in `src/scrapers/config/linkedin_search_profiles.json`.

## CV upload

`POST /api/v1/profile/cv` accepts `multipart/form-data` with a `file` field.

- Accepted types: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- Max size: 10 MB (configurable via `MAX_UPLOAD_SIZE_MB`)
- The backend extracts text, sends it to Ollama, and stores the plain-text summary in `profile.resume_text`

## Project structure

```text
backend/
├── alembic/           — migration files
├── scripts/           — start-backend.sh, migration helpers
├── src/
│   ├── ai/            — LLM client, CV parser, prompts
│   ├── api/           — FastAPI routers (v1)
│   ├── core/          — config, exceptions, logging
│   ├── db/            — session factory, base model
│   ├── models/        — SQLAlchemy ORM models
│   ├── repositories/  — async DB access layer
│   ├── schemas/       — Pydantic request/response models
│   ├── scrapers/      — Playwright scraper implementations
│   ├── services/      — business logic layer
│   └── tasks/         — Celery task definitions
├── tests/             — pytest test suite
├── main.py            — FastAPI app entry point
├── requirements.in    — direct dependencies
└── requirements.txt   — compiled + hashed lockfile
```
