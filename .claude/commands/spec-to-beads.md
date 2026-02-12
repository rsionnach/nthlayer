---
description: Decompose a specification into Beads issues with dependency tracking
allowed-tools: Bash, Read, Write, Task
---

# Spec-to-Beads: $ARGUMENTS

Read the specification file provided in $ARGUMENTS (e.g., `/spec-to-beads specs/feature-x.md`).

## Instructions

### Phase 1: Analyse the spec
1. Read the entire spec file
2. Identify:
   - The overall feature/epic name
   - Discrete implementation tasks (aim for tasks that take 15-60 minutes each)
   - Dependencies between tasks (what must be done before what)
   - Acceptance criteria for each task
   - Any design decisions or constraints noted in the spec

### Phase 2: Create the epic
1. Create a Beads epic for the overall feature:
   ```
   bd create "<epic-name>" --type epic --priority 1 --description "<one-line summary from spec>"
   ```
2. Note the epic ID returned

### Phase 3: Create tasks with dependencies
For each task identified, create a Beads issue:
```
bd create "<task-title>" --type task --priority <1-3> --description "<what to implement>" --notes "Spec: $ARGUMENTS | Acceptance: <criteria>"
```

Then add dependency links:
```
bd update <task-id> --blocked-by <dependency-id>
```

Link each task to the epic:
```
bd update <task-id> --parent <epic-id>
```

### Phase 4: Verify
1. Run `bd list --epic <epic-id>` to show all created tasks
2. Run `bd ready` to confirm the dependency graph is valid and the first tasks are unblocked
3. Present a summary table:
   - Task ID | Title | Priority | Blocked by | Status

### Rules
- Tasks should be atomic — one clear deliverable per task
- Always set `--priority` (1 = must have, 2 = should have, 3 = nice to have)
- Include the spec file path in the `--notes` field of every task for traceability
- If the spec references other specs or ADRs, note those in the task description
- Do NOT begin implementation — this command only creates the task graph

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
