## Career Scout Platform

Career Scout is a job-tracking backend platform for collecting and managing job listings, with built-in observability for local development.

### What it does (current status)
- Provides a FastAPI backend with request-level logging and standardized error responses.
- Exposes Jobs CRUD APIs (`/api/v1/jobs`) with business rules (immutability, soft delete, validation).
- Includes health checks at `/api/v1/health`.
- Provides OpenAPI/Swagger docs for API exploration.
- Ships with PostgreSQL, Redis, pgAdmin, Prometheus, and Grafana in Docker Compose.
- Includes production-style Loguru logging (colored console, rotated file logs, separate error logs).

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

Password flow in this project:
- `postgres` reads `secrets/db_password.txt` via Docker secret `db_password`.
- `backend` reads `DB_PASSWORD_FILE=/run/secrets/db_password` in Compose.
- `DB_PASSWORD` in `.env` is fallback for non-Compose direct runs.

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

### Service URLs
- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/api/v1/openapi.json`
- Health endpoint: `http://localhost:8000/api/v1/health`
- pgAdmin: `http://localhost:5050`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001` (default login `admin/admin`)

### Jobs API (current)
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs`
- `PATCH /api/v1/jobs/{job_id}`
- `DELETE /api/v1/jobs/{job_id}`

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
