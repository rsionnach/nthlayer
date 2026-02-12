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
