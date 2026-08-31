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

echo "Stopping Capsule..."
compose down

if [ -n "$(compose ps -q 2>/dev/null || true)" ]; then
  echo "Error: containers are still running."
  compose ps
  exit 1
fi

echo "Services stopped."
