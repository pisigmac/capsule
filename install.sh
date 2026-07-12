#!/bin/bash
set -e

echo "🚀 Welcome to Capsule Installer!"
echo "====================================="

echo "📦 1. Setting up environment..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "   Created .env from .env.example"
    else
        echo "   No .env.example found, creating default .env"
        echo "CAPSULE_API_PORT=9000" > .env
    fi
else
    echo "   .env already exists, skipping."
fi

echo "🔧 2. Making scripts executable..."
chmod +x scripts/*.sh

echo "🐳 3. Building and starting Docker containers..."
./scripts/stop_all.sh || true
./scripts/start_all.sh

echo "====================================="
echo "✅ Capsule installation complete!"
echo ""
echo "🌐 Frontend Dashboard : http://localhost:5173"
echo "🔌 API Gateway        : http://localhost:9000/api/v1"
echo "📚 API Documentation  : http://localhost:9000/docs"
echo ""
echo "To interact via CLI, run:"
echo "  docker exec -it capsule-cli /bin/sh"
echo "  capsule --help"
