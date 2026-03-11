# NthLayer Harness Engineering — Implementation Spec

## Overview

This spec implements entropy management and quality infrastructure for the NthLayer codebase, inspired by OpenAI's "Harness Engineering" practices. The goal is to minimise AI slop by encoding human taste into mechanically enforceable rules that compound over time.

This spec is designed to be executed by Claude Code. **Read this entire document before creating an implementation plan.** Do not modify existing source code. Do not delete or overwrite existing files unless explicitly instructed. When a step says "merge into existing file", read the file first and integrate — do not replace.

---

## Prerequisites

- The workflow setup from `specs/nthlayer-workflow-setup.md` should already be applied (hooks, slash commands, Ralph loop)
- The code review and audit setup from `specs/nthlayer-code-review-audit.md` should already be applied (subagents, GitHub Action, `scripts/create-audit-issue.sh`)
- `bd` CLI installed and initialised
- `gh` CLI authenticated

If those specs haven't been applied yet, apply them first.

---

## Step 1: Golden Principles Document

Create `docs/golden-principles.md`. This is the single source of truth for opinionated, mechanical rules that keep the codebase consistent across agent runs. Each principle must be testable — either by a linter, a structural test, or a grep pattern.

### File: `docs/golden-principles.md`

```markdown
# Golden Principles

These are opinionated, mechanical rules that keep the NthLayer codebase legible
and consistent across agent runs. Every principle here is enforceable — either
by a linter, a structural test, or a convention check.

When documentation proves insufficient to prevent a recurring violation,
the rule MUST be promoted into code (lint rule or structural test). See
the Promotion Ladder section below.

## Principles

### 1. Validate at the boundary, not inline

All external inputs — CLI arguments, config files, OpenSRM manifests, API
payloads — must be validated at the entry point using schema validation or
typed parsing. Do not scatter ad-hoc field checks through business logic.

**Why:** Agents love writing `if config.get("field")` checks deep in
call chains. This produces duplicated validation, inconsistent error messages,
and fields that are "validated" in some paths but not others.

**Enforcement:** [DOCUMENTATION] — promote to lint when third violation observed.

### 2. Shared utilities over hand-rolled helpers

If a pattern appears more than twice, it belongs in a shared module under
the project's common/utils packages. Before writing any utility function,
check whether one already exists in the existing modules.

Common agent-generated duplicates to watch for:
- Duration formatting
- Label validation
- String sanitisation
- Retry/backoff logic
- Map/slice helpers

**Why:** Every fresh agent context window reinvents helpers slightly differently.
Centralising utilities keeps invariants in one place.

**Enforcement:** [DOCUMENTATION] — promote to lint when duplicate detected.

### 3. Structured logging only

All log output must use the project's structured logger (e.g., `structlog` or
the configured `logging` setup). No bare `print()` statements, `sys.stdout.write()`,
or unconfigured `logging.info()` calls in any module except CLI entrypoints
(where logging is initialised).

Field naming conventions:
- `err` or `error` for errors (not `e`, `failure`, `exc`)
- `component` for the subsystem (not `module`, `pkg`, `source`)
- `duration_ms` for timing (not `elapsed`, `time`, `took`)

**Why:** Inconsistent logging makes observability impossible. This is an
SRE project — our own observability must be exemplary.

**Enforcement:** [LINT] — see `scripts/lint/check-no-unstructured-logging.sh`

### 4. Exception handling with context at layer boundaries

Exceptions must be caught and re-raised with descriptive context at module
boundaries using `raise XError("doing X") from err` or wrapped in
domain-specific exception classes. Never use bare `except: pass` or
`except Exception: pass`. Never silently swallow exceptions except where
explicitly documented with a `# intentionally ignored: <reason>` comment.

**Why:** Agents frequently write bare `except: pass` blocks or catch-all
handlers that discard error context. Uncontextualized exceptions produce
tracebacks with no indication of what the code was trying to do.

**Enforcement:** [DOCUMENTATION] — promote to lint when pattern recurs.

### 5. Template functions for all generated output

Prometheus rules, Grafana dashboards, and any other generated configuration
must use the template system (e.g., Jinja2 templates or the project's template
module). Never construct generated
output via raw string concatenation or `fmt.Sprintf`.

**Why:** Raw string construction is the single most likely source of
correctness bugs in NthLayer. Template functions centralise escaping,
formatting, and validation.

**Enforcement:** [DOCUMENTATION] — promote to lint for Prometheus/Grafana paths.

### 6. No orphaned TODOs

Every `TODO` comment must reference a Beads issue ID:
`# TODO(bd-xxxx): description`. TODOs without issue references rot
and become invisible tech debt.

