# Empty States

## CLI
- `capsule search` with no results: "No capsules found. Create one with `capsule new`"
- `capsule stale` with no stale: "All capsules are fresh."
- `capsule status` with 0 capsules: "Workspace empty. Run `capsule init`"

## API
- `GET /capsules` empty: `[]` with 200
- `GET /tags` empty: `[]` with 200
- `POST /search` no matches: `[]` with 200

## First-Time UX
`capsule init` creates a welcome capsule explaining the system.
