# Secrets Directory

This directory stores local development secrets.

## Files

- `db_password.txt`: PostgreSQL password
- `grafana_password.txt`: Grafana admin password
- `linkedin_password.txt`: LinkedIn password (optional, for scraper milestones)

## Generate Secrets

Run:

```bash
bash scripts/generate-secrets.sh
```

The script creates secure random passwords and applies restricted file permissions.

## Security Notes

- Never commit secret `.txt` files to git.
- Keep `.env` out of version control.
- Rotate credentials if exposed.
