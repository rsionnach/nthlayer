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
