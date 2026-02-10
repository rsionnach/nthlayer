# NthLayer Code Review & Codebase Audit — Implementation Spec

## Overview

Two complementary systems for automated code quality enforcement:

1. **PR Code Review**: GitHub Action that reviews every pull request automatically
2. **Proactive Codebase Audit**: Claude Code subagent + slash command that scans the full codebase, files findings as both Beads issues and GitHub Issues

Both share a common shell function (`scripts/create-audit-issue.sh`) for dual Beads + GitHub Issue creation with cross-references.

---

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth status`)
- `bd` CLI installed and initialised in the NthLayer repo
- GitHub repo admin access (for installing the Claude GitHub App)
- Anthropic API key (for the GitHub Action)

---

## Step 1: Shared Issue Creation Function

Create `scripts/create-audit-issue.sh`. This is used by both the codebase audit slash command and can be called from any future automation that needs to file issues in both systems.

### File: `scripts/create-audit-issue.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# create-audit-issue.sh — Create a linked Beads issue + GitHub Issue
#
# Usage:
#   ./scripts/create-audit-issue.sh \
#     --title "[AUDIT] Nil pointer in rule compiler" \
#     --body "File: pkg/compiler/rules.go:142-148\n\nThe error from..." \
#     --priority 2 \
#     --labels "audit,bug"
#
# Options:
#   --title      Issue title (required)
#   --body       Issue body/description (required, supports \n for newlines)
#   --priority   Beads priority 1-4, default 2
#   --labels     Comma-separated GitHub labels, default "audit,bug"
#   --epic       Optional Beads epic ID to attach to
#   --dry-run    Print what would be created without creating

TITLE=""
BODY=""
PRIORITY=2
LABELS="audit,bug"
EPIC=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --title)    TITLE="$2";    shift 2 ;;
    --body)     BODY="$2";     shift 2 ;;
    --priority) PRIORITY="$2"; shift 2 ;;
    --labels)   LABELS="$2";   shift 2 ;;
    --epic)     EPIC="$2";     shift 2 ;;
    --dry-run)  DRY_RUN=true;  shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$TITLE" || -z "$BODY" ]]; then
  echo "Error: --title and --body are required" >&2
  exit 1
fi

if $DRY_RUN; then
  echo "=== DRY RUN ==="
  echo "Title:    $TITLE"
  echo "Priority: P$PRIORITY"
  echo "Labels:   $LABELS"
  echo "Epic:     ${EPIC:-none}"
  echo "Body:"
  echo -e "$BODY"
  exit 0
fi

# --- Create Beads issue first ---
BD_ARGS=("create" "$TITLE" "-t" "bug" "-p" "$PRIORITY")
if [[ -n "$EPIC" ]]; then
  BD_ARGS+=("--parent" "$EPIC")
fi

BD_OUTPUT=$(bd "${BD_ARGS[@]}" --json 2>/dev/null)
BD_ID=$(echo "$BD_OUTPUT" | jq -r '.id // empty')

if [[ -z "$BD_ID" ]]; then
  echo "Error: Failed to create Beads issue" >&2
  echo "$BD_OUTPUT" >&2
  exit 1
fi

# --- Create GitHub Issue with Beads cross-reference ---
GH_BODY=$(echo -e "$BODY")
GH_BODY="${GH_BODY}

---
_Beads: \`${BD_ID}\`_"

GH_URL=$(gh issue create \
  --title "$TITLE" \
  --body "$GH_BODY" \
  --label "$LABELS" 2>/dev/null)

GH_NUMBER=$(echo "$GH_URL" | grep -oE '[0-9]+$')

# --- Update Beads issue description with GitHub cross-reference ---
if [[ -n "$GH_NUMBER" ]]; then
  FULL_DESC=$(echo -e "$BODY")
  FULL_DESC="${FULL_DESC}

GH: #${GH_NUMBER}"
  bd update "$BD_ID" --description "$FULL_DESC" >/dev/null 2>&1
fi

# --- Output result as JSON for consumption by callers ---
echo "{\"bead_id\": \"${BD_ID}\", \"gh_number\": ${GH_NUMBER:-null}, \"gh_url\": \"${GH_URL:-}\"}"
```

### Setup steps

1. Create the file at `scripts/create-audit-issue.sh`
2. `chmod +x scripts/create-audit-issue.sh`
3. Ensure the `audit` and `bug` labels exist on the GitHub repo:
   ```bash
   gh label create audit --description "Automated codebase audit finding" --color "D93F0B" 2>/dev/null || true
   gh label create bug --color "d73a4a" 2>/dev/null || true
   ```
4. Test with dry run:
   ```bash
   ./scripts/create-audit-issue.sh \
     --title "[AUDIT] Test issue" \
     --body "Testing cross-reference creation" \
     --priority 3 \
     --dry-run
   ```

---

## Step 2: PR Code Review (Automated GitHub Action)

### 2a. Install the Claude GitHub App

Run this inside Claude Code in the NthLayer repo:

```
/install-github-app
```

