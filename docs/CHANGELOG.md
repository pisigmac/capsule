# Changelog

All notable changes to Capsule will be documented in this file.

## [1.0.0] - 2026-07-11

### Added
- Initial release
- `.capsule.md` file format with YAML frontmatter
- Full-text search using SQLite FTS5
- Context composition for AI sessions
- Knowledge graph with typed relationships
- File system sync with Watchdog
- Freshness decay detection
- Rich CLI with Click
- FastAPI REST API
- Docker Compose orchestration
- Comprehensive test suite (30+ tests)
- 30 deliverable documents

### Features
- `capsule init` — Initialize workspace
- `capsule new` — Create capsule (interactive or $EDITOR)
- `capsule search` — Full-text search with filters
- `capsule show` — Display capsule details
- `capsule link` — Link capsules
- `capsule compose` — Build context windows
- `capsule stale` — Detect decaying knowledge
- `capsule sync` — Sync directories
- `capsule archive` — Archive capsules
- `capsule status` — System overview

### API Endpoints
- `POST /api/v1/capsules` — Create capsule
- `GET /api/v1/capsules` — List capsules
- `GET /api/v1/capsules/{id}` — Get capsule
- `PATCH /api/v1/capsules/{id}` — Update capsule
- `DELETE /api/v1/capsules/{id}` — Delete capsule
- `POST /api/v1/capsules/{id}/archive` — Archive capsule
- `POST /api/v1/search` — Search capsules
- `POST /api/v1/compose` — Compose context
- `POST /api/v1/relationships` — Create relationship
- `GET /api/v1/capsules/{id}/relationships` — Get relationships
- `GET /api/v1/tags` — List tags
- `POST /api/v1/sync` — Sync directory
- `GET /api/v1/stale` — Get stale capsules

### Architecture
- Service-oriented design with 5 services
- SQLite with WAL mode
- FTS5 full-text search
- SQLAlchemy ORM
- Pydantic validation
- Docker Compose orchestration

### Documentation
- README.md
- FEATURES.md
- AGENTS.md
- API.md
- OPENAPI.yaml
- MARKETING.md
- SOCIAL.md
- CODEMAP.md
- FUTURE.md
- TESTS.md
- ARCHITECTURE.md
- TECH-STACK.md
- ENV.md
- DEPLOY.md
- DB_SCHEMA.md
- PRICING.md
- ANALYTICS.md
- ERRORS.md
- CHANGELOG.md
- SECURITY.md
- PAYMENTS.md
- RATE_LIMITS.md
- PERF_BUDGET.md
- EVENTS.md
- FEATURE_FLAGS.md
- EMAIL.md
- MONITORING.md
- STAGING.md
- EMPTY_STATES.md
- DATA_RETENTION.md

## [Unreleased]

### Planned
- Web UI for browsing capsules
- Git integration
- Import from Notion, Obsidian, Logseq
- Team sharing
- MCP server
- VS Code extension
- PostgreSQL backend
- Redis caching
- OpenTelemetry tracing
