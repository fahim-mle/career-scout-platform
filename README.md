## Career Scout Platform

### Setup

#### Prerequisites
- Docker
- Docker Compose (`docker compose`)

#### 1) Configure environment variables
```bash
cp .env.example .env
```

Set these required values in `.env`:
- `DB_PASSWORD`
- `PGADMIN_DEFAULT_EMAIL`
- `PGADMIN_DEFAULT_PASSWORD`

Password source in this project:
- `postgres` reads `secrets/db_password.txt` via Docker secret `db_password`.
- `backend` (in Docker Compose) reads `DB_PASSWORD_FILE=/run/secrets/db_password` from that same secret.
- `DB_PASSWORD` in `.env` is a fallback for non-Compose/local direct runs.

If `DB_PASSWORD` and `secrets/db_password.txt` differ when not using shared-secret mode, database authentication can fail.

#### 2) Generate local secrets
```bash
bash scripts/generate-secrets.sh
```

Use `bash scripts/generate-secrets.sh --force` to overwrite existing files in `secrets/`.
If you set `DB_PASSWORD` manually for non-Compose runs, keep it aligned with `secrets/db_password.txt`.

#### 3) Start the stack
```bash
docker compose up -d --build
```

### Verify services
- Backend health: `http://localhost:8000/api/v1/health/`
- pgAdmin: `http://localhost:5050`
- Postgres port: `localhost:5432`
- Redis port: `localhost:6379`

### Useful commands
```bash
# Restart all services
docker compose restart

# Stop and remove containers and network
docker compose down

# Full teardown (also removes named volumes)
docker compose down -v
```
