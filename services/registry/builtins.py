"""Curated, pre-verified offline knowledge packs shipped with Capsule."""
from __future__ import annotations

from typing import Dict, List
from services.registry.manifest import PackManifest

BUILTIN_MANIFESTS: Dict[str, PackManifest] = {
    "python-best-practices": PackManifest(
        name="python-best-practices",
        version="1.0.0",
        author="Vikas Budde",
        description="Essential Python performance, concurrency, and architecture rules for agents",
        caps_count=5,
        tags=["python", "asyncio", "dataclasses", "performance", "typing"],
        verified=True,
    ),
    "fastapi-security": PackManifest(
        name="fastapi-security",
        version="1.0.0",
        author="Capsule Security Guild",
        description="Production API security patterns, auth invariants, and OWASP defenses for FastAPI",
        caps_count=5,
        tags=["fastapi", "security", "auth", "jwt", "owasp"],
        verified=True,
    ),
    "postgres-performance": PackManifest(
        name="postgres-performance",
        version="1.0.0",
        author="PostgreSQL Engineering",
        description="PostgreSQL indexing, query optimization, connection pool sizing, and locking invariants",
        caps_count=3,
        tags=["postgres", "database", "sql", "performance", "indexes"],
        verified=True,
    ),
}

BUILTIN_PACKS: Dict[str, Dict[str, str]] = {
    "python-best-practices": {
        "asyncio-task-shield.caps.md": """---
id: py-asyncio-shield-001
topic: Protect critical cleanup logic using asyncio.shield
tags:
  - python
  - asyncio
  - concurrency
source: knowledge-pack:python-best-practices
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Protect critical cleanup logic using asyncio.shield

When an asyncio Task is cancelled, any awaited coroutine raises `asyncio.CancelledError`. If a task is inside a critical step—such as releasing an acquired distributed lock, closing a transactional state, or committing an audit record—the cancellation interrupts execution immediately.

To guarantee that a critical sub-coroutine runs to completion even if the enclosing task receives a cancellation request, wrap it with `asyncio.shield()`:

```python
import asyncio

async def release_resource():
    await write_audit_log()
    await db.release_lease()

async def worker():
    try:
        await perform_work()
    finally:
        # Prevents CancelledError from aborting release_resource midway
        await asyncio.shield(release_resource())
```
""",
        "dataclass-mutable-defaults.caps.md": """---
id: py-dataclass-defaults-002
topic: Avoid mutable default arguments in dataclasses with default_factory
tags:
  - python
  - dataclasses
  - bugs
source: knowledge-pack:python-best-practices
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Avoid mutable default arguments in dataclasses with default_factory

In Python, defining mutable default values (lists, dicts, sets) on class attributes shares that single instance across all instances of the class.

In `dataclasses`, Python raises a `ValueError` if you attempt `items: list = []`. Always declare mutable fields using `field(default_factory=...)`:

```python
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class AgentState:
    session_id: str
    # Safe: each instance gets an independent list and dict
    history: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
```
""",
        "exception-group-handling.caps.md": """---
id: py-exception-groups-003
topic: Handle concurrent task failures with ExceptionGroup and except*
tags:
  - python
  - asyncio
  - exception-handling
source: knowledge-pack:python-best-practices
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Handle concurrent task failures with ExceptionGroup and except*

Python 3.11+ introduces `asyncio.TaskGroup`, which aggregates concurrent task exceptions into an `ExceptionGroup`. Using standard `except Exception:` catches the group wrapper rather than isolating the individual sub-exceptions.

Always use `except*` syntax to unpack specific exception types concurrently:

```python
import asyncio

async def run_pipeline():
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(fetch_data())
            tg.create_task(write_cache())
    except* TimeoutError as eg:
        logger.warning(f"Timeout occurred in tasks: {eg.exceptions}")
    except* ConnectionError as eg:
        logger.error(f"Network failure: {eg.exceptions}")
```
""",
        "fastapi-lifespan-caching.caps.md": """---
id: py-fastapi-lifespan-004
topic: Manage application startup and shutdown using FastAPI lifespan context
tags:
  - python
  - fastapi
  - architecture
source: knowledge-pack:python-best-practices
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Manage application startup and shutdown using FastAPI lifespan context

FastAPI has deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")`. The modern, type-safe approach is an `asynccontextmanager` passed to `FastAPI(lifespan=lifespan)`.

This ensures clean teardown even during fatal startup errors and yields shared state into `request.state`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import httpx

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize pooled connection
    client = httpx.AsyncClient(timeout=10.0)
    yield {"http_client": client}
    # Shutdown: cleanly close resources
    await client.aclose()

app = FastAPI(lifespan=lifespan)
```
""",
        "pydantic-v2-field-validator.caps.md": """---
id: py-pydantic-v2-validator-005
topic: Use classmethod field_validator in Pydantic v2
tags:
  - python
  - pydantic
  - validation
source: knowledge-pack:python-best-practices
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Use classmethod field_validator in Pydantic v2

In Pydantic v2, `@validator` is deprecated in favor of `@field_validator`. Field validators MUST be declared as `@classmethod`, and access to surrounding field values is passed through `ValidationInfo`:

```python
from pydantic import BaseModel, field_validator, ValidationInfo

class UserPayload(BaseModel):
    username: str
    slug: str

    @field_validator("slug", mode="after")
    @classmethod
    def normalize_slug(cls, v: str, info: ValidationInfo) -> str:
        clean = v.strip().lower().replace(" ", "-")
        if not clean:
            raise ValueError("Slug cannot be empty")
        return clean
```
""",
    },
    "fastapi-security": {
        "cors-wildcard-credentials.caps.md": """---
id: sec-cors-credentials-001
topic: Never pair CORS wildcard origin with allow_credentials=True
tags:
  - fastapi
  - security
  - cors
source: knowledge-pack:fastapi-security
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Never pair CORS wildcard origin with allow_credentials=True

Browsers strictly forbid returning `Access-Control-Allow-Origin: *` when `Access-Control-Allow-Credentials: true` is set. Furthermore, attempting to bypass this by reflecting the incoming `Origin` header dynamically without validation exposes authenticated sessions to cross-site request forgery.

Always specify an explicit whitelist of trusted origins:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

TRUSTED_ORIGINS = [
    "https://app.example.com",
    "https://staging.example.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=TRUSTED_ORIGINS,  # NEVER ["*"] with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```
""",
        "jwt-algorithm-none-attack.caps.md": """---
id: sec-jwt-alg-none-002
topic: Explicitly specify algorithms in PyJWT decode to prevent alg=none attack
tags:
  - fastapi
  - security
  - jwt
  - auth
source: knowledge-pack:fastapi-security
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Explicitly specify algorithms in PyJWT decode to prevent alg=none attack

If JWT verification does not pin the expected signing algorithm, attackers can alter the token header to `{"alg": "none"}` or substitute an asymmetric RS256 key with an HMAC HS256 signed using the server's public key.

Always enforce explicit `algorithms=["HS256"]` during `jwt.decode()`:

```python
import jwt
from fastapi import HTTPException, status

SECRET_KEY = "your-strong-random-key"
ALGORITHM = "HS256"

def verify_token(token: str) -> dict:
    try:
        # Enforces HS256; rejects "none" and public key substitution
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
```
""",
        "constant-time-token-compare.caps.md": """---
id: sec-token-compare-003
topic: Use secrets.compare_digest for constant-time API key verification
tags:
  - fastapi
  - security
  - cryptography
source: knowledge-pack:fastapi-security
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Use secrets.compare_digest for constant-time API key verification

Standard string comparison (`token == expected_token`) exits immediately at the first mismatched character. Attackers can measure response time variations down to microseconds to deduce tokens byte-by-byte (timing attacks).

Always use `secrets.compare_digest` for secret strings:

```python
import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
EXPECTED_API_KEY = "super-secret-production-token"

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key or not secrets.compare_digest(api_key, EXPECTED_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key"
        )
    return api_key
```
""",
        "rate-limiting-slowapi.caps.md": """---
id: sec-rate-limit-004
topic: Protect public endpoints against brute force using SlowAPI
tags:
  - fastapi
  - security
  - rate-limiting
source: knowledge-pack:fastapi-security
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Protect public endpoints against brute force using SlowAPI

Unprotected authentication routes (`/login`, `/token`, `/reset-password`) are vulnerable to credential stuffing and denial of service.

Use `slowapi` with IP or user key identifiers to enforce rate limiting:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request):
    return {"message": "Authenticated"}
```
""",
        "path-traversal-validation.caps.md": """---
id: sec-path-traversal-005
topic: Validate filesystem paths against base directory to prevent Path Traversal
tags:
  - fastapi
  - security
  - path-traversal
source: knowledge-pack:fastapi-security
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Validate filesystem paths against base directory to prevent Path Traversal

When serving files or writing uploads based on user-supplied filenames, characters like `../` or encoded `%2e%2e%2f` can escape the intended root directory and read `/etc/passwd` or overwrite source code.

Always resolve paths canonically and verify that the target directory starts with the allowed base:

```python
from pathlib import Path
from fastapi import HTTPException, status

BASE_STORAGE = Path("/var/app/data").resolve()

def safe_resolve(user_filename: str) -> Path:
    # Resolve canonical absolute path
    target = (BASE_STORAGE / user_filename).resolve()
    
    # Boundary check
    if not str(target).startswith(str(BASE_STORAGE)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path traversal sequence"
        )
    return target
```
""",
    },
    "postgres-performance": {
        "b-tree-composite-index-order.caps.md": """---
id: pg-btree-composite-001
topic: Order composite B-Tree indexes by equality columns before range columns
tags:
  - postgres
  - sql
  - indexes
  - performance
source: knowledge-pack:postgres-performance
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Order composite B-Tree indexes by equality columns before range columns

In PostgreSQL, a B-Tree index can only navigate sequentially past the first inequality/range condition (`>`, `<`, `BETWEEN`, `LIKE 'prefix%'`). If a range column is placed first, subsequent columns cannot be used to narrow the index scan.

Always order index columns: `(equality_col1, equality_col2, ..., range_col)`:

```sql
-- Query:
SELECT * FROM events 
WHERE tenant_id = 'org_123' 
  AND status = 'pending' 
  AND created_at >= '2026-01-01';

-- OPTIMAL: Equality columns first, range column last
CREATE INDEX idx_events_lookup 
ON events (tenant_id, status, created_at);
```
""",
        "partial-indexes-soft-deletes.caps.md": """---
id: pg-partial-index-002
topic: Use partial indexes to exclude soft-deleted rows and NULLs
tags:
  - postgres
  - sql
  - indexes
  - optimization
source: knowledge-pack:postgres-performance
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Use partial indexes to exclude soft-deleted rows and NULLs

Tables using soft-deletes (`deleted_at TIMESTAMP NULL`) often accumulate millions of inactive rows. Standard indexes index every row, consuming excessive memory and cache space.

Adding a `WHERE deleted_at IS NULL` predicate produces partial indexes that are 60-90% smaller and faster to traverse:

```sql
-- Partial index only includes active records
CREATE INDEX idx_users_active_email 
ON users (email) 
WHERE deleted_at IS NULL;
```
""",
        "connection-pooling-sizing.caps.md": """---
id: pg-conn-pooling-003
topic: Size PostgreSQL connection pools to 2x CPU cores plus spindle count
tags:
  - postgres
  - architecture
  - performance
source: knowledge-pack:postgres-performance
confidence: high
created: 2026-09-30T10:00:00+00:00
modified: 2026-09-30T10:00:00+00:00
---

# Size PostgreSQL connection pools to 2x CPU cores plus spindle count

PostgreSQL uses a process-per-connection model. Allocating hundreds of concurrent active connections leads to severe CPU context-switching thrashing and memory bloat.

Use PgBouncer in transaction mode and size worker connection pools according to the standard formula:

$$\\text{pool\\_size} = (\\text{core\\_count} \\times 2) + \\text{effective\\_spindle\\_count}$$

For a 4-core SSD database server, a pool size of **9 to 12 connections** will routinely outperform a pool of 200 unmanaged connections with significantly lower latency.
""",
    },
}
