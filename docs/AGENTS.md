# Agents

Capsule is meant to be read by agents.

1. Search: `POST /api/v1/search` with a short query and tags.
2. Compose: `POST /api/v1/compose` with `max_tokens` sized to the session.
3. Prefer `confidence_min: medium` unless you explicitly want hearsay.

## MCP

```bash
capsule mcp
```

Stdio JSON-RPC 2.0, protocol `2024-11-05`. Tools: `search_capsules`, `compose_context`, `get_capsule`, `create_capsule`, `list_stale`.

Example Cursor MCP config:

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
