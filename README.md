## Career Scout Platform

Career Scout is a job-tracking backend platform for collecting and managing job listings, with built-in observability for local development.

### What it does (current status)
- Provides a FastAPI backend with request-level logging and standardized error responses.
- Exposes Jobs CRUD APIs (`/api/v1/jobs`) with business rules (immutability, soft delete, validation).
- Includes health checks at `/api/v1/health`.
- Provides OpenAPI/Swagger docs for API exploration.
- Ships with PostgreSQL, Redis, pgAdmin, Prometheus, and Grafana in Docker Compose.
- Includes production-style Loguru logging (colored console, rotated file logs, separate error logs).

### Current progress snapshot
- Milestone 2 scraper flow is functional for LinkedIn list scraping plus detail-page description enrichment.
- Celery supports both single search runs and profile-set runs from JSON config.
- Default search profiles are Australia-first, with Brisbane profiles at highest priority.
- Skills and salary extraction are intentionally deferred to a later milestone.

### Prerequisites
- Docker
- Docker Compose (`docker compose`)

### Quick start

#### 1) Configure environment variables
```bash
cp .env.example .env
```

Set these required values in `.env`:
- `DB_PASSWORD`
- `PGADMIN_DEFAULT_EMAIL`
- `PGADMIN_DEFAULT_PASSWORD`
- `GRAFANA_USER`
- `SCRAPER_ENABLED` (`true` to allow scraper tasks to run)
- `LINKEDIN_EMAIL` (for scraper milestone)
- `LINKEDIN_PASSWORD_FILE` (for scraper milestone, recommended: `secrets/linkedin_password.txt`)

Password flow in this project:
- `postgres` reads `secrets/db_password.txt` via Docker secret `db_password`.
- `backend` reads `DB_PASSWORD_FILE=/run/secrets/db_password` in Compose.
- `DB_PASSWORD` in `.env` is fallback for non-Compose direct runs.
- `backend`, `celery-worker`, and `celery-beat` read `LINKEDIN_PASSWORD_FILE=/run/secrets/linkedin_password` in Compose.

If `DB_PASSWORD` and `secrets/db_password.txt` are different when running locally outside shared-secret mode, DB authentication can fail.

#### 2) Generate local secrets
```bash
bash scripts/generate-secrets.sh
```

Use `bash scripts/generate-secrets.sh --force` to overwrite existing files in `secrets/`.

#### 3) Start the platform
```bash
docker compose up -d --build
```

For faster UI iteration (without waiting on full health dependency chains), you can start only core services for frontend work:

```bash
docker compose up -d frontend backend postgres redis
```

For non-Docker frontend development:

```bash
# from repo root
cd frontend
cat > .env <<'EOF'
VITE_API_TARGET=http://localhost:8000
EOF
```

Then install and run the frontend locally:

```bash
npm install
npm run dev
```

The app runs on Vite's default port (`http://localhost:5173`) unless changed in your local config.

### LLM / Ollama quick test

Make sure the Ollama service is running first (`docker compose up -d ollama`).

```bash
bash backend/scripts/pull-ollama-model.sh
python3 backend/scripts/test_ollama.py
python3 backend/scripts/test_llm_client.py
```

### Service URLs
- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/api/v1/openapi.json`
- Health endpoint: `http://localhost:8000/api/v1/health`
- pgAdmin: `http://localhost:5050`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001` (user from `GRAFANA_USER`, password from `secrets/grafana_password.txt`)

### Jobs API (current)
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs`
- `PATCH /api/v1/jobs/{job_id}`
- `DELETE /api/v1/jobs/{job_id}`

### Scraper Status (Milestone 2)
- Implemented: Base Playwright scraper lifecycle and LinkedIn login/search flow.
- Implemented: LinkedIn list scraping + detail-page enrichment for `description_full`, `description_short`, and `job_type`.
- Implemented: Celery tasks for both single query runs and profile-set runs.
- Implemented: Australia-first profile configuration with Brisbane-priority profiles.
- Current state: skills/job_type/compensation extraction now runs in the processed enrichment layer (`job_enrichments`) while raw `jobs` remains source-of-truth.

