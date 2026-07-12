# Events

## Event System (Future)
Async event bus for cross-service communication.

## Event Types
| Event | Producer | Consumers |
|-------|----------|-----------|
| `capsule.created` | API | Search, Analytics, Sync |
| `capsule.updated` | API | Search, Analytics |
| `capsule.deleted` | API | Search, Analytics |
| `capsule.archived` | API | Analytics |
| `sync.completed` | Sync | Analytics |
| `search.performed` | Search | Analytics |

## Implementation
SQLite triggers for local events. Redis pub/sub for distributed.
