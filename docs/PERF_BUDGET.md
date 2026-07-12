# Performance Budget

## Targets
| Metric | Target | Max |
|--------|--------|-----|
| API response (p95) | <100ms | 200ms |
| Search query (p95) | <50ms | 100ms |
| Context compose | <200ms | 500ms |
| Sync initial scan | <5s per 1000 files | 10s |
| CLI startup | <500ms | 1s |

## Database
- SQLite WAL mode enabled
- Connection pooling: 5 connections
- Query timeout: 5 seconds

## Memory
- Max RSS: 256MB per service
- Capsule cache: 1000 items
