# Conventions

## How to Work in This Repo

- Keep changes small and testable (PR-sized chunks)
- Prefer refactors that reduce touch points for adding templates/backends
- Keep CLI thin; move business logic into modules/classes
- Always update/extend tests when changing behaviour
- Never commit secrets (use env vars)

See `docs/golden-principles.md` for mechanical enforcement of key rules.

## Error Handling

- Always raise `ProviderError` or `NthLayerError` subclasses for application errors
- Never use bare `Exception` or `RuntimeError` in application code
- Provider modules define their own error subclasses: `GrafanaProviderError(ProviderError)`
- Import errors from `nthlayer.core.errors`
- Exception handling with context at layer boundaries — see Golden Principle #4

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Warning/error |
| 2 | Critical/blocked |

## Commit Messages

Format: `<type>: <description> (<bead-id>)`

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `lint`

When fixing a GitHub Issue: `fix: <description> (<bead-id>, closes #<number>)`

## Structured Logging

Field naming conventions:
- `err` or `error` for errors (not `e`, `failure`, `exc`)
- `component` for the subsystem (not `module`, `pkg`, `source`)
- `duration_ms` for timing (not `elapsed`, `time`, `took`)

See Golden Principle #3 for enforcement details.

## Task Tracking with Beads (bd)

This project uses [Beads](https://github.com/steveyegge/beads) for issue tracking. **Always use the `bd` CLI** — never create individual JSON files in `.beads/`.

### Essential Commands

```bash
bd ready              # Show tasks ready to work on (no blockers)
bd list               # List all issues
bd list --status open # List open issues only
bd show <id>          # Show issue details
bd create --title "..." --description "..." --priority 1 --type feature
bd update <id> --status in_progress
bd close <id> --reason "What was done"
bd comment <id> "Comment text"
bd stats              # Project statistics
bd blocked            # Show blocked issues
bd dep tree <id>      # Show dependency tree
```

### Workflow

1. Check what's ready: `bd ready`
2. Start work: `bd update <id> --status in_progress`
3. Do the work
4. Close when done: `bd close <id> --reason "Description"`
5. Check next task: `bd ready`

### Linking to Specifications

For detailed feature specs, add a comment to the bd issue:
```bash
bd comment <id> "Specification: FEATURE_SPEC.md - Full implementation details."
```

### File Structure (DO NOT MODIFY MANUALLY)

```
.beads/
├── issues.jsonl    # Source of truth (managed by bd)
├── config.yaml     # Configuration
├── metadata.json   # Metadata
└── beads.db       # SQLite cache (gitignored)
```

## Workflow Tooling

### Session Lifecycle

- **SessionStart hook** automatically loads Beads state and recent spec changes
- **Stop hook** enforces "land the plane" discipline — you cannot end a session with uncommitted changes, unpushed commits, or stale in-progress beads

### Slash Commands

- `/spec-to-beads <spec-file>` — Decompose a spec into Beads issues with dependency tracking. Do NOT implement — only create the task graph.
- `/audit-codebase` — Run a systematic codebase audit using the code-auditor subagent. Files findings as dual Beads + GitHub Issues.
- `/gc-sweep` — Entropy cleanup sweep using the gc-sweep subagent.
- `/doc-garden` — Documentation freshness check using the doc-gardener subagent.

### Autonomous Execution

- Ralph loop prompt: `.claude/ralph-prompt.md`
- Ralph loop runner: `.claude/ralph-loop.sh [max-iterations]`
- Completion promise: `RALPH_COMPLETE`

### Specs

Specification files live in `specs/`. When implementing from a spec, always reference the spec file path in Beads task notes for traceability. If you make architectural decisions that diverge from the spec, document them in the task's notes field.

## Release Process

- PyPI uses trusted publisher (no token needed)
- Create a GitHub release → triggers `.github/workflows/release.yml` → auto-publishes to PyPI
- Version is defined **only** in `pyproject.toml` (single source of truth via `importlib.metadata`)
- **CHANGELOG.md must be updated** before every release with all changes since the last release
