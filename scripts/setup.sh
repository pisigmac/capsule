#!/bin/bash
set -e

echo "Setting up Capsule development environment..."

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Created virtual environment"
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
echo "Installed dependencies"

# Create directories
mkdir -p capsules capsules/shared capsules/archived
echo "Created capsule directories"

# Initialize database
python -c "from services.shared.models import init_db; init_db()"
echo "Initialized database"

echo ""
echo "Setup complete. Run:"
echo "  source .venv/bin/activate"
echo "  capsule init"
echo "  capsule --help"
