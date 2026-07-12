# Staging Environment

## Setup
```bash
cp .env.example .env.staging
# Edit: API_PORT=8001, DEBUG=true
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up
```

## Differences from Production
- SQLite in-memory or staging.db
- Debug mode enabled
- No rate limits
- Verbose logging

## Deployment
Auto-deploy on PR merge to `staging` branch.
