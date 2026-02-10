#!/usr/bin/env bash
set -euo pipefail

# create-audit-issue.sh — Create a linked Beads issue + GitHub Issue
#
# Usage:
#   ./scripts/create-audit-issue.sh \
#     --title "[AUDIT] Nil pointer in rule compiler" \
#     --body "File: src/nthlayer/cli/apply.py:142-148\n\nThe error from..." \
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
