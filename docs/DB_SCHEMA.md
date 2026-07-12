# Database Schema

## Entity Relationship Diagram

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Capsule   │◄─────►│  CapsuleTag │◄─────►│    Tag      │
│             │   M:N  │             │  M:N  │             │
│ id (PK)     │       │ capsule_id  │       │ id (PK)     │
│ topic       │       │ tag_id      │       │ name (UQ)   │
│ content     │       └─────────────┘       │ created_at  │
│ freshness   │                               └─────────────┘
│ source      │
│ confidence  │       ┌─────────────────────┐
│ created_at  │◄─────►│ CapsuleRelationship │
│ updated_at  │  1:M  │                     │
│ archived    │       │ id (PK)             │
│ file_path   │       │ from_capsule_id (FK)│
└─────────────┘       │ to_capsule_id (FK)  │
                      │ relationship_type   │
                      │ created_at          │
                      └─────────────────────┘
```

## Tables

### capsules

Primary storage for knowledge atoms.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, auto | Unique identifier |
| topic | VARCHAR(500) | NOT NULL, INDEX | Human-readable title |
| content | TEXT | NOT NULL | Markdown body |
| freshness | DATETIME | NOT NULL | Last verified date |
| source | VARCHAR(500) | NULL | Origin of knowledge |
| confidence | VARCHAR(20) | NOT NULL | high/medium/low/hearsay |
| created_at | DATETIME | NOT NULL | Creation timestamp |
| updated_at | DATETIME | NOT NULL | Last modification |
| archived | BOOLEAN | NOT NULL, DEFAULT FALSE | Archive status |
| file_path | VARCHAR(1000) | NULL | Source file location |

**Indexes:**
- `ix_capsules_topic` — Topic search
- `ix_capsules_freshness` — Stale detection
- `ix_capsules_confidence` — Confidence filtering
- `ix_capsules_archived` — Archive filtering

### tags

Categorization labels.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, auto | Unique identifier |
| name | VARCHAR(100) | NOT NULL, UNIQUE | Tag name |
| created_at | DATETIME | NOT NULL | Creation timestamp |

**Indexes:**
- `ix_tags_name` — Tag lookup

### capsule_tags

Many-to-many junction table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| capsule_id | UUID | PK, FK → capsules | Capsule reference |
| tag_id | UUID | PK, FK → tags | Tag reference |

**Constraints:**
- CASCADE DELETE on both foreign keys

### capsule_relationships

Knowledge graph edges.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, auto | Unique identifier |
| from_capsule_id | UUID | NOT NULL, FK → capsules | Source capsule |
| to_capsule_id | UUID | NOT NULL, FK → capsules | Target capsule |
| relationship_type | VARCHAR(50) | NOT NULL | Type of relationship |
| created_at | DATETIME | NOT NULL | Creation timestamp |

**Indexes:**
- `ix_rel_from` — Outgoing queries
- `ix_rel_to` — Incoming queries
- `ix_rel_type` — Type filtering

**Constraints:**
- CASCADE DELETE on both foreign keys

### capsule_search (FTS5 Virtual Table)

Full-text search index.

| Column | Type | Description |
|--------|------|-------------|
| topic | TEXT | Indexed topic |
| content | TEXT | Indexed content |

**Properties:**
- Virtual table using FTS5
- Content table: `capsules`
- Content rowid: `id`
- Auto-synced via triggers

## Triggers

### capsules_ai (AFTER INSERT)
```sql
INSERT INTO capsule_search(rowid, topic, content)
VALUES (new.id, new.topic, new.content);
```

### capsules_ad (AFTER DELETE)
```sql
INSERT INTO capsule_search(capsule_search, rowid, topic, content)
VALUES ('delete', old.id, old.topic, old.content);
```

### capsules_au (AFTER UPDATE)
```sql
INSERT INTO capsule_search(capsule_search, rowid, topic, content)
VALUES ('delete', old.id, old.topic, old.content);
INSERT INTO capsule_search(rowid, topic, content)
VALUES (new.id, new.topic, new.content);
```

## Migrations

### Current Version

v1.0.0 — Initial schema

### Migration History

| Version | Date | Changes |
|---------|------|---------|
| v1.0.0 | 2026-07-11 | Initial release |

### Future Migrations

- v1.1.0: Add `capsule_embeddings` table (for vector search)
- v1.2.0: Add `users` table (for multi-user support)
- v1.3.0: Add `capsule_versions` table (for versioning)

## Data Retention

- Archived capsules: Retained indefinitely (user-managed)
- Deleted capsules: Hard delete (no soft delete)
- Tags: Orphaned tags auto-cleaned (future)
- Relationships: Cascade delete with capsules
