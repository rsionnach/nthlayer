# NthLayer Autonomous Development Loop

You are working on the NthLayer project. Your task execution follows this exact cycle:

## Step 1: Orient
- Read CLAUDE.md for project context and conventions
- Run `bd ready --json` to find the highest-priority unblocked task
- If no tasks are ready, output "RALPH_COMPLETE" and stop

## Step 2: Claim
- Run `bd update <task-id> --status in_progress`
- Read the task description, notes, and any linked spec files

## Step 3: Implement
- Implement the task following all conventions in CLAUDE.md
- Write or update tests for any changed functionality
- Run the project's test suite to verify nothing is broken

## Step 4: Verify
- Run tests: ensure all pass
- Run linting/formatting if configured
- If tests fail, fix the issues before proceeding

## Step 5: Complete
- Run `bd update <task-id> --status closed`
- Commit with a descriptive message referencing the bead ID: `git commit -m "feat: <description> [<bead-id>]"`
- If you discovered new work during implementation, file it: `bd create "<new-task>" --type task --priority 2`
- Update the corresponding plan in `plans/active/` — check off the requirement
- If you made a decision that clarifies or deviates from the spec, add an entry
  to the Decision Log or Deviation Log in the plan file
- Commit plan updates alongside code changes

## Step 6: Continue or finish
- Run `bd ready --json` again
- If more tasks exist, return to Step 2
- If no tasks remain, run `git push`, then output "RALPH_COMPLETE"

## Rules
- Never skip tests
- Never mark a task closed if tests are failing
- If stuck on a task for more than 3 attempts, file a bug bead and move to the next ready task
- Always commit after each completed task — small, atomic commits
- The completion promise is: RALPH_COMPLETE
