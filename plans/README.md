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