**Why:** Agents generate TODOs liberally as placeholders. Without tracking,
they accumulate indefinitely.

**Enforcement:** [LINT] — see `scripts/lint/no-orphan-todos.sh`

## Promotion Ladder

Rules progress through enforcement levels as violations recur:

1. **DOCUMENTATION** — Rule exists in this document and in `docs/conventions.md`.
   Agents should follow it. Violations caught during human review.

2. **CONVENTION CHECK** — Rule checked by the GC sweep agent
   (`/project:gc-sweep`). Violations produce refactoring PRs.

3. **LINT** — Rule enforced by a script in `scripts/lint/`. Violations fail
   CI and block PRs. Lint error messages include remediation instructions
   written for agent consumption.

4. **STRUCTURAL TEST** — Rule enforced by a test in the test suite. Hardest
   to bypass, appropriate for architectural invariants.

When you observe a violation of a DOCUMENTATION-level rule for the third time,
it is time to promote it. Create a Beads issue: `[PROMOTE] <rule name> to <next level>`.

## Adding New Principles

A golden principle must be:
- **Opinionated**: It makes a clear choice. "Prefer X over Y", not "consider X".
- **Mechanical**: It can be checked without human judgement.
- **Justified**: The "Why" section explains the real-world failure mode.
- **Enforceable**: It has a clear path to code-level enforcement.

If a rule requires human judgement to evaluate, it is a convention, not a
golden principle. Put it in `docs/conventions.md` instead.
```

---

## Step 2: Restructure CLAUDE.md

The current CLAUDE.md should be restructured as a **table of contents** — roughly 100 lines that serve as a map with pointers to deeper sources of truth in `docs/`, `specs/`, and `plans/`.

### Instructions

1. Read the current CLAUDE.md in its entirety
2. Identify content that belongs in dedicated docs files:
   - Architecture/package descriptions → `docs/architecture.md`
   - Coding conventions and style rules → `docs/conventions.md`
   - Testing patterns and commands → `docs/testing.md`
   - Golden principles (already created in Step 1)
3. Create those `docs/` files with the extracted content
4. Rewrite CLAUDE.md as a concise routing document

### Target CLAUDE.md structure

The restructured CLAUDE.md should follow this template. Adapt section contents to match what actually exists in the NthLayer codebase — do not invent architecture or conventions that don't exist. If a section would be empty, include the heading with a `TODO: document this` note.

```markdown
# NthLayer

[One-sentence project description from existing CLAUDE.md]

## Quick Reference

- **Language:** Python
- **Build:** [detect from codebase — e.g., `pip install -e .` or `poetry install`]
- **Test:** [detect from codebase — e.g., `pytest` or `python -m pytest`]
- **Lint:** [detect from codebase — e.g., `ruff check .`, plus `./scripts/lint/run-all.sh`]

## Documentation Map

| What | Where |
|------|-------|
| Architecture & package layout | `docs/architecture.md` |
| Coding conventions | `docs/conventions.md` |
| Golden principles (mechanical rules) | `docs/golden-principles.md` |
| Testing patterns | `docs/testing.md` |
| Quality grades by package | `docs/quality.md` |
| Active specs | `specs/` |
| Execution plans | `plans/active/` |
| Completed plans | `plans/completed/` |
| Technical debt backlog | `plans/tech-debt.md` |

Read the specific doc relevant to your task. Do NOT try to load all docs at once.

## Current State

<!-- AUTO-MANAGED: current-state -->
This section is auto-managed by claude-code-auto-memory.
Do not edit manually.
<!-- /AUTO-MANAGED: current-state -->

## Key Architectural Rules

These are enforced by linters and structural tests. See `docs/golden-principles.md`
for the full list with rationale.

1. Validate inputs at the boundary, not inline
2. Use shared utilities — do not hand-roll helpers that already exist
3. Structured logging only — no bare `print()` outside CLI entrypoints
4. Handle exceptions with context at module boundaries
5. Use template system for all generated output — no raw string construction
6. Every `TODO` must reference a Beads issue ID

## Workflow

- **Task tracking:** Beads (`bd ready`, `bd list`, `bd close`)
- **Issue creation:** `./scripts/create-audit-issue.sh` for dual Beads + GitHub Issues
- **Code review:** Automated on every PR via GitHub Action
- **Codebase audit:** `/project:audit-codebase`
- **GC sweep:** `/project:gc-sweep` (entropy cleanup)
- **Doc gardening:** `/project:doc-garden`
- **Spec to tasks:** `/project:spec-to-beads <spec-file>`

## Commit Messages

Format: `<type>: <description> (<bead-id>)`

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `lint`

