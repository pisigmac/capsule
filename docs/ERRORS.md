# Error Handling

## Error Philosophy

Capsule follows these error handling principles:
1. **Fail fast** — Validate early, fail clearly
2. **No silent failures** — Every error is logged and reported
3. **Graceful degradation** — Core features work even if non-critical services fail
4. **User-friendly messages** — Technical details in logs, plain language for users

## Error Categories

### 1. Validation Errors (400)

**Cause:** Invalid user input

**Examples:**
- Topic too short (< 3 characters)
- Content too short (< 10 characters)
- Invalid confidence level
- Invalid UUID format
- Malformed YAML frontmatter

**Response:**
```json
{
  "detail": [
    {
      "loc": ["body", "topic"],
      "msg": "ensure this value has at least 3 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

**CLI Output:**
```
Error: Topic must be at least 3 characters
```

### 2. Not Found Errors (404)

**Cause:** Requested resource doesn't exist

**Examples:**
- Capsule ID not found
- Tag not found
- Relationship not found
- File path not found

**Response:**
```json
{
  "detail": "Capsule not found"
}
```

**CLI Output:**
```
Error: Capsule not found
```

### 3. Database Errors (500)

**Cause:** SQLite operation failed

**Examples:**
- Database locked (concurrent write)
- Disk full
- Corrupted database
- FTS5 index mismatch

**Response:**
```json
{
  "detail": "Database error occurred"
}
```

**CLI Output:**
```
Error: Database operation failed. Check disk space and permissions.
```

### 4. Parse Errors (400)

**Cause:** Invalid .capsule.md format

**Examples:**
- Invalid YAML frontmatter
- Missing required fields
- Encoding issues
- File not readable

**CLI Output:**
```
Error: Failed to parse capsule.md: Invalid YAML at line 3
```

### 5. Sync Errors (500)

**Cause:** File system watcher failure

**Examples:**
- Directory not accessible
- Permission denied
- Watchdog initialization failed
- Too many files open

**CLI Output:**
```
Error: Cannot watch directory: Permission denied
```

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `CAPSULE_001` | 400 | Invalid capsule format |
| `CAPSULE_002` | 400 | Validation failed |
| `CAPSULE_003` | 404 | Capsule not found |
| `CAPSULE_004` | 404 | Tag not found |
| `CAPSULE_005` | 404 | Relationship not found |
| `CAPSULE_006` | 500 | Database error |
| `CAPSULE_007` | 500 | FTS5 error |
| `CAPSULE_008` | 500 | Sync error |
| `CAPSULE_009` | 500 | Parse error |
| `CAPSULE_010` | 400 | Invalid UUID |

## Logging

### Log Levels

| Level | Used For |
|-------|----------|
| DEBUG | SQL queries, file watcher events |
| INFO | API requests, sync operations |
| WARNING | Stale capsules, slow queries |
| ERROR | Failed operations, exceptions |
| CRITICAL | Database corruption, data loss |

### Log Format

```
2026-07-11 14:32:15 [INFO] api: POST /capsules 201 45ms
2026-07-11 14:32:16 [ERROR] sync: Failed to parse /path/to/file.capsule.md: Invalid YAML
```

## Recovery

| Error | Recovery Action |
|-------|----------------|
| Database locked | Retry with exponential backoff |
| Parse error | Skip file, log error, continue |
| Sync failure | Restart watcher, re-scan |
| FTS5 mismatch | Rebuild index |
| Disk full | Archive old capsules, alert user |

## Retry Policy

```python
# services/shared/retry.py (future)
class RetryPolicy:
    max_retries = 3
    base_delay = 1  # seconds
    max_delay = 30  # seconds
    exponential_base = 2
```