### Enrichment Data Model
- `jobs` remains the raw source-of-truth from scraping and ingestion.
- `job_enrichments` stores processed parser output (`skills`, normalized salary fields, job type, confidence metadata).
- Enrichment rows are versioned by `extractor_version` with one row per `(job_id, extractor_version)`.

### Scraper Configuration
- Required env vars: `SCRAPER_ENABLED`, `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD_FILE`.
- Secrets flow: store the LinkedIn password in `secrets/linkedin_password.txt`; Compose mounts it to `/run/secrets/linkedin_password`, and app settings read it through `LINKEDIN_PASSWORD_FILE`.
- Profile config path is currently fixed in code to `backend/src/scrapers/config/linkedin_search_profiles.json`; edit this file to add/disable/reprioritize profiles (`active`, `priority`, `query`, `location`, `limit`).

### How to run scraper
```bash
# 1) Bring up required services
docker compose up -d postgres redis backend celery-worker celery-beat

# 2) Trigger a single LinkedIn scrape task (returns a task id)
docker compose exec celery-worker python -m celery -A src.celery_app.celery_app call src.tasks.scraper_tasks.scrape_linkedin_jobs --kwargs='{"query":"Junior Software Engineer Python Node React","location":"Brisbane, Queensland, Australia","limit":5}'

# 3) Trigger the profile-set task (reads linkedin_search_profiles.json)
docker compose exec celery-worker python -m celery -A src.celery_app.celery_app call src.tasks.scraper_tasks.scrape_linkedin_profile_set

# 4) Fetch task result (replace with returned id)
docker compose exec celery-worker python -m celery -A src.celery_app.celery_app result <TASK_ID>
```

### What to expect
- Task result payload includes counters such as `scraped`, `created`, `updated`, `duplicates`, and `failed` (plus status/platform/query/location context).
- Scraped jobs can be verified via `GET /api/v1/jobs?platform=linkedin`.
- For enriched jobs, `description_full` should contain normalized detail text and `description_short` should contain a truncated summary; some jobs may still have null descriptions if LinkedIn detail markup is unavailable.

### Monitoring
- Scraper metrics are exposed by `celery-worker:9101/metrics` and scraped by Prometheus (`job_name: celery-worker`).
- Grafana dashboard: `Scraper Monitoring` at `http://localhost:3001/d/career-scout-scraper-metrics/scraper-monitoring`.
- Key panels include success rate, jobs scraped/created, failures, run status, run duration (p95/avg), duplicates rate, and jobs-in-db by platform.
- In low-frequency runs, short time windows can look sparse; widen the window (for example, last 24h) before concluding data is missing.

### Troubleshooting quick guide
- LinkedIn auth/challenge: if task logs show challenge/checkpoint/captcha or auth failures, verify credentials/secrets, retry later, and use a low-frequency scrape profile.
- Stale Grafana data: run a new scraper task, then refresh dashboard time range and confirm Prometheus target `celery-worker` is up.
- Playwright runtime/container notes: run scraper tasks from `celery-worker` (it includes the runtime); local host runs without the container image may fail due to missing browser deps.

### Observability
- Prometheus scrapes backend metrics target at `backend:8000/metrics` every 15s.
- Grafana auto-provisions Prometheus datasource and dashboard folder from `monitoring/grafana/`.
- Backend log files are written to `backend/logs/` with retention and rotation.

### Useful commands
```bash
# Restart all services
docker compose restart

# View service status
docker compose ps

# Follow backend logs
docker compose logs -f backend

# Stop and remove containers and network
docker compose down

# Full teardown (also removes named volumes)
docker compose down -v
```
