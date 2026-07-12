# Analytics

## Metrics Overview

Capsule tracks usage metrics to improve the product and provide insights.

## Tracked Events

### User Actions

| Event | Description | Properties |
|-------|-------------|------------|
| `capsule_created` | New capsule created | topic_length, tag_count, confidence |
| `capsule_updated` | Capsule modified | fields_changed |
| `capsule_deleted` | Capsule removed | — |
| `capsule_archived` | Capsule archived | days_old |
| `search_performed` | Search executed | query_length, result_count, filters_used |
| `context_composed` | Context window built | capsule_count, token_estimate, tags_used |
| `relationship_created` | Capsule linked | relationship_type |
| `sync_triggered` | Directory synced | file_count, capsule_count |
| `stale_checked` | Stale capsules viewed | stale_count, days_threshold |

### System Metrics

| Metric | Description | Collection |
|--------|-------------|------------|
| `api_latency` | API response time | Per endpoint, p50/p95/p99 |
| `search_latency` | FTS5 query time | Per query |
| `db_size` | Database file size | Daily |
| `capsule_count` | Total capsules | Daily |
| `tag_count` | Total tags | Daily |
| `relationship_count` | Total relationships | Daily |
| `active_users` | Daily active users | Daily (cloud only) |

## Analytics Architecture

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  Client │────▶│  Event Bus  │────▶│  Analytics  │
│  (CLI)  │     │  (SQLite)   │     │  Engine     │
└─────────┘     └─────────────┘     └──────┬──────┘
                                            │
                                     ┌──────▼──────┐
                                     │  Dashboard  │
                                     │  (Future)   │
                                     └─────────────┘
```

## Privacy

### Local Mode
- No data leaves your machine
- Analytics stored in local SQLite
- Opt-out available

### Cloud Mode
- Anonymous usage statistics
- No capsule content transmitted
- Only metadata (topic length, tag count, etc.)
- GDPR compliant

## Reports

### Weekly Report (Email)
- Capsules created this week
- Search queries performed
- Context compositions
- Stale capsules detected
- Knowledge health score

### Monthly Report
- Total capsules growth
- Most active tags
- Top search queries
- Team collaboration metrics (Team tier)
- Storage usage

## Dashboard (Future)

Web-based analytics dashboard:
- Real-time capsule creation
- Search trend graph
- Knowledge decay visualization
- Tag cloud
- Relationship network graph
- Team activity heatmap

## Implementation

```python
# services/shared/analytics.py (future)
class Analytics:
    def track(self, event: str, properties: dict):
        """Track an analytics event."""
        pass

    def report(self, period: str) -> dict:
        """Generate analytics report."""
        pass
```
