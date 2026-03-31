# Career Scout Platform

An AI-powered job discovery and tracking platform. Career Scout scrapes job listings, enriches them with structured data, scores them against your profile using a local LLM, and presents everything through a modern web UI.

## What it does

- **Scrapes** job listings from LinkedIn via Playwright-based automation
- **Enriches** raw listings — extracts skills, job type, and salary ranges
- **Scores** jobs against your profile using a local LLM (Ollama) for relevance ranking
- **Profile ingestion** — upload your CV (PDF/DOCX) and the LLM parses it into a structured profile
- **Frontend** — React dashboard for browsing, filtering, and reviewing scored jobs
- **Observability** — Prometheus metrics + Grafana dashboards out of the box

## Architecture

```text
frontend (React + Vite)
    │
    ▼
backend (FastAPI + Celery)
    ├── PostgreSQL  — jobs, profiles, enrichments, match scores
    ├── Redis       — Celery broker + result backend
    └── Ollama      — local LLM for scoring and CV parsing
```

## Quick start

### 1. Prerequisites

- Docker
- Docker Compose v2 (`docker compose`)

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Required | Description |
| --- | --- | --- |
| `DB_PASSWORD` | yes | PostgreSQL password |
| `PGADMIN_DEFAULT_EMAIL` | yes | pgAdmin login email |
| `PGADMIN_DEFAULT_PASSWORD` | yes | pgAdmin login password |
| `GRAFANA_USER` | yes | Grafana admin username |
| `OLLAMA_MODEL` | no | LLM model name (default: `llama3.2:3b`) |
| `SCRAPER_ENABLED` | no | Set `true` to allow scraper tasks |
| `LINKEDIN_EMAIL` | no | LinkedIn account for scraping |

### 3. Generate secrets

```bash
bash scripts/generate-secrets.sh
```

This creates `secrets/db_password.txt`, `secrets/grafana_password.txt`, and `secrets/linkedin_password.txt`. Run with `--force` to regenerate.

### 4. Pull the LLM model

```bash
docker compose up -d ollama
docker exec career-scout-ollama ollama pull qwen3.5:latest
```

Or use any model available on [ollama.com/library](https://ollama.com/library) — update `OLLAMA_MODEL` in `.env` to match.

### 5. Start the platform

```bash
docker compose up -d --build
```

Alembic migrations run automatically on backend startup.

## Service URLs

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| Backend API | <http://localhost:8000> |
| Swagger UI | <http://localhost:8000/docs> |
| Health check | <http://localhost:8000/api/v1/health> |
| pgAdmin | <http://localhost:5050> |
| Prometheus | <http://localhost:9090> |
| Grafana | <http://localhost:3001> |

## Common commands

```bash
# Start everything
docker compose up -d

# Start only core services (skip monitoring)
docker compose up -d postgres redis ollama backend frontend celery-worker celery-beat

# View logs
docker compose logs -f backend
docker compose logs -f celery-worker

# Stop containers (keep volumes)
docker compose down

# Full teardown including volumes
docker compose down -v

# Restart a single service
docker compose restart backend
```

## Secrets

Passwords are passed via Docker secrets (files), not plain env vars:

- `secrets/db_password.txt` — mounted as `/run/secrets/db_password` in backend/postgres
- `secrets/linkedin_password.txt` — mounted as `/run/secrets/linkedin_password` in backend/celery
- `secrets/grafana_password.txt` — mounted as `/run/secrets/grafana_password` in grafana

`DB_PASSWORD` in `.env` is a fallback for running the backend directly outside Docker.

## Scraper

See [backend/README.md](backend/README.md) for scraper configuration and usage.

## Monitoring

- Prometheus scrapes backend at `backend:8000/metrics` every 15s
- Grafana auto-provisions datasource and dashboards from `monitoring/grafana/`
- Scraper dashboard: **Scraper Monitoring** at `http://localhost:3001`