This walks through OAuth setup, installs the Claude GitHub App on the repo, and creates a PR with a `.github/workflows/claude.yml` workflow file. **Review the PR before merging.**

Alternatively, install manually:

1. Go to https://github.com/apps/claude and install on the NthLayer repo
2. Grant permissions: Contents (read & write), Issues (read & write), Pull requests (read & write)
3. Add `ANTHROPIC_API_KEY` as a repository secret: Settings → Secrets and variables → Actions

### 2b. Create the workflow file

If `/install-github-app` didn't create it, or you want to customise it, create `.github/workflows/claude-review.yml`:

```yaml
name: Claude Code Review

on:
  pull_request:
    types: [opened, synchronize]
  issue_comment:
    types: [created]

jobs:
  review:
    if: |
      (github.event_name == 'pull_request') ||
      (github.event_name == 'issue_comment' &&
       contains(github.event.comment.body, '@claude'))
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      issues: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          model: claude-sonnet-4-5-20250929
          direct_prompt: |
            Review this pull request for bugs and security issues only.

            Focus on:
            - Logic errors that will produce wrong results
            - Unhandled errors or swallowed exceptions
            - Security issues (injection, auth bypass, secrets in code)
            - CLAUDE.md violations — read CLAUDE.md first and quote the rule being broken
            - Prometheus rule generation correctness (template misuse, label conflicts)
            - OpenSRM spec compliance if changes touch spec-related code

            Do NOT comment on:
            - Style preferences, naming opinions, or formatting
            - "Consider using X" suggestions
            - Test coverage suggestions unless a critical path is untested
            - Things that are obviously intentional design choices

            Be concise. Only flag issues where you have HIGH confidence.
            For each issue, state the file, line range, what the bug is, and why it matters.
```

### 2c. Customise review scope (optional)

To only trigger reviews on changes to source code (not docs or config):

```yaml
on:
  pull_request:
    types: [opened, synchronize]
    paths:
      - 'src/**'
      - 'pkg/**'
      - 'internal/**'
      - 'cmd/**'
      - '*.go'
      - '*.ts'
```

### 2d. Verify it works

1. Create a branch with a deliberate bug (e.g., unchecked error return)
2. Open a PR
3. Claude should comment within 1-2 minutes with findings
4. Tune the `direct_prompt` based on signal-to-noise of the first few reviews

---

## Step 3: Proactive Codebase Audit

### 3a. Create the audit subagent

Create `.claude/agents/code-auditor.md`:

```markdown
---
name: code-auditor
description: Read-only codebase audit agent — finds real bugs, not style nits
tools: Read, Grep, Glob
disallowedTools: Write, Edit, Bash
model: opus
---

You are a senior reliability engineer performing a systematic codebase audit.

## Before you start

1. Read CLAUDE.md to understand project conventions and architectural rules
2. Read any specs in specs/ to understand intended behaviour

## What to look for

Find REAL BUGS with HIGH CONFIDENCE. Categories in priority order:

1. **Logic errors**: Code that will produce wrong results regardless of inputs
2. **Error handling gaps**: Unhandled errors, swallowed exceptions, missing nil checks
3. **Security issues**: Injection vectors, auth bypass, secrets in code, unsafe deserialization
4. **CLAUDE.md violations**: Quote the exact rule being broken
5. **Spec divergence**: Behaviour that contradicts what specs/ documents say should happen
6. **Race conditions**: Unsynchronised shared state, TOCTOU bugs
7. **Dead code / unreachable paths**: Code that indicates an incomplete refactor
8. **Inconsistencies**: Related functions that should behave the same way but don't

## What NOT to flag

- Style preferences or naming opinions
- "Consider using X" suggestions
- Missing tests (unless a critical path has zero coverage)
- TODOs that are already tracked
- Performance optimisations unless there's a clear O(n²) or worse issue

## Output format

For EACH finding, output a structured block:

```
### [SEVERITY] Brief title

**File:** path/to/file.ext
**Lines:** 42-58
**Category:** (one of the categories above)

**Description:**
One paragraph explaining the actual bug and its real-world impact.

