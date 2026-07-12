# Rate Limits

## API Limits (v1.0)
No rate limiting in open-source version. Add reverse proxy for production.

## Recommended Limits
| Endpoint | Limit | Window |
|----------|-------|--------|
| Search | 100 | 1 minute |
| Create | 60 | 1 minute |
| Compose | 30 | 1 minute |

## Implementation (Future)
Add `slowapi` or `fastapi-limiter` with Redis backend.
