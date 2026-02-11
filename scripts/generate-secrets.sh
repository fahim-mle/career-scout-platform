#!/bin/bash

set -euo pipefail

mkdir -p secrets

# Database password
openssl rand -base64 32 > secrets/db_password.txt

# Grafana password
openssl rand -base64 32 > secrets/grafana_password.txt

chmod 600 secrets/*.txt

echo "Secrets generated in secrets/"
echo "Do not commit these files."
