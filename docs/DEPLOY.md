# Deployment Guide

## Local Development

```bash
# Clone repository
git clone https://github.com/capsule-dev/capsule.git
cd capsule

# Setup
./scripts/setup.sh
source .venv/bin/activate

# Initialize
capsule init

# Run API
uvicorn services.api.main:app --reload

# Run CLI (another terminal)
capsule status
```

## Docker (Recommended)

```bash
# Build and run
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api

# Stop
docker-compose down

# Reset data
docker-compose down -v
```

## Docker Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| API | capsule-api | 9000 | REST API |
| Sync | capsule-sync | — | File watcher |
| CLI | capsule-cli | — | Interactive shell |

## Production Deployment

### Single Server

```bash
# 1. Clone
git clone https://github.com/capsule-dev/capsule.git /opt/capsule
cd /opt/capsule

# 2. Environment
cp .env.example .env
# Edit .env with production values

# 3. Docker Compose
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 4. Reverse proxy (nginx)
# See nginx.conf.example

# 5. SSL (Let's Encrypt)
certbot --nginx -d capsule.yourdomain.com
```

### Kubernetes (Future)

```yaml
# capsule-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: capsule-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: capsule-api
  template:
    metadata:
      labels:
        app: capsule-api
    spec:
      containers:
      - name: api
        image: capsule-dev/capsule:latest
        ports:
        - containerPort: 9000
        env:
        - name: CAPSULE_DATABASE_URL
          value: "postgresql://..."
```

### Cloud Platforms

#### AWS
- ECS Fargate for API
- RDS PostgreSQL for database
- EFS for capsule files
- Application Load Balancer

#### GCP
- Cloud Run for API
- Cloud SQL for PostgreSQL
- Cloud Storage for capsule files
- Cloud Load Balancing

#### Azure
- Container Instances for API
- Azure Database for PostgreSQL
- Azure Files for capsule storage
- Application Gateway

## Migration

### SQLite to PostgreSQL

```bash
# 1. Export SQLite
sqlite3 capsule.db ".dump" > dump.sql

# 2. Convert syntax (if needed)
# 3. Import to PostgreSQL
psql -h localhost -U capsule -d capsule < dump.sql

# 4. Update connection string
export CAPSULE_DATABASE_URL="postgresql://user:pass@localhost/capsule"
```

## Health Checks

```bash
# API health
curl http://localhost:9000/health

# Database connectivity
capsule status

# Sync service
docker-compose logs sync | grep "Sync running"
```

## Backup Strategy

### SQLite
```bash
# Automated backup cron
0 2 * * * cp /data/capsule.db /backups/capsule-$(date +%Y%m%d).db
```

### PostgreSQL
```bash
# pg_dump
pg_dump -h localhost -U capsule capsule > backup.sql
```

## Monitoring

- API: `/health` endpoint
- Database: Connection pool metrics
- Sync: File watcher status
- Disk: Capsule storage growth

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| API won't start | Port conflict | Change `API_PORT` |
| Sync not detecting files | Wrong path | Check `CAPSULES_DIR` |
| Search returns nothing | FTS5 not initialized | Run `capsule init` |
| Database locked | Concurrent writes | Enable WAL mode |
