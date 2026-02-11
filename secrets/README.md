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

The script creates secure random values for all documented secret files and applies restricted file permissions.

By default, it will not overwrite existing secret files. If any target file already exists, the script exits with a helpful message.

To overwrite all target secret files:

```bash
bash scripts/generate-secrets.sh --force
```

## Security Notes

- Never commit secret `.txt` files to git.
- Keep `.env` out of version control.
- Rotate credentials if exposed.
