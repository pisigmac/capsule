#!/bin/bash
set -euo pipefail

echo "Capsule installer"
echo "================="

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  fi
fi

chmod +x scripts/*.sh
./scripts/start_all.sh
