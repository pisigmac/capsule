# Environment Configuration

## Configuration Sources

Capsule reads configuration in this priority order:
1. Environment variables (highest priority)
2. `.env` file
3. Default values (lowest priority)

## Required Variables

None. Capsule works out of the box with defaults.

## Optional Variables

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `CAPSULE_DATABASE_URL` | `sqlite:///capsule.db` | Database connection string |

### Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `CAPSULES_DIR` | `./capsules` | Main capsules directory |
| `CAPSULES_SHARED_DIR` | `./capsules/shared` | Cross-project shared capsules |
| `CAPSULES_ARCHIVED_DIR` | `./capsules/archived` | Archived capsules |

### API

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `0.0.0.0` | API server host |
| `API_PORT` | `9000` | API server port |
| `CAPSULE_API_URL` | `http://localhost:9000/api/v1` | API base URL for CLI |

### Search

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_LIMIT` | `50` | Default search result limit |

### Sync

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_INTERVAL` | `30` | File watcher polling interval (seconds) |
| `AUTO_ARCHIVE_DAYS` | `90` | Days before knowledge is considered stale |

### Development

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Example .env

```bash
# Production
CAPSULE_DATABASE_URL=sqlite:////data/capsule.db
CAPSULES_DIR=/data/capsules
API_HOST=0.0.0.0
API_PORT=9000

# Development
DEBUG=true
LOG_LEVEL=DEBUG
```

## Docker Environment

When running in Docker, use a `.env` file or pass variables via `docker-compose.yml`:

```yaml
environment:
  - CAPSULE_DATABASE_URL=sqlite:///data/capsule.db
  - CAPSULES_DIR=/data/capsules
```

## Security Notes

- Never commit `.env` files to version control
- Use `.env.example` as a template
- For production, use secrets management (Vault, AWS Secrets Manager)
- Database URL should not contain credentials in plain text
