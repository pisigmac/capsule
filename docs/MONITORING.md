# Monitoring

## Health Checks
- `GET /health` — API liveness
- `GET /health/ready` — Readiness (DB connected)
- `GET /health/db` — Database connectivity

## Metrics
- Prometheus endpoint (future)
- Custom metrics: capsules_created, search_latency, sync_errors

## Alerts
| Condition | Severity | Action |
|-----------|----------|--------|
| API down > 1 min | Critical | Page on-call |
| DB errors > 10/min | High | Slack alert |
| Disk > 90% | High | Email alert |
| Sync lag > 5 min | Medium | Log warning |

## Logging
Structured JSON logs. Level: INFO in production, DEBUG in dev.
