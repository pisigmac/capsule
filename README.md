<div align="center">
  <h1>Capsule</h1>
  <p><b>Atomic knowledge for AI agents.</b></p>
</div>

Capsule stores one fact per `.capsule.md` file. The search index is SQLite locally, or PostgreSQL when you run Docker.

## Quick start

```bash
pip install kapsule   # or: pip install korn / pip install pykorn
kapsule init          # or: capsule init / korn init
```

From a clone:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
capsule init
uvicorn services.api.main:app --host 127.0.0.1 --port 9100 --workers 1
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

- UI: http://localhost:5173
- API: http://localhost:9100/api/v1
- OpenAPI: http://localhost:9100/docs

Docker (Postgres + API + sync + UI):

```bash
./install.sh
```

- UI: http://localhost:8080
- API: http://localhost:9100

## File format

```markdown
---
id: 7c2a9f14-6b81-4d3e-9a0c-1f8e2b4d6c70
topic: "Auth middleware bypass in staging"
tags: [bug, auth, staging]
freshness: 2026-07-11T00:00:00
source: "incident-4482"
confidence: high
---

Staging skips JWT verification when `X-Debug-Override` is present.
This is intentional for E2E tests. Do not remove; mobile CI depends on it.
```

Creating a capsule via the UI, CLI, or API writes this file. Editing the file updates the index.

## CLI

```bash
capsule new "Auth middleware bypass in staging" -t auth -t bug -c high
capsule search "JWT"
capsule compose -t auth -c medium -m 2000
capsule mcp    # stdio MCP server for agents
```

## MCP

Point an MCP client at `capsule mcp` (official SDK, stdio). Optional: `capsule mcp --http --port 9101`.

Tools: `search_capsules`, `compose_context`, `get_capsule`, `create_capsule`, `list_stale`.

```json
{
  "mcpServers": {
    "capsule": {
      "command": "capsule",
      "args": ["mcp"]
    }
  }
}
```

## Architecture

One API process. It indexes `CAPSULES_DIR` on boot and watches for file changes. Do not run multiple uvicorn workers — SQLite plus the watcher assume a single writer.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DEPLOY.md](docs/DEPLOY.md), and [docs/API.md](docs/API.md).

## Tests

```bash
pytest
```

## License

MIT
