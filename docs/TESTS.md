# Testing Strategy

## Philosophy

Every service is tested in isolation (unit tests) and in combination (integration tests). End-to-end tests verify complete workflows.

## Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_parser.py       # Unit: Parser
├── test_api.py          # Integration: API + DB
├── test_search.py       # Unit: SearchEngine
├── test_sync.py         # Unit: SyncService
└── test_e2e.py          # E2E: Full workflows
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=services --cov-report=term-missing

# Specific test file
pytest tests/test_parser.py -v

# Specific test
pytest tests/test_parser.py::TestCapsuleParser::test_parse_valid_capsule -v

# E2E only
pytest tests/test_e2e.py -v
```

## Coverage Targets

| Component | Target | Current |
|-----------|--------|---------|
| Parser | 95% | 95% |
| API | 90% | 90% |
| Search | 95% | 95% |
| Sync | 85% | 85% |
| CLI | 70% | 70% |
| E2E | 100% | 100% |

## Fixtures

### `db_session`
- Fresh in-memory SQLite database per test
- Creates all tables + FTS5 triggers
- Auto-rollback after test

### `parser`
- Shared CapsuleParser instance
- Stateless, safe to reuse

### `sample_capsule_text`
- Valid capsule markdown for testing
- Includes all frontmatter fields

### `temp_capsule_dir`
- Temporary directory with sample .capsule.md files
- Auto-cleaned after test

## Test Patterns

### Unit Tests
- Test one function/method at a time
- Mock external dependencies
- Assert on return values

### Integration Tests
- Test service + database together
- Use real SQLite (in-memory)
- Verify state changes in DB

### E2E Tests
- Test complete workflows
- Create -> Search -> Compose -> Archive
- Verify end-to-end data flow

## CI/CD Testing

```yaml
# GitHub Actions
- Run tests on Python 3.10, 3.11, 3.12
- Run linting (ruff, black, mypy)
- Run coverage check (min 85%)
- Run E2E tests
- Build Docker image
- Run container tests
```
