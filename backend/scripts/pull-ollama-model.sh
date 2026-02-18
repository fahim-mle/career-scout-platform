#!/usr/bin/env bash

set -euo pipefail

CONTAINER_NAME="career-scout-ollama"
MODEL="${1:-${OLLAMA_MODEL:-llama3.2:3b}}"

echo "[ollama] Pulling model: ${MODEL}"
echo "[ollama] Using container: ${CONTAINER_NAME}"

if ! docker ps --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  echo "[ollama] Error: container ${CONTAINER_NAME} is not running."
  echo "[ollama] Start it first: docker compose up -d ollama"
  exit 1
fi

if docker exec -i "${CONTAINER_NAME}" ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "${MODEL}"; then
  echo "[ollama] Model already installed: ${MODEL}"
  echo "[ollama] Skipping pull."
  exit 0
fi

echo "[ollama] Model not found. Pulling: ${MODEL}"
docker exec -i "${CONTAINER_NAME}" ollama pull "${MODEL}"

echo "[ollama] Pull complete. Installed models:"
docker exec -i "${CONTAINER_NAME}" ollama list

echo "[ollama] Done."
