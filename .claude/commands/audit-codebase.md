Run a systematic codebase audit using the code-auditor subagent.

## Instructions

1. Invoke the code-auditor subagent to scan the codebase. Target these directories:
   - `src/nthlayer/cli/`
   - `src/nthlayer/dashboards/`
   - `src/nthlayer/slos/`
   - `src/nthlayer/validation/`
   - `src/nthlayer/providers/`
   - `src/nthlayer/alerts/`
   - `src/nthlayer/discovery/`
   - `src/nthlayer/specs/`
   - `src/nthlayer/recording_rules/`
   - `src/nthlayer/orchestrator.py`
   - `scripts/`

   Skip: `__pycache__/`, `.venv/`, `generated/`, `.beads/`, `tests/`, `node_modules/`, `dist/`, `build/`

2. Collect all findings from the subagent output.

3. Before filing, deduplicate against existing audit issues:
   ```bash
   bd list --status open
   ```
   If an existing issue covers the same file and line range, skip it and note "already tracked as <bead-id>" in the summary.

4. For each new finding, call the shared issue creation script:

   ```bash
   ./scripts/create-audit-issue.sh \
     --title "[AUDIT] <brief title from finding>" \
     --body "<full finding text including file, lines, category, description, and suggested fix direction>" \
     --priority <1 for CRITICAL, 2 for HIGH, 3 for MEDIUM> \
     --labels "audit,bug"
   ```

5. After all issues are filed, print a summary table:

   ```
   ## Audit Summary — <date>

   | # | Severity | File | Title | Beads | GH |
   |---|----------|------|-------|-------|----|
   | 1 | CRITICAL | src/nthlayer/cli/apply.py:42 | Nil pointer on empty input | bd-xxxx | #47 |
   | 2 | HIGH | src/nthlayer/slos/collector.py:115 | Auth check bypassed for ... | bd-yyyy | #48 |
   ```

6. If no issues were found, say so — that's a good result, not a failure.

## Notes

- The code-auditor subagent is READ-ONLY. It cannot modify files.
- Do not create duplicate issues. Check existing open issues before filing.
- If an existing audit issue covers the same finding, skip it and note "already tracked" in the summary.
