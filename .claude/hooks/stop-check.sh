#!/usr/bin/env bash
set -euo pipefail

ISSUES=""

# Check for uncommitted changes
if ! git diff --quiet 2>/dev/null; then
    ISSUES="${ISSUES}• You have uncommitted changes. Please commit or stash before ending the session.\n"
fi

# Check for staged but uncommitted changes
if ! git diff --cached --quiet 2>/dev/null; then
    ISSUES="${ISSUES}• You have staged changes that haven't been committed.\n"
fi

# Check if there are in-progress beads that should be updated
if command -v bd &>/dev/null; then
    IN_PROGRESS=$(bd list --status in_progress --json 2>/dev/null || echo "[]")
    IP_COUNT=$(echo "$IN_PROGRESS" | jq 'length' 2>/dev/null || echo "0")
    if [ "$IP_COUNT" -gt 0 ]; then
        ISSUES="${ISSUES}• There are $IP_COUNT in-progress beads. Update their status or file remaining work before ending.\n"
    fi
fi

# Check for unpushed commits (only if upstream is configured)
if git rev-parse --abbrev-ref --symbolic-full-name @{u} &>/dev/null; then
    UNPUSHED=$(git log @{u}.. --oneline 2>/dev/null | wc -l | tr -d ' ')
    if [ "$UNPUSHED" -gt 0 ]; then
        ISSUES="${ISSUES}• You have $UNPUSHED unpushed commit(s). Run git push before ending.\n"
    fi
fi

# Optional: uncomment when lint rules are stable
# if ! ./scripts/lint/run-all.sh >/dev/null 2>&1; then
#   ISSUES="${ISSUES}• Lint violations detected. Run ./scripts/lint/run-all.sh to see details.\n"
# fi

if [ -n "$ISSUES" ]; then
    echo "## Land the Plane 🛬" >&2
    echo "" >&2
    echo "Cannot end session — cleanup required:" >&2
    echo "" >&2
    echo -e "$ISSUES" >&2
    echo "" >&2
    echo "Please complete cleanup, then try again." >&2
    exit 2  # Blocks stop, reinjects this message
fi

# All clear
exit 0
