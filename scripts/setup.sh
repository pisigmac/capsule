#!/bin/bash
set -e

echo "Setting up Capsule development environment..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Created virtual environment"
fi

source .venv/bin/activate
pip install -e ".[dev]"
mkdir -p capsules capsules/shared capsules/archived
python -c "from services.shared.models import init_db, reset_engine; reset_engine(); init_db()"
echo "Setup complete. Run: source .venv/bin/activate && capsule init"
