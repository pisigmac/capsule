# Features

## Core Features

### 1. Atomic Knowledge Format (.capsule.md)
- YAML frontmatter + markdown body
- Human-readable, machine-parseable
- One fact per file
- Self-describing metadata (freshness, confidence, source)

### 2. Full-Text Search (FTS5)
- SQLite FTS5 virtual table
- Sub-second search across thousands of capsules
- Tag-based filtering
- Confidence filtering
- Archived status filtering

### 3. Context Composition
- Build AI-ready context windows from matching capsules
- Token budget management
- Confidence-based filtering
- Tag-based inclusion

### 4. Knowledge Graph
- Link capsules with typed relationships
- Bidirectional relationship tracking
- Query relationship chains

### 5. File System Sync
- Watch directories for `.capsule.md` files
- Auto-import on file creation/modification
- Hash-based change detection
- Cross-platform (Linux, macOS, Windows)

### 6. Freshness Decay
- Auto-detect stale knowledge (configurable days)
- Archive old capsules
- Surface decaying facts before they rot

### 7. Cross-Project Sharing
- `shared/` directory for cross-project knowledge
- Syndicate learnings across repos
- One fix in Project A becomes a capsule for Project B

### 8. Rich CLI
- Beautiful terminal output with Rich
- Interactive prompts
- Editor integration ($EDITOR)
- Color-coded confidence levels

## API Features

- RESTful CRUD for capsules
- Search endpoint with FTS5
- Compose endpoint for context windows
- Relationship management
- Tag management
- Health checks

## Planned Features

- Web UI for browsing capsules
- Git integration (auto-commit on capsule changes)
- Team sharing via shared database
- Capsule templates
- Import from Notion, Obsidian, Logseq
- Export to PDF, HTML
- AI-powered capsule suggestions
- Duplicate detection
