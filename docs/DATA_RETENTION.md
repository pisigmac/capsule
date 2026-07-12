# Data Retention

## Policy
- Active capsules: Retained indefinitely
- Archived capsules: Retained indefinitely (user-managed)
- Deleted capsules: Hard delete immediately
- Sync logs: 30 days
- Analytics events: 90 days

## Compliance
- GDPR: Right to erasure (delete capsule)
- Export: Full workspace export available
- Backup: Daily automated backups

## Cleanup
```bash
# Archive stale capsules
capsule stale --days=90
# Manual review and archive
```

## Storage Limits
| Tier | Limit |
|------|-------|
| Free | Local only |
| Pro | 5GB |
| Team | 50GB |
| Enterprise | Unlimited |
