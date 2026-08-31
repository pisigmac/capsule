# AgentDrive — Agent Governance

## Scope
This AGENTS.md governs ALL AI providers (Claude, Codex, Cursor, OpenAI, etc.)
accessing this vault via MCP or direct filesystem.

## Rules
1. **Branch Rule**: All writes go to `dev` branch. Never commit to `main` directly.
2. **Approval Gate**: Every write must be staged in `.vault/staging/` and raised as a PR.
3. **Schema Rule**: Every markdown file MUST include frontmatter per its directory config.
4. **Archive Rule**: Files older than threshold are moved to `.vault/archive/`. Do not delete.
5. **Attribution Tags**: Every markdown file must include `source: <provider>` and `model: <model-name>` in frontmatter.
6. **No Raw Secrets**: Never write API keys, tokens, or passwords into any vault file.
7. **Cross-Reference**: Link related entries with `[[WikiLinks]]` or `related:` frontmatter.
8. **Confidence Tag**: Mark speculative content with `confidence: low`.
9. **Git Tracking**: When committing code, you MUST identify your model using the author flag. Example: `git commit --author="AgentDrive (Claude 3.5) <ai@agentdrive.com>"`.
10. **Error Tracking**: Whenever an error is encountered and fixed, you MUST document it in a `debugging.md` file. Format: `ERROR: <Details> | Date: <date> | Status: <new/re-occur> | Fix: <Fix description>`.
11. **Startup Scripts**: If `start_all.sh` and `stop_all.sh` scripts do not exist in the repository, you MUST create them to manage the project's services.

## Directory Quick Reference
| Directory | Purpose | Archive | Template |
|-----------|---------|---------|----------|
| projects/ | Active work | 120d | templates/project.md |
| people/ | Contacts | Never | templates/person.md |
| goals/ | OKRs | 365d | templates/goal.md |
| meetings/ | Meeting notes | 90d | templates/meeting.md |
| decisions/ | ADRs | Never | templates/decision.md |
| resources/ | Bookmarks | 180d | templates/resource.md |
| experiments/ | Prototypes | 30d | templates/experiment.md |
| threads/ | Conversations | 120d | templates/thread.md |
| reviews/ | Retrospectives | 365d | templates/review.md |
