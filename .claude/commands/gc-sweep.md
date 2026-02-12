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
