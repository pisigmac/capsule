# Security

## Security Model

Capsule is a local-first tool. By default, all data stays on your machine.

## Threat Model

### Assets
1. Capsule content (knowledge)
2. Database file
3. Configuration (potentially sensitive paths)

### Threats
1. **Unauthorized access** — Local file system access
2. **Data loss** — Database corruption, accidental deletion
3. **Injection** — Malicious capsule content
4. **Network exposure** — API running on public interface

## Mitigations

### Local Security

| Threat | Mitigation |
|--------|------------|
| File system access | Standard OS permissions |
| Database access | SQLite file permissions |
| API exposure | Bind to localhost by default |

### Input Validation

- YAML frontmatter parsed safely (no arbitrary code execution)
- Content sanitized for XSS (future web UI)
- File paths validated (no directory traversal)
- UUID validation on all IDs

### API Security

- CORS enabled for development (restrict in production)
- No authentication in v1.0 (add for production)
- Input validation via Pydantic
- SQL injection prevention via SQLAlchemy ORM

## Best Practices

### For Users

1. **Keep database local** — Don't expose SQLite over network
2. **Backup regularly** — Copy `capsule.db` to secure location
3. **Review capsule content** — Don't store passwords in capsules
4. **Update dependencies** — `pip install -U` regularly

### For Administrators

1. **Run behind reverse proxy** — nginx/traefik with SSL
2. **Enable authentication** — Add API key or OAuth
3. **Monitor logs** — Watch for unusual access patterns
4. **Restrict API access** — Firewall rules, VPN

## Vulnerability Reporting

If you discover a security vulnerability:

1. Email: security@capsule.dev
2. Do not open public issues
3. Allow 30 days for fix before disclosure
4. Credit will be given in changelog

## Dependencies

| Dependency | Version | Known Vulnerabilities |
|------------|---------|----------------------|
| fastapi | 0.110.0 | None known |
| sqlalchemy | 2.0.0 | None known |
| pydantic | 2.0.0 | None known |
| pyyaml | 6.0.0 | None known |

Regular security audits via `pip-audit`:

```bash
pip install pip-audit
pip-audit
```

## Compliance

### GDPR (Future)
- Right to export data
- Right to delete data
- Data processing records
- Consent management

### SOC2 (Enterprise)
- Access controls
- Audit logging
- Encryption at rest
- Encryption in transit
