# Security

Capsule is local-first. Treat an exposed API as a single-user filesystem.

- Default bind is localhost. Docker images bind `0.0.0.0` on a private compose network; publish ports only on trusted hosts.
- `CAPSULE_API_TOKEN` enables Bearer auth when the port is reachable by others.
- CORS is an explicit origin list. Credentials are not enabled.
- YAML is parsed with `safe_load`. File writes are sandboxed to `CAPSULES_DIR`.
- FTS queries are tokenized and quoted; user text is not passed through as raw FTS syntax.
- SQLite runs with `foreign_keys=ON`, WAL, and a busy timeout.
- There is no multi-user authorization model. Do not put this on the public internet without a reverse proxy that authenticates.
