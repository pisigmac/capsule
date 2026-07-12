#!/bin/bash
# stop_all.sh - Utility to stop all Capsule services

# Ensure we are in the directory containing docker-compose.yml if possible
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "Stopping Capsule services..."
docker-compose down

echo "Validating services are stopped..."
running_containers=$(docker-compose ps -q)
if [ -n "$running_containers" ]; then
    echo "Error: Some containers are still running:"
    docker-compose ps
    exit 1
fi

echo "Services stopped and validated successfully."
