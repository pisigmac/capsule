# API Documentation

## Base URL

```
http://localhost:9000/api/v1
```

## Authentication

Currently no authentication. For production, add API key headers:
```
Authorization: Bearer <token>
```

## Endpoints

### Capsules

#### Create Capsule
```http
POST /capsules
Content-Type: application/json

{
  "topic": "Auth bypass",
  "content": "JWT verification skipped in staging",
  "tags": ["auth", "bug"],
  "confidence": "high",
  "source": "Claude session #4482"
}
```

#### List Capsules
```http
GET /capsules?archived=false&tag=auth&limit=50&offset=0
```

#### Get Capsule
```http
GET /capsules/{id}
```

#### Update Capsule
```http
PATCH /capsules/{id}
Content-Type: application/json

{
  "topic": "Updated topic",
  "confidence": "medium"
}
```

#### Delete Capsule
```http
DELETE /capsules/{id}
```

#### Archive Capsule
```http
POST /capsules/{id}/archive
```

### Search

#### Search Capsules
```http
POST /search
Content-Type: application/json

{
  "query": "JWT auth",
  "tags": ["security"],
  "confidence": "high",
  "archived": false,
  "limit": 50,
  "offset": 0
}
```

#### Compose Context
```http
POST /compose
Content-Type: application/json

{
  "tags": ["auth", "staging"],
  "query": "middleware",
  "confidence_min": "medium",
  "max_tokens": 4000
}
```

**Response:**
```json
{
  "context": "# Auth bypass\n...",
  "token_estimate": 245
}
```

### Relationships

#### Create Relationship
```http
POST /relationships
Content-Type: application/json

{
  "from_capsule_id": "uuid-1",
  "to_capsule_id": "uuid-2",
  "relationship_type": "blocks"
}
```

#### Get Capsule Relationships
```http
GET /capsules/{id}/relationships
```

### Tags

#### List Tags
```http
GET /tags
```

**Response:**
```json
[
  {"name": "auth", "count": 12},
  {"name": "bug", "count": 5}
]
```

### Sync

#### Sync Directory
```http
POST /sync?path=/path/to/capsules
```

### Stale Capsules

#### Get Stale Capsules
```http
GET /stale?days=90
```

## Error Responses

| Status | Meaning | Example |
|--------|---------|---------|
| 400 | Bad Request | Invalid UUID format |
| 404 | Not Found | Capsule does not exist |
| 422 | Validation Error | Missing required field |
| 500 | Server Error | Database error |

## Rate Limits

No rate limiting in v1.0. Add reverse proxy (nginx, traefik) for production.

## Pagination

All list endpoints support `limit` and `offset` query parameters.
- Default limit: 50
- Max limit: 500
