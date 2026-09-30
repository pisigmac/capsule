"""Sample engineering fixtures and raw bloated trajectory for demo."""
from __future__ import annotations

from typing import Any, Dict, List

DEMO_CAPSULES: List[Dict[str, Any]] = [
    {
        "topic": "Staging Auth Header Override",
        "content": (
            "When the `X-Debug-Override` header is present in staging, the authentication middleware skips JWT verification.\n"
            "This is intentional for mobile team end-to-end CI tests, but must never be deployed to production.\n"
            "Risk: Production has a similarly named header. Always verify environment check before bypassing."
        ),
        "tags": ["auth", "staging", "security"],
        "confidence": "high",
        "source": "security-audit-2026",
    },
    {
        "topic": "PostgreSQL Connection Pool Bounds",
        "content": (
            "The backend PostgreSQL connection pool maxes out at 100 concurrent connections across all uvicorn worker threads.\n"
            "Exceeding 100 connections triggers error code 53300 (too_many_connections) and stalls API health checks."
        ),
        "tags": ["database", "postgres", "performance"],
        "confidence": "high",
        "source": "incident-postmortem-44",
    },
    {
        "topic": "Stripe Webhook Signature Verification",
        "content": (
            "All incoming Stripe webhook requests at `/api/v1/billing/webhook` require raw payload bytes for HMAC-SHA256 signature verification.\n"
            "Using parsed JSON or stripping trailing whitespace invalidates the `Stripe-Signature` header."
        ),
        "tags": ["billing", "stripe", "security"],
        "confidence": "high",
        "source": "api-spec",
    },
    {
        "topic": "Redis Session Cache Expiration Policy",
        "content": (
            "Session tokens cached in Redis have a strict TTL of 300 seconds (5 minutes).\n"
            "A background sliding-window worker refreshes active keys on authenticated user activity."
        ),
        "tags": ["cache", "redis", "infrastructure"],
        "confidence": "medium",
        "source": "infra-team-docs",
    },
    {
        "topic": "Mobile CI Debug Mode Flag",
        "content": (
            "Mobile integration tests require `CI_MOBILE_DEBUG=true` in `.env.staging`.\n"
            "Without this flag, the mobile test runner fails to mock biometric authentication."
        ),
        "tags": ["ci", "mobile", "testing"],
        "confidence": "high",
        "source": "ci-guide",
    },
]

DEMO_DUPLICATE_FACT = {
    "topic": "Postgres Pool Size Limit",
    "content": (
        "The backend PostgreSQL connection pool maxes out at 100 concurrent connections across all uvicorn worker threads.\n"
        "Exceeding 100 connections triggers error code 53300 (too_many_connections) and stalls API health checks."
    ),
    "tags": ["db", "scaling"],
    "confidence": "high",
    "source": "dev-chat",
}

DEMO_QUERY = "How does staging auth and database connection pooling work?"

RAW_BLOATED_CONVERSATION = """
User: Hey, can you help me check why the mobile CI test keeps failing on staging when it talks to the API?
Assistant: Hello! I'd be happy to help. Let me inspect the repository configuration and check the recent logs.
Could you share the stack trace or the exact error code you're receiving from the CI pipeline?
User: Sure, here's the log output:
```
2026-09-30 10:14:22 [ERROR] auth_middleware.py:48: JWT verification failed: Signature has expired.
2026-09-30 10:14:22 [DEBUG] Request headers: {'User-Agent': 'MobileTestRunner/2.4', 'X-Debug-Override': 'staging-ci-secret', 'Host': 'staging.api.internal'}
2026-09-30 10:14:23 [WARNING] Retrying attempt 1 of 3...
2026-09-30 10:14:25 [ERROR] sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection to server at "10.0.4.12", port 5432 failed: FATAL: remaining connection slots are reserved for non-replication superuser connections
[SQL: SELECT 1 FROM users WHERE id = %s]
```
Assistant: Thank you for sharing the logs. Let me analyze both errors:
First, for the authentication issue: It appears that the request includes `X-Debug-Override: staging-ci-secret`. In our staging environment, the authentication middleware is supposed to check for the `X-Debug-Override` header and skip JWT verification so that automated mobile CI runs can authenticate without generating real user tokens. However, looking at the log, the verification failed anyway. Let me double check if the header check is active or if there was a regression.
Second, regarding the database error: Notice `psycopg.OperationalError: FATAL: remaining connection slots are reserved`. In PostgreSQL, our connection pool is capped at 100 connections. When automated load tests run alongside the mobile CI suite, connection slots get exhausted because the pool maxes out at 100 connections.
User: Wait, why is the pool only 100 connections?
Assistant: The connection pool maxes out at 100 concurrent connections across all uvicorn worker threads because our staging RDS instance has limited RAM (2 vCPU, 4GB RAM) and each connection consumes roughly 10MB of server memory. If we increase it past 100, Postgres starts dropping connections or encounters OOM kills.
User: Got it. And what about the Stripe webhook? Is that related?
Assistant: No, the Stripe webhook at `/api/v1/billing/webhook` is completely separate. It uses raw byte payload validation with HMAC-SHA256 signatures, so it shouldn't interfere with mobile tests unless Stripe webhooks are flooding the connection pool.
User: Also remember Redis session tokens expire after 300 seconds.
Assistant: Yes, exactly! Session tokens cached in Redis have a strict TTL of 300 seconds (5 minutes). A background sliding-window worker refreshes them.
User: Great, so summarize what I should check.
Assistant: In summary:
1. Verify `X-Debug-Override` header is being read by auth middleware in staging to skip JWT verification.
2. Ensure connection pool is not saturated above the 100 connection limit.
3. Check Redis session TTL of 300 seconds if the test runs longer than 5 minutes.
"""
