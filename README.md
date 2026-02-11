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

#### 2) Generate local secrets
```bash
bash scripts/generate-secrets.sh
```

Use `bash scripts/generate-secrets.sh --force` to overwrite existing files in `secrets/`.

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
