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

## Comments and Facts About Other Files

A comment or docstring may describe its own file. A fact about another file
is either cited by a stable name and pinned by a test, or left out.

- **A stable name** is a title: a rule's title, a section heading, a
  function or constant name. Never a rule number and never a line number;
  both move when something is inserted above them.
- **Pinned by a test** means a test fails when the cited thing is renamed,
  moved or removed. A citation nothing checks is the same defect with better
  spelling.
- **Left out** is a real option, and often the right one. If the fact is not
  worth a test, it is not worth asserting in prose that will outlive it.

This applies across repositories as well as within one: a pointer into a
sibling repo's file is the least checkable kind.

**Why:** claims about the same file get corrected when the file changes,
because the author is looking at them. Claims about another file do not. One
gate found six stale ones (a floor, a file, a constant and a count, each
somewhere else), four of them written during the gate itself (opensrm-ir5m).
A later change made to fix one such pointer introduced three more before it
merged (opensrm-v929). In neither case had a claim about the comment's own
file gone stale.

**Cost:** this forbids some useful prose. A sentence saying where the other
half of a mechanism lives is helpful right up to the day it is wrong.

**Enforcement:** DOCUMENTATION, the first step of the promotion ladder,
since 2026-11-18 (opensrm-p29v). It is not a gate review check.

**Promotion:** violations are counted from that date. On the third, file
`[PROMOTE] cross-file claims to <next level>` and promote the mechanical part
only: a citation by rule number, and a path that does not exist. Those two
can be caught by a lint or a structural test. Whether a sentence asserts a
fact about another file at all needs judgement, and stays here.

**Violations seen since 2026-11-18:** none recorded. Add each one here, with
its bead, when it is found.

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
