# Agents

## Capsule for AI Agents

Capsule is designed to be consumed by AI agents. The format is intentionally simple so agents can parse it without complex tooling.

### Agent Protocol

When an agent starts a session, it should:

1. **Read the workspace index**
   ```
   GET /api/v1/capsules?limit=50
   ```

2. **Query relevant capsules**
   ```
   POST /api/v1/search
   {"query": "auth middleware", "tags": ["security"], "confidence": "high"}
   ```

3. **Compose context**
   ```
   POST /api/v1/compose
   {"tags": ["auth", "staging"], "max_tokens": 2000}
   ```

### Agent-Friendly Properties

| Property | Benefit |
|----------|---------|
| Atomic size | 50-300 tokens per capsule — fits in context windows |
| Confidence scoring | Agent can weight facts by reliability |
| Freshness | Agent knows if knowledge is current |
| Source attribution | Agent can trace facts to origin |
| Typed relationships | Agent understands dependencies |

### Example Agent Prompt

```
You are a senior engineer working on the payment gateway.

Before suggesting changes, read the relevant capsules:
- Search for "payment" and "auth"
- Read capsules with confidence >= medium
- Check relationships for blocked tasks

Current context:
{composed_context}
```

### MCP Integration

Capsule can expose an MCP (Model Context Protocol) server:

```python
# tools/get_capsules
{
  "name": "get_capsules",
  "description": "Retrieve capsules by tags or query",
  "parameters": {
    "tags": ["string"],
    "query": "string",
    "confidence": "string"
  }
}
```

### Agent Memory

Use Capsule as an agent's long-term memory:
- Each session creates a capsule
- Agent reads previous session capsules before starting
- Knowledge accumulates instead of being lost

### Best Practices

1. **One fact per capsule** — agents parse faster
2. **High confidence for critical facts** — agents trust these more
3. **Tag consistently** — agents rely on tags for filtering
4. **Link related capsules** — agents follow relationship chains
5. **Archive obsolete knowledge** — agents don't waste tokens on stale facts
