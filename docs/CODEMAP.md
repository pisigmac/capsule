# Code Map

## Directory Structure

```
capsule/
├── services/
│   ├── api/              # FastAPI REST API
│   │   ├── main.py       # App factory & startup
│   │   ├── routes.py     # All API endpoints
│   │   └── dependencies.py # DI container (future)
│   ├── parser/           # .capsule.md parser
│   │   └── parser.py     # CapsuleParser + ParsedCapsule
│   ├── search/           # Full-text search
│   │   └── engine.py     # SearchEngine (FTS5)
│   ├── sync/             # File system watcher
│   │   └── watcher.py    # CapsuleSyncService + EventHandler
│   └── shared/           # Shared infrastructure
│       ├── models.py     # SQLAlchemy models + DB setup
│       ├── config.py     # Configuration management
│       └── database.py   # (merged into models.py)
├── cli/
│   └── main.py           # Click CLI with Rich output
├── tests/
│   ├── conftest.py       # Pytest fixtures
│   ├── test_parser.py    # Parser unit tests
│   ├── test_api.py       # API integration tests
│   ├── test_search.py    # Search engine tests
│   ├── test_sync.py      # Sync service tests
│   └── test_e2e.py       # End-to-end workflow tests
├── docs/                 # 30 deliverable documents
├── scripts/
│   └── setup.sh          # Development setup script
├── pyproject.toml        # Project metadata & dependencies
├── docker-compose.yml    # Multi-service orchestration
├── Dockerfile            # Container image
└── .env.example          # Configuration template
```

## Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `services/shared/models.py` | Database schema, ORM, FTS5 setup | ~200 |
| `services/parser/parser.py` | Markdown/YAML parsing, validation | ~150 |
| `services/search/engine.py` | FTS5 queries, context composition | ~120 |
| `services/sync/watcher.py` | File watcher, auto-sync | ~150 |
| `services/api/routes.py` | REST API endpoints | ~300 |
| `cli/main.py` | Terminal interface | ~250 |

## Data Flow

```
.capsule.md file
    │
    ▼
[Parser] ──▶ ParsedCapsule
    │
    ▼
[Sync Service] ──▶ [Database]
    │                    │
    ▼                    ▼
[CLI] ◀────────── [Search Engine]
    │                    │
    ▼                    ▼
[API Gateway] ◀──── [FTS5 Index]
```

## Service Boundaries

### Parser Service
- Input: Raw markdown text or file path
- Output: ParsedCapsule dataclass
- No external dependencies
- Pure function (idempotent)

### Capsule Service (in routes.py)
- Input: HTTP requests
- Output: JSON responses
- Depends on: Database, Parser
- Handles: CRUD, validation, tag management

### Search Service
- Input: Query string + filters
- Output: Ranked capsule list or composed context
- Depends on: Database (FTS5)
- Stateless

### Sync Service
- Input: File system events
- Output: Database mutations
- Depends on: Database, Parser
- Stateful (running watcher)

## Extension Points

1. **New relationship types** — Add to `CapsuleRelationship.relationship_type`
2. **New search backends** — Implement `SearchEngine` interface
3. **New CLI commands** — Add Click commands to `cli/main.py`
4. **New API versions** — Add routers with `/api/v2` prefix
5. **New storage backends** — Extend `models.py` for PostgreSQL, MySQL
