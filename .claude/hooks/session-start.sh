#!/usr/bin/env bash
set -euo pipefail

echo "## Current Beads State"
echo ""

# Show ready work
if command -v bd &>/dev/null; then
    READY=$(bd ready --json 2>/dev/null || echo "[]")
    COUNT=$(echo "$READY" | jq 'length' 2>/dev/null || echo "0")
    echo "**Ready tasks:** $COUNT"
    if [ "$COUNT" -gt 0 ]; then
        echo ""
        echo "$READY" | jq -r '.[] | "- [\(.id)] \(.title) (P\(.priority // "?"))"' 2>/dev/null || true
    fi
    echo ""

    # Show in-progress work
    IN_PROGRESS=$(bd list --status in_progress --json 2>/dev/null || echo "[]")
    IP_COUNT=$(echo "$IN_PROGRESS" | jq 'length' 2>/dev/null || echo "0")
    if [ "$IP_COUNT" -gt 0 ]; then
        echo "**In progress:** $IP_COUNT"
        echo "$IN_PROGRESS" | jq -r '.[] | "- [\(.id)] \(.title)"' 2>/dev/null || true
        echo ""
    fi
else
    echo "⚠ Beads (bd) not found in PATH"
    echo ""
fi

# Show recent spec changes
echo "## Recent Spec Changes"
echo ""
SPEC_CHANGES=$(git diff --name-only HEAD~10 -- specs/ docs/specs/ spec/ 2>/dev/null || echo "")
if [ -n "$SPEC_CHANGES" ]; then
    echo "$SPEC_CHANGES" | while read -r f; do echo "- $f"; done
else
    echo "No spec changes in last 10 commits."
fi
echo ""

# Show uncommitted changes as a reminder
DIRTY=$(git status --porcelain 2>/dev/null | head -10)
if [ -n "$DIRTY" ]; then
    echo "## ⚠ Uncommitted Changes"
    echo ""
    echo "$DIRTY"
    echo ""
fi

echo "## Available Commands"
echo ""
echo "/spec-to-beads <spec>  — Decompose spec into Beads tasks + plan"
echo "/audit-codebase        — Find bugs, file as Beads + GH Issues"
echo "/gc-sweep              — Entropy cleanup sweep"
echo "/doc-garden            — Documentation freshness check"
echo ""