When fixing a GitHub Issue: `fix: <description> (<bead-id>, closes #<number>)`
```

### Critical rules for this step

- **Do not delete the existing CLAUDE.md and start fresh.** Read it, extract content to docs files, then rewrite in place.
- **Preserve any auto-managed sections** (from claude-code-auto-memory) by keeping the marker comments.
- **Preserve any existing `.claude/settings.json` hooks** — the restructure is about CLAUDE.md content, not hook configuration.
- **Create `docs/` directory** if it doesn't exist. Create `docs/architecture.md`, `docs/conventions.md`, `docs/testing.md` by extracting relevant content from the existing CLAUDE.md. If the existing CLAUDE.md doesn't have content for a section, create the file with a skeleton and `TODO` markers.

---

## Step 3: Quality Grades Document

Create `docs/quality.md`. This document is both human-readable and machine-updatable — the audit and GC sweep agents update it on each run.

### File: `docs/quality.md`

```markdown
# Package Quality Grades

Last updated: [DATE — auto-updated by audit/GC agents]

## Grading Criteria

| Grade | Meaning |
|-------|---------|
| A | Test coverage >80%, docs complete, error handling complete, API stable |
| B | Test coverage >60%, docs partial, minor error handling gaps, API stable |
| C | Test coverage >40%, docs minimal, notable gaps, API evolving |
| D | Test coverage <40%, docs absent, significant gaps |
| F | Untested, undocumented, known bugs unaddressed |

## Current Grades

<!-- AUTO-MANAGED: quality-grades -->
| Package | Tests | Docs | Error Handling | API Stability | Grade | Notes |
|---------|-------|------|----------------|---------------|-------|-------|
<!-- Populated by first audit/GC run -->
<!-- /AUTO-MANAGED: quality-grades -->

## Grade History

Track grade changes to see trajectory over time.

<!-- AUTO-MANAGED: grade-history -->
| Date | Package | Change | Reason |
|------|---------|--------|--------|
<!-- Populated by audit/GC runs -->
<!-- /AUTO-MANAGED: grade-history -->

## Improvement Priorities

Packages graded D or F should have active Beads issues for improvement.
Run `/project:audit-codebase` to identify specific gaps.
```

### Instructions

1. Create the file as shown above
2. Run a quick assessment of the current codebase to populate initial grades:
   - For each top-level module/package, check test file existence and rough coverage
   - Check for docstrings on public classes and functions
   - Check for exception handling patterns
   - Assign initial grades based on the criteria table
3. Replace the placeholder table with actual package data
4. Commit: `docs: add quality grades document (bd-xxxx)`

---

## Step 4: Plan Tracking

Create a `plans/` directory structure for tracking execution state of specs. Plans are first-class versioned artifacts — they track what was specified, what was decided during implementation, and what deviated.

### Directory structure

```
plans/
├── README.md              # Explains the plan format and lifecycle
├── active/                # Plans currently being implemented
│   └── .gitkeep
├── completed/             # Finished plans (moved here on completion)
│   └── .gitkeep
└── tech-debt.md           # Running inventory of known technical debt
```

### File: `plans/README.md`

```markdown
# Execution Plans

Plans track the implementation lifecycle of specs. They are created automatically
by the `/project:spec-to-beads` command and updated during implementation.

## Plan Lifecycle

1. **Created** — `/project:spec-to-beads` generates a plan in `plans/active/`
2. **In Progress** — Agent updates the plan as tasks are completed
3. **Completed** — All tasks done, plan moved to `plans/completed/`

## Plan Format

Each plan is a markdown file named `YYYY-MM-DD-<slug>.md` containing:

### Metadata
- Source spec file path
- Beads epic ID
- Date created
- Status (active | completed | abandoned)

### Requirements Checklist
Extracted from the spec. Each requirement has a checkbox, the Beads issue ID
implementing it, and its current status.

### Decision Log
Decisions made during implementation that deviated from or clarified the spec.
Each entry has a date, the decision, and the rationale.

### Deviation Log
Anything that was specified but implemented differently, with explanation.
This is the primary defence against spec drift.

### Completion Summary
Added when the plan moves to `plans/completed/`. Summarises what was built,
what was deferred, and any follow-up work filed as tech debt.
```

### File: `plans/tech-debt.md`

```markdown
# Technical Debt Inventory

Known technical debt, tracked as a living document. Items here should have
corresponding Beads issues. Updated by GC sweep and audit agents.

<!-- AUTO-MANAGED: tech-debt -->
| ID | Package | Description | Severity | Beads | Filed |
|----|---------|-------------|----------|-------|-------|
<!-- Populated by audit/GC agents -->
<!-- /AUTO-MANAGED: tech-debt -->

