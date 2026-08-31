#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

echo "Starting Capsule..."
compose up -d --build

echo "Waiting for API health..."
for _ in $(seq 1 60); do
  if curl -fsS --noproxy '*' "http://127.0.0.1:9100/health" >/dev/null 2>&1; then
    echo "API is healthy."
    compose ps
    echo ""
    echo "Web UI:  http://localhost:8080"
    echo "API:     http://localhost:9100/api/v1"
    echo "Docs:    http://localhost:9100/docs"
    exit 0
  fi
  sleep 2
done

echo "Error: API did not become healthy."
compose logs --tail=80 api postgres sync
exit 1
