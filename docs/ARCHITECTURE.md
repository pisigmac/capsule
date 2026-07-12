# Architecture

## Overview

Capsule uses a **service-oriented architecture** with clean boundaries. While currently running as a single process for local use, each service is designed to be extractable into a standalone microservice.

## Design Principles

1. **Single Responsibility** — Each service does one thing
2. **Dependency Inversion** — Services depend on interfaces, not implementations
3. **Database Per Service** — Each service could have its own DB (currently shared SQLite)
4. **Event-Driven** — Async operations via events (future)
5. **API-First** — All operations exposed via REST API

## Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │   CLI   │  │  Web UI │  │  Agent  │  │  Editor │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
└───────┼────────────┼────────────┼────────────┼─────────────┘
        │            │            │            │
        └────────────┴─────┬──────┴────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                   API Gateway (FastAPI)                      │
│              Port: 9000 | REST + OpenAPI                     │
└──────────────────────────┼──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌────────▼────────┐  ┌────▼─────┐
│   Capsule    │  │     Search      │  │   Sync   │
│   Service    │  │    Service      │  │ Service  │
│  (CRUD)      │  │   (FTS5)        │  │(Watchdog)│
└───────┬──────┘  └────────┬────────┘  └────┬─────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
              ┌────────────▼────────────┐
              │      SQLite (WAL)         │
              │   Shared Database         │
              │   (Extensible to PG)      │
              └───────────────────────────┘
```

## Service Details

### API Gateway
- **Technology:** FastAPI
- **Responsibility:** Routing, validation, serialization
- **State:** Stateless
- **Scalability:** Horizontal (multiple instances behind load balancer)

### Capsule Service
- **Technology:** Python + SQLAlchemy
- **Responsibility:** CRUD operations, tag management, validation
- **State:** Stateless (DB holds state)
- **Scalability:** Horizontal with shared DB

### Parser Service
- **Technology:** Python + PyYAML + regex
- **Responsibility:** Parse .capsule.md files
- **State:** Stateless (pure functions)
- **Scalability:** Embarrassingly parallel

### Search Service
- **Technology:** SQLite FTS5
- **Responsibility:** Full-text search, context composition
- **State:** Stateless (FTS5 index in DB)
- **Scalability:** Read replicas (with PostgreSQL)

### Sync Service
- **Technology:** Python + Watchdog
- **Responsibility:** File system monitoring, auto-import
- **State:** Stateful (running watcher, file hashes)
- **Scalability:** One instance per workspace

## Data Flow

### Create Capsule (CLI)
```
CLI → Parser → Capsule Service → Database → FTS5 Index
```

### Search Capsules
```
CLI/API → Search Service → FTS5 Query → Database → Results
```

### Sync Directory
```
File System → Watchdog → Parser → Capsule Service → Database
```

### Compose Context
```
CLI/API → Search Service → Filter → Token Budget → Context String
```

## Database Design

### Schema

```sql
-- Capsules table
capsules (
    id UUID PRIMARY KEY,
    topic VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    freshness DATETIME NOT NULL,
    source VARCHAR(500),
    confidence VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    file_path VARCHAR(1000)
);

-- Tags table
tags (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    created_at DATETIME NOT NULL
);

-- Many-to-many junction
capsule_tags (
    capsule_id UUID REFERENCES capsules(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (capsule_id, tag_id)
);

-- Relationships
capsule_relationships (
    id UUID PRIMARY KEY,
    from_capsule_id UUID REFERENCES capsules(id) ON DELETE CASCADE,
    to_capsule_id UUID REFERENCES capsules(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL,
    created_at DATETIME NOT NULL
);

-- FTS5 virtual table
capsule_search USING fts5(topic, content, content='capsules', content_rowid='id');
```

### Indexes

- `ix_capsules_topic` — Topic search
- `ix_capsules_freshness` — Stale detection
- `ix_capsules_confidence` — Confidence filtering
- `ix_capsules_archived` — Archive filtering
- `ix_tags_name` — Tag lookup
- `ix_rel_from/to/type` — Relationship queries

## Extensibility

### Adding a New Service

1. Create directory: `services/new_service/`
2. Implement business logic
3. Add routes to API Gateway
4. Add tests
5. Update Docker Compose

### Adding a New Storage Backend

1. Implement database interface
2. Add connection factory
3. Update config
4. Add migration scripts
5. Update tests

## Deployment Patterns

### Local Development
```
Single process + SQLite
```

### Single Server
```
Docker Compose: API + Sync + SQLite volume
```

### Production (Future)
```
K8s: API pods + Sync pod + PostgreSQL + Redis
```