## Debt Reduction Policy

- GC sweep agent files small refactoring PRs for low-severity items
- High-severity items get dedicated Beads issues and planned work
- Items older than 90 days without progress should be re-evaluated:
  either schedule them or accept the debt and remove from this list
```

### Modify the spec-to-beads slash command

Update `.claude/commands/spec-to-beads.md` to also create a plan artifact. **Read the existing file first**, then append the following to the instructions:

```markdown
## Plan Creation

After creating the Beads epic and all tasks, also create an execution plan:

1. Create a plan file at `plans/active/YYYY-MM-DD-<slug>.md` where:
   - YYYY-MM-DD is today's date
   - <slug> is a short kebab-case name derived from the spec title

2. The plan file must contain:

   ```markdown
   # Plan: <spec title>

   **Source spec:** <path to spec file>
   **Beads epic:** <epic bead ID>
   **Created:** <date>
   **Status:** active

   ## Requirements

   Extracted from the spec. Each requirement maps to one or more Beads issues.

   - [ ] <requirement 1> → `<bead-id>`
   - [ ] <requirement 2> → `<bead-id>`
   - [ ] <requirement 3> → `<bead-id>`, `<bead-id>`

   ## Decision Log

   | Date | Decision | Rationale |
   |------|----------|-----------|
   | | | |

   ## Deviation Log

   | Date | Specified | Implemented | Reason |
   |------|-----------|-------------|--------|
   | | | | |

   ## Completion Summary

   _To be filled when plan is completed._
   ```

3. Commit the plan file alongside the Beads epic creation.
```

### Modify the Ralph prompt

Update `.claude/ralph-prompt.md` to include plan updates during execution. **Read the existing file first**, then add to the task completion step:

```markdown
After completing each task, also:
- Update the corresponding plan in `plans/active/` — check off the requirement
- If you made a decision that clarifies or deviates from the spec, add an entry
  to the Decision Log or Deviation Log in the plan file
