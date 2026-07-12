# Tech Stack

## Core Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Language | Python | 3.10+ | Application logic |
| Web Framework | FastAPI | 0.110+ | REST API |
| Server | Uvicorn | 0.27+ | ASGI server |
| ORM | SQLAlchemy | 2.0+ | Database abstraction |
| Database | SQLite | 3.35+ | Local storage |
| FTS | SQLite FTS5 | built-in | Full-text search |
| CLI Framework | Click | 8.1+ | Terminal interface |
| CLI UI | Rich | 13.0+ | Terminal formatting |
| File Watch | Watchdog | 3.0+ | File system monitoring |
| YAML | PyYAML | 6.0+ | Frontmatter parsing |
| Validation | Pydantic | 2.0+ | Request validation |
| HTTP Client | HTTPX | 0.26+ | API client (tests) |

## Dev Tools

| Tool | Purpose |
|------|---------|
| pytest | Testing framework |
| pytest-cov | Coverage reporting |
| black | Code formatting |
| ruff | Linting |
| mypy | Type checking |
| pre-commit | Git hooks |

## Infrastructure

| Tool | Purpose |
|------|---------|
| Docker | Containerization |
| Docker Compose | Multi-service orchestration |
| GitHub Actions | CI/CD (future) |

## Why These Choices?

### Python
- Universal in AI/ML ecosystem
- Excellent library support
- Fast development velocity
- Easy to extend

### SQLite
- Zero configuration
- Single file database
- WAL mode for concurrent reads
- FTS5 built-in
- Easy to migrate to PostgreSQL later

### FastAPI
- Automatic OpenAPI generation
- Pydantic integration
- Async support (future)
- Great performance

### SQLAlchemy
- Database agnostic
- Migration support (Alembic-ready)
- Complex query support
- Connection pooling

### Click + Rich
- Click: Industry standard for CLI
- Rich: Beautiful terminal output
- Combined: Best-in-class CLI experience

## Alternative Considerations

| Alternative | Why Not Chosen |
|-------------|---------------|
| PostgreSQL | Overkill for local-first tool |
| Django | Too heavy for API-only service |
| Flask | Less async support, no auto-docs |
| Typer | Less mature than Click |
| Elasticsearch | Overkill for <100k capsules |
| MongoDB | No FTS5 equivalent, more complexity |

## Migration Path

### SQLite → PostgreSQL
1. Add PostgreSQL driver (`psycopg2`)
2. Update connection string
3. Run migrations
4. No code changes needed (SQLAlchemy abstraction)

### FastAPI → gRPC
1. Add protobuf definitions
2. Implement gRPC services
3. Keep FastAPI as gateway
4. Gradual migration

### Single Process → Microservices
1. Extract services to separate containers
2. Add message queue (Redis/RabbitMQ)
3. Update Docker Compose
4. Add service discovery
