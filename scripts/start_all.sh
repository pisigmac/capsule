#!/bin/bash
# start_all.sh - Utility to start all Capsule services

# Ensure we are in the directory containing docker-compose.yml if possible,
# or assume the script is run from the project root.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "Starting Capsule services..."
docker-compose up -d --build

echo "Validating services are up..."
for service in api sync cli frontend; do
    container_id=$(docker-compose ps -q $service)
    if [ -z "$container_id" ]; then
        echo "Error: Service $service failed to start (container not found)."
        exit 1
    fi
    status=$(docker inspect -f '{{.State.Status}}' "$container_id")
    if [ "$status" != "running" ]; then
        echo "Error: Service $service is not running (status: $status)."
        exit 1
    fi
    echo "Service $service is running."
done

echo "Checking API health..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    api_container_id=$(docker-compose ps -q api)
    api_health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$api_container_id")
    
    if [ "$api_health" == "healthy" ]; then
        echo "API service is healthy!"
        break
    elif [ "$api_health" == "unhealthy" ]; then
        echo "Error: API service became unhealthy."
        exit 1
    fi
    
    echo "Waiting for API to be healthy (current status: $api_health)..."
    sleep 2
    RETRY_COUNT=$((RETRY_COUNT+1))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Error: Timeout waiting for API service to be healthy."
    exit 1
fi

echo ""
echo "All services started and validated successfully:"
docker-compose ps