**Suggested fix direction:**
One paragraph on how to approach the fix (don't write the code).
```

Where SEVERITY is one of: CRITICAL, HIGH, MEDIUM

## Critical rules

- If you are not at least 80% confident a finding is a real bug, SKIP IT
- False positives destroy trust — when in doubt, leave it out
- Read surrounding context before flagging — what looks like a bug may be intentional
- Check if there's a comment explaining why something is done a certain way
```

### 3b. Create the audit slash command

Create `.claude/commands/audit-codebase.md`:

```markdown
Run a systematic codebase audit using the code-auditor subagent.

## Instructions

1. Invoke the code-auditor subagent to scan the codebase. Target these directories:
   - src/
   - pkg/
   - internal/
   - cmd/

   Skip: vendor/, node_modules/, .beads/, dist/, build/, test fixtures, generated files

2. Collect all findings from the subagent output.

3. For each finding, call the shared issue creation script:

   ```bash
   ./scripts/create-audit-issue.sh \
     --title "[AUDIT] <brief title from finding>" \
     --body "<full finding text including file, lines, category, description, and suggested fix direction>" \
     --priority <1 for CRITICAL, 2 for HIGH, 3 for MEDIUM> \
     --labels "audit,bug"
   ```

4. After all issues are filed, print a summary table:

   ```
   ## Audit Summary — <date>

   | # | Severity | File | Title | Beads | GH |
   |---|----------|------|-------|-------|----|
   | 1 | CRITICAL | pkg/compiler/rules.go:42 | Nil pointer on empty input | bd-xxxx | #47 |
   | 2 | HIGH | internal/api/handler.go:115 | Auth check bypassed for ... | bd-yyyy | #48 |
   ```

5. If no issues were found, say so — that's a good result, not a failure.

## Notes

- The code-auditor subagent is READ-ONLY. It cannot modify files.
- Do not create duplicate issues. Before filing, check `bd list --label audit --json` for existing open audit issues with the same file and line range.
- If an existing audit issue covers the same finding, skip it and note "already tracked as <bead-id>" in the summary.
```

### 3c. Create GitHub labels

Run once to ensure the labels exist:

```bash
gh label create audit --description "Automated codebase audit finding" --color "D93F0B" 2>/dev/null || true
gh label create security --description "Security-related issue" --color "e11d48" 2>/dev/null || true
```

### 3d. Run the audit

In Claude Code:

```
/project:audit-codebase
```

Review the summary table. Findings are now tracked in both Beads (for your Ralph loop workflow) and GitHub Issues (for public visibility and PR auto-close).

### 3e. Automate recurring audits (optional, do after manual calibration)

Once you've run 2-3 manual audits and are happy with signal quality, add a scheduled GitHub Action to run weekly:

Create `.github/workflows/codebase-audit.yml`:

```yaml
name: Weekly Codebase Audit

on:
  schedule:
    - cron: '0 6 * * 1'  # Monday 6am UTC
  workflow_dispatch:       # Manual trigger

jobs:
  audit:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install bd
        run: |
          curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash
          bd init --quiet

      - name: Install gh (already available on ubuntu-latest)
        run: gh --version

      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          model: claude-opus-4-6
          prompt: |
            Perform a full codebase audit.

            Scan src/, pkg/, internal/, cmd/ for bugs, security issues,
            and CLAUDE.md violations. Skip vendor/, node_modules/, .beads/.

            For each HIGH CONFIDENCE finding, run:
            ./scripts/create-audit-issue.sh \
              --title "[AUDIT] <title>" \
              --body "<description with file, lines, impact>" \
              --priority <1|2|3> \
              --labels "audit,bug"

            Only flag issues where confidence >= 80%.
            Check existing issues with `gh issue list --label audit` to avoid duplicates.

            End with a summary of findings count by severity.
```

**Important**: Start with manual `/project:audit-codebase` runs first. The weekly automation should only be enabled after you've tuned the prompts to minimise false positives. Every false positive filed as a GitHub Issue erodes trust in the system.

---

## Step 4: CLAUDE.md Updates

Add the following section to your CLAUDE.md so that both the PR reviewer and audit agent understand your project's rules:

```markdown
## Code Review & Audit Rules

### Architectural invariants
- [Add your project-specific rules here, e.g.:]
- Prometheus rule generation must use template functions from `pkg/templates/`
- All API handlers must validate input before processing
- Error returns must never be silently discarded
- OpenSRM spec fields must match the schema in specs/opensrm-schema.yaml

### Known intentional patterns (do not flag)
- [Add patterns that look like bugs but are intentional, e.g.:]
- pkg/legacy/compat.go uses deprecated API deliberately for backward compatibility
- Empty catch blocks in migration code are intentional (best-effort migration)
```

---

## Execution Order

1. **Create** `scripts/create-audit-issue.sh` and `chmod +x` it
2. **Create** GitHub labels (`audit`, `bug`, `security`)
3. **Run** `/install-github-app` in Claude Code for PR review setup
4. **Customise** the review workflow prompt in `.github/workflows/claude-review.yml`
5. **Test** PR review by opening a PR with a deliberate bug
6. **Create** `.claude/agents/code-auditor.md`
7. **Create** `.claude/commands/audit-codebase.md`
8. **Run** `/project:audit-codebase` manually 2-3 times, tuning prompts each time
9. **Update** CLAUDE.md with architectural invariants and known patterns
10. **Optionally** add `.github/workflows/codebase-audit.yml` for weekly automation

---

## How Fixes Flow Back

When you or a Ralph loop picks up an audit finding from `bd ready`:

1. The Beads issue description contains the GitHub Issue number (`GH: #47`)
2. Fix the code on a branch
3. Commit with: `fix: <description> (<bead-id>, closes #47)`
4. Open PR — the PR reviewer (Step 2) automatically reviews the fix
5. On merge, GitHub auto-closes `#47`
6. The Ralph loop (or you) closes the Beads issue: `bd close <bead-id>`

This creates a complete audit trail: finding → issue → fix → review → merge → close.
