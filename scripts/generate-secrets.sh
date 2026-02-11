#!/bin/bash

set -euo pipefail

FORCE=false
if [ "${1:-}" = "--force" ]; then
  FORCE=true
elif [ "${1:-}" != "" ]; then
  echo "Usage: $0 [--force]"
  exit 1
fi

mkdir -p secrets

TARGET_FILES="secrets/db_password.txt secrets/grafana_password.txt secrets/linkedin_password.txt"

if [ "$FORCE" = false ]; then
  EXISTING_FILES=""
  for file in $TARGET_FILES; do
    if [ -e "$file" ]; then
      EXISTING_FILES="$EXISTING_FILES $file"
    fi
  done

  if [ -n "$EXISTING_FILES" ]; then
    echo "Refusing to overwrite existing secret file(s):$EXISTING_FILES"
    echo "Re-run with --force to overwrite all target secret files."
    exit 1
  fi
fi

# Database password
openssl rand -base64 32 | tr -d '\n' > secrets/db_password.txt

# Grafana password
openssl rand -base64 32 | tr -d '\n' > secrets/grafana_password.txt

# LinkedIn password placeholder secret
openssl rand -base64 32 | tr -d '\n' > secrets/linkedin_password.txt

chmod 600 secrets/*.txt

echo "Secrets generated in secrets/"
echo "Do not commit these files."
