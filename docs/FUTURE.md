# Future Roadmap

## Q3 2026 (Next 3 Months)

### Web UI
- Browse capsules with faceted search
- Visual relationship graph (D3.js)
- Real-time sync status dashboard
- Capsule editor with preview

### Git Integration
- Auto-commit capsule changes
- Git diff for capsules
- Branch-aware capsule states
- Merge conflict resolution for .capsule.md files

### Import/Export
- Notion importer
- Obsidian vault importer
- Logseq graph importer
- Markdown bulk export
- PDF/HTML export

### Team Features
- Shared SQLite over network (SQLite HTTP)
- User authentication
- Capsule ownership
- Comment threads on capsules

## Q4 2026 (Months 4-6)

### AI Enhancements
- Auto-generate capsules from code comments
- Suggest tags using embeddings
- Detect duplicate knowledge
- Summarize long capsules
- Auto-archive obsolete capsules

### Performance
- PostgreSQL backend option
- Redis caching layer
- Async search with Celery
- Distributed sync service

### Ecosystem
- VS Code extension
- Cursor extension
- Claude Code skill
- MCP server
- Neovim plugin

## 2027 (Beyond)

### Enterprise
- SAML/SSO integration
- Audit logs
- Compliance reporting (SOC2, GDPR)
- On-premise deployment
- Custom integrations

### Advanced Features
- Capsule versioning
- Time-travel (view knowledge at any point)
- Knowledge decay prediction
- Team knowledge health scores
- Capsule quality metrics

### Platform
- Hosted cloud service
- Mobile app (read-only)
- Browser extension (capture web knowledge)
- Slack/Discord bot
- Zapier/Make integration

## Technical Debt

- [ ] Add proper dependency injection
- [ ] Extract CapsuleService from routes.py
- [ ] Add async database operations
- [ ] Implement proper logging (structlog)
- [ ] Add OpenTelemetry tracing
- [ ] Improve test coverage to 95%+
- [ ] Add property-based tests (Hypothesis)
- [ ] Add load tests (Locust)