- Commit plan updates alongside code changes
```

---

## Step 5: GC Sweep Agent and Slash Command

### File: `.claude/agents/gc-sweep.md`

```yaml
---
name: gc-sweep
description: Entropy cleanup agent — finds convention violations, duplicated patterns, stale code, and quality regressions
tools: Read, Write, Edit, Grep, Glob, Bash
model: sonnet
---
```

```markdown
You are a codebase entropy reduction agent. Your job is to find and fix small
consistency issues that accumulate over time. You are NOT looking for bugs
(that is the code-auditor's job). You are looking for drift, duplication,
and convention violations.

## Before you start

1. Read `docs/golden-principles.md` to understand the mechanical rules
2. Read `docs/conventions.md` for coding conventions
3. Read `docs/quality.md` for current package grades

## What to scan for

### Convention violations (fix directly)
- Unstructured logging (bare `print()`, `sys.stdout.write` outside CLI entrypoints)
- TODOs without Beads issue references
- Bare `except: pass` without `# intentionally ignored` comment
- Overly broad exception handling (catching `Exception` and silently discarding)

### Duplication (consolidate)
- Utility functions that exist in multiple packages but do the same thing
- Repeated validation logic that should use a shared validator
- Duplicated constants or magic numbers

### Staleness (clean up)
- Public functions/classes with zero callers (use `grep -r` to verify)
- Config fields that are defined but never read
- Import statements that are unused (the linter may catch this, but verify)
- Commented-out code blocks longer than 5 lines

### Documentation drift (update)
- Function signatures that changed but doc comments didn't
- README sections that reference removed features or old package names
- `docs/quality.md` grades that no longer reflect reality

## How to make changes

For EACH finding, create a SEPARATE commit. Do not batch unrelated changes.

Commit format:
- `refactor: consolidate duplicate <X> helpers into <module> (bd-xxxx)`
- `chore: remove dead code in <module> (bd-xxxx)`
- `docs: update <file> to reflect current <thing>`
- `lint: add TODO issue reference for <description>`

## Quality grade updates

After scanning, update `docs/quality.md`:
- Re-evaluate grades for any package you touched
- Add entries to the Grade History table if grades changed
- Update the "Last updated" date

## Rules

- Make minimal, surgical changes. Each commit should be reviewable in under a minute.
- Do NOT refactor working code for style preferences. Only fix convention violations
  documented in `docs/golden-principles.md` or `docs/conventions.md`.
- Do NOT add features, change behaviour, or modify tests (unless a test is testing
  removed dead code).
- If you find something that looks like a bug, do NOT fix it. File it with
  `./scripts/create-audit-issue.sh` instead. Bugs are the auditor's domain.
- If you find a golden principle being violated for the third+ time and it's still
  at DOCUMENTATION level, note it in your summary as a promotion candidate.
```

### File: `.claude/commands/gc-sweep.md`

```markdown
Run an entropy cleanup sweep using the gc-sweep subagent.

## Instructions

1. Create a new branch for the sweep:
   ```bash
   git checkout -b gc/sweep-$(date +%Y%m%d)
   ```

2. Invoke the gc-sweep subagent to scan the codebase. Target these directories:
   - src/
   - nthlayer/ (or whatever the main package directory is)
   - scripts/
   - docs/

   Skip: venv/, .venv/, __pycache__/, .beads/, node_modules/, dist/, build/, test fixtures, generated files

3. The subagent will make changes directly, creating one commit per finding.

4. After the sweep completes, create a summary. Print:

   ```
   ## GC Sweep Summary — <date>

   ### Changes Made
   | # | Type | File | Description | Commit |
   |---|------|------|-------------|--------|
   | 1 | refactor | nthlayer/utils/labels.py | Consolidated duplicate validators | abc1234 |
   | 2 | chore | nthlayer/api/old.py | Removed dead code | def5678 |

   ### Promotion Candidates
   Rules that were violated 3+ times and should be promoted to the next enforcement level:
   - [ ] <rule name>: <current level> → <proposed level> — <evidence>

   ### Quality Grade Changes
   | Package | Previous | Current | Reason |
   |---------|----------|---------|--------|

   ### Bugs Found (filed, not fixed)
   | # | Title | Beads | GH |
   |---|-------|-------|----|
   ```

5. If the sweep produced changes, open a PR:
   ```bash
   git push origin gc/sweep-$(date +%Y%m%d)
   gh pr create \
     --title "GC sweep $(date +%Y-%m-%d)" \
     --body "Entropy cleanup. See commit messages for individual changes." \
     --label "chore,gc-sweep"
   ```

6. If no issues were found, say so and delete the branch:
   ```bash
   git checkout main
   git branch -D gc/sweep-$(date +%Y%m%d)
   ```

## Notes

- The GC sweep agent CAN write to files (unlike the read-only code auditor)
- Each change must be a separate, minimal commit
- Bugs found during sweep are filed via `./scripts/create-audit-issue.sh`, not fixed
- Run this after major Ralph loop sessions or weekly as maintenance
```

### Create GitHub label

```bash
gh label create gc-sweep --description "Automated entropy cleanup" --color "0E8A16" 2>/dev/null || true
```

---

## Step 6: Doc-Gardening Slash Command

This is a separate slash command (not a mode flag on the audit) because its scope and output are different — it produces documentation PRs, not issue filings.

### File: `.claude/agents/doc-gardener.md`

```yaml
---
name: doc-gardener
description: Documentation freshness agent — finds stale, missing, or incorrect documentation
tools: Read, Write, Edit, Grep, Glob
disallowedTools: Bash
model: sonnet
---
```

```markdown
You are a documentation quality agent. Your job is to ensure that documentation
accurately reflects the current state of the codebase.

## Before you start

1. Read `docs/` directory listing to understand what documentation exists
2. Read CLAUDE.md to understand the documentation map

## What to check

### Accuracy
- Do function/method signatures in docs match actual code?
- Do documented CLI flags/options match what the code actually accepts?
- Do documented config fields match the actual config struct/schema?
- Do architecture descriptions match current package layout?
- Do example commands in docs actually work?

### Completeness
- Are all public functions/classes documented with docstrings?
- Are all modules represented in `docs/architecture.md`?
- Do all `docs/` files referenced in CLAUDE.md actually exist?
- Are there packages with no documentation at all?

### Freshness
- Are there references to removed features, old package names, or deprecated APIs?
- Are there version numbers, dates, or "current" references that are stale?
- Do links in documentation point to files that still exist?

### Cross-reference integrity
- Does every file in `docs/` get referenced from CLAUDE.md?
- Do internal doc links (e.g., "see docs/conventions.md#error-handling") resolve?
- Are Beads issue references in TODOs still open? (Check with `bd show <id>`)

## Output format

For each finding, output:

```
### [CATEGORY] Brief description

**File:** path/to/doc.md
**Lines:** 42-58

**Current content:**
> The quoted text that is incorrect or stale

**Suggested fix:**
> The corrected text

**Evidence:**
How you verified this is actually wrong (e.g., "function signature in nthlayer/validator.py:42
shows `def validate(ctx: Context, input: str)` but docs say
`def validate(input: str)`")
```

## Rules

- Only flag things you can VERIFY are wrong by checking the actual code
- Do not flag style preferences in documentation
- Do not rewrite documentation for "improvement" — only fix inaccuracies
- If you can't verify whether something is wrong, skip it
```

### File: `.claude/commands/doc-garden.md`

```markdown
Run a documentation freshness sweep using the doc-gardener subagent.

## Instructions

1. Create a new branch:
   ```bash
   git checkout -b docs/garden-$(date +%Y%m%d)
   ```

2. Invoke the doc-gardener subagent to scan documentation against the codebase.

3. For each finding that the subagent identifies:
   - If the fix is straightforward (wrong function signature, stale reference,
     broken link), apply the fix directly and commit:
     `docs: fix <description>`
   - If the fix requires understanding intent (e.g., a whole section is outdated
     and it's unclear what the current behaviour should be), file a Beads issue
     instead:
     ```bash
     bd create "[DOCS] <description>" -t task -p 3
     ```

4. After the sweep, print a summary:

   ```
   ## Doc Garden Summary — <date>

   ### Fixes Applied
   | # | File | Description | Commit |
   |---|------|-------------|--------|

   ### Issues Filed (needs human judgement)
   | # | File | Description | Beads |
   |---|------|-------------|-------|

   ### Documentation Coverage
   | Area | Status |
   |------|--------|
   | CLAUDE.md → docs/ links | All valid / X broken |
   | Public function/class docstrings | X% coverage |
   | Module-level docs | X of Y modules documented |
   ```

5. If changes were made, open a PR:
   ```bash
   git push origin docs/garden-$(date +%Y%m%d)
   gh pr create \
     --title "Doc garden $(date +%Y-%m-%d)" \
     --body "Documentation freshness fixes. See commit messages for details." \
     --label "docs"
   ```

6. If nothing needed fixing, clean up:
   ```bash
   git checkout main
   git branch -D docs/garden-$(date +%Y%m%d)
   ```
```

---

## Step 7: Custom Linter Rules

Create `scripts/lint/` with an initial set of linter scripts. Each script is a standalone executable that:
- Exits 0 if no violations found
- Exits 1 if violations found
- Prints agent-readable error messages with file, line, and remediation instructions
- Can be run independently or via `scripts/lint/run-all.sh`

### File: `scripts/lint/run-all.sh`

```bash
#!/usr/bin/env bash
set -uo pipefail

# Run all custom lint rules. Returns non-zero if any rule fails.
# Designed to be called from CI and from Claude Code hooks.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$SCRIPT_DIR")")"
EXIT_CODE=0
FAILURES=()

for script in "$SCRIPT_DIR"/check-*.sh; do
  [ -f "$script" ] || continue
  name=$(basename "$script" .sh)
  if ! bash "$script" "$REPO_ROOT"; then
    EXIT_CODE=1
    FAILURES+=("$name")
  fi
done

if [ $EXIT_CODE -ne 0 ]; then
  echo ""
  echo "=== LINT FAILURES ==="
  for f in "${FAILURES[@]}"; do
    echo "  ✗ $f"
  done
  echo ""
  echo "Fix these issues before committing. See docs/golden-principles.md for rationale."
fi

exit $EXIT_CODE
```

### File: `scripts/lint/check-no-unstructured-logging.sh`

```bash
#!/usr/bin/env bash
set -uo pipefail

# Golden Principle #3: Structured logging only
# No bare print(), sys.stdout.write(), or unconfigured logging calls
# outside CLI entrypoints.

REPO_ROOT="${1:-.}"
VIOLATIONS=0

# Exclude test files, CLI entrypoints, and virtual environments
EXCLUDE_DIRS="venv|\.venv|__pycache__|\.beads|node_modules|dist|build"
EXCLUDE_FILES="cli\.py|__main__\.py|conftest\.py"

while IFS= read -r file; do
  [ -z "$file" ] && continue

  # Skip CLI entrypoints
  if echo "$file" | grep -qE "$EXCLUDE_FILES"; then
    continue
  fi

  # Check for bare print() statements
  while IFS=: read -r line_num content; do
    # Skip comments and docstrings
    stripped=$(echo "$content" | sed 's/^[[:space:]]*//')
    if echo "$stripped" | grep -qE '^#'; then
      continue
    fi
    echo "ERROR: Unstructured logging at $file:$line_num"
    echo "  Found: $stripped"
    echo "  Fix: Use the project's structured logger instead of print()."
    echo "       See docs/golden-principles.md#3-structured-logging-only"
    echo ""
    VIOLATIONS=$((VIOLATIONS + 1))
  done < <(grep -n -E '^\s*(print\(|sys\.stdout\.write|sys\.stderr\.write)' "$file" 2>/dev/null || true)

done < <(find "$REPO_ROOT" -name "*.py" -not -path "*test*" 2>/dev/null | grep -v -E "$EXCLUDE_DIRS" || true)

if [ $VIOLATIONS -gt 0 ]; then
  echo "Found $VIOLATIONS unstructured logging violation(s)."
  echo "All logging must use the project's structured logger. No bare print() calls."
  echo "See docs/golden-principles.md#3-structured-logging-only for rationale."
  exit 1
fi

exit 0
```

### File: `scripts/lint/check-no-orphan-todos.sh`

```bash
#!/usr/bin/env bash
set -uo pipefail

# Golden Principle #6: No orphaned TODOs
# Every TODO must reference a Beads issue ID: TODO(bd-xxxx)

REPO_ROOT="${1:-.}"
VIOLATIONS=0

FILE_EXTS=("*.py" "*.yaml" "*.yml" "*.toml" "*.md")
EXCLUDE_DIRS="venv|\.venv|__pycache__|\.beads|node_modules|dist|build"

for ext in "${FILE_EXTS[@]}"; do
  while IFS= read -r file; do
    [ -z "$file" ] && continue
    while IFS=: read -r line_num content; do
      # Check if TODO has a beads reference
      if ! echo "$content" | grep -qE 'TODO\(bd-[a-z0-9]+\)'; then
        echo "ERROR: Orphaned TODO at $file:$line_num"
        echo "  Found: $(echo "$content" | sed 's/^[[:space:]]*//')"
        echo "  Fix: Add a Beads issue reference: # TODO(bd-xxxx): description"
        echo "       Create one with: bd create \"<description>\" -t task -p 3"
        echo "       See docs/golden-principles.md#6-no-orphaned-todos"
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
      fi
    done < <(grep -n -E '(TODO|FIXME|HACK|XXX)' "$file" 2>/dev/null | grep -v 'TODO(bd-' || true)
  done < <(find "$REPO_ROOT" -name "$ext" -not -path "*test*" 2>/dev/null | grep -v -E "$EXCLUDE_DIRS" || true)
done

if [ $VIOLATIONS -gt 0 ]; then
  echo "Found $VIOLATIONS orphaned TODO(s) without Beads issue references."
  echo "Every TODO/FIXME/HACK/XXX must reference a Beads issue: # TODO(bd-xxxx)"
  echo "See docs/golden-principles.md#6-no-orphaned-todos for rationale."
  exit 1
fi

exit 0
```

### File: `scripts/lint/check-exception-handling.sh`

```bash
#!/usr/bin/env bash
set -uo pipefail

# Golden Principle #4: Exception handling with context
# Detects bare except:pass and overly broad exception swallowing in Python.

REPO_ROOT="${1:-.}"
VIOLATIONS=0
EXCLUDE_DIRS="venv|\.venv|__pycache__|\.beads|node_modules|dist|build"

while IFS= read -r file; do
  [ -z "$file" ] && continue

  # Pattern 1: bare "except:" (catches everything including KeyboardInterrupt)
  while IFS=: read -r line_num content; do
    stripped=$(echo "$content" | sed 's/^[[:space:]]*//')
    if echo "$stripped" | grep -qE '^except\s*:'; then
      echo "ERROR: Bare except clause at $file:$line_num"
      echo "  Found: $stripped"
      echo "  Fix: Catch a specific exception type. Use 'except Exception as e:' at minimum."
      echo "       See docs/golden-principles.md#4-exception-handling-with-context"
      echo ""
      VIOLATIONS=$((VIOLATIONS + 1))
    fi
  done < <(grep -n -E '^\s*except\s*:' "$file" 2>/dev/null || true)

  # Pattern 2: "except Exception: pass" or "except: pass" without comment
  while IFS=: read -r line_num content; do
    # Read next non-blank line to check for pass
    next_line=$(sed -n "$((line_num + 1))p" "$file" 2>/dev/null | sed 's/^[[:space:]]*//')
    if echo "$next_line" | grep -qE '^pass\s*(#.*)?$'; then
      # Check if there's an "intentionally ignored" comment
      if ! echo "$next_line" | grep -q "intentionally ignored"; then
        echo "WARNING: Silently swallowed exception at $file:$line_num"
        echo "  Found: $(echo "$content" | sed 's/^[[:space:]]*//')  →  $next_line"
        echo "  Fix: Handle the exception, or add '# intentionally ignored: <reason>' comment."
        echo "       See docs/golden-principles.md#4-exception-handling-with-context"
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
      fi
    fi
  done < <(grep -n -E '^\s*except\s' "$file" 2>/dev/null || true)

done < <(find "$REPO_ROOT" -name "*.py" -not -path "*test*" 2>/dev/null | grep -v -E "$EXCLUDE_DIRS" || true)

if [ $VIOLATIONS -gt 0 ]; then
  echo "Found $VIOLATIONS exception handling violation(s)."
  echo "Exceptions must be caught specifically and handled or re-raised with context."
  echo "See docs/golden-principles.md#4-exception-handling-with-context for rationale."
  exit 1
fi

exit 0
```

### Make all scripts executable

```bash
chmod +x scripts/lint/run-all.sh
chmod +x scripts/lint/check-no-unstructured-logging.sh
chmod +x scripts/lint/check-no-orphan-todos.sh
chmod +x scripts/lint/check-exception-handling.sh
```

### Integration

After creating the lint scripts, update the following:

1. **CLAUDE.md** — the Quick Reference section should list `./scripts/lint/run-all.sh` as a lint command

2. **`.claude/hooks/stop-check.sh`** (if it exists from the workflow setup spec) — optionally add a lint check before allowing session end. This is aggressive and may be annoying during early development; enable when the lint rules are stable:
   ```bash
   # Optional: uncomment when lint rules are stable
   # if ! ./scripts/lint/run-all.sh >/dev/null 2>&1; then
   #   echo "Lint violations detected. Run ./scripts/lint/run-all.sh to see details."
   #   exit 2
   # fi
   ```

3. **CI workflow** — if you have a CI pipeline, add `./scripts/lint/run-all.sh` as a step. If not, the PR review GitHub Action will catch violations because the lint rules are referenced in CLAUDE.md and the reviewer will flag code that violates them.

---

## Step 8: Wire Everything Together

### Update `.claude/settings.json`

**Read the existing file first.** Merge these additions into the existing hooks configuration — do not replace the file.

The SessionStart hook should be updated to also show available commands:

```bash
echo ""
echo "=== Available commands ==="
echo "/project:spec-to-beads <spec>  — Decompose spec into Beads tasks + plan"
echo "/project:audit-codebase        — Find bugs, file as Beads + GH Issues"
echo "/project:gc-sweep              — Entropy cleanup sweep"
echo "/project:doc-garden            — Documentation freshness check"
echo ""
```

### Create missing GitHub labels

```bash
gh label create gc-sweep --description "Automated entropy cleanup" --color "0E8A16" 2>/dev/null || true
gh label create docs --description "Documentation changes" --color "0075ca" 2>/dev/null || true
gh label create promotion --description "Golden principle promotion candidate" --color "F9D0C4" 2>/dev/null || true
```

---

## Execution Order

1. **Create** `docs/golden-principles.md` (Step 1)
2. **Restructure** CLAUDE.md and create `docs/` files (Step 2)
   - Read existing CLAUDE.md
   - Create `docs/architecture.md`, `docs/conventions.md`, `docs/testing.md`
   - Rewrite CLAUDE.md as table of contents
3. **Create** `docs/quality.md` with initial grades from codebase scan (Step 3)
4. **Create** `plans/` directory structure and files (Step 4)
   - Create `plans/README.md`, `plans/tech-debt.md`
   - Update `.claude/commands/spec-to-beads.md` with plan creation
   - Update `.claude/ralph-prompt.md` with plan update instructions
5. **Create** GC sweep agent and slash command (Step 5)
6. **Create** doc-gardening agent and slash command (Step 6)
7. **Create** `scripts/lint/` directory and lint scripts (Step 7)
   - Create all scripts
   - Make executable
   - Test each script against the codebase
   - Update CLAUDE.md Quick Reference with lint command
8. **Wire** everything together (Step 8)
   - Update SessionStart hook
   - Create GitHub labels
9. **Verify** everything works:
   - Run `./scripts/lint/run-all.sh` — should complete without errors (fix any initial violations)
   - Run `/project:gc-sweep` in Claude Code — verify it produces a summary
   - Run `/project:doc-garden` in Claude Code — verify it finds and fixes stale docs
   - Verify CLAUDE.md is under 120 lines and all `docs/` links resolve

## Post-Setup Workflow

After implementation, the recurring maintenance cadence is:

| Frequency | Action | Command |
|-----------|--------|---------|
| Every PR | Automated code review | GitHub Action (automatic) |
| After each Ralph loop | GC sweep | `/project:gc-sweep` |
| Weekly | Codebase audit | `/project:audit-codebase` |
| Weekly | Doc gardening | `/project:doc-garden` |
| On violation recurrence | Promote golden principle | Manual — add lint rule to `scripts/lint/` |
| After quality changes | Update grades | Auto-updated by audit/GC agents |

The system gets smarter over time:
- Review comments → convention documentation → lint rules → structural tests
- Each promotion reduces future human attention cost permanently
- Quality grades track trajectory, making improvement (or regression) visible
