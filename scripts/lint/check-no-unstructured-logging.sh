#!/usr/bin/env bash
set -uo pipefail

# Golden Principle #3: Structured logging only
# No bare print(), sys.stdout.write(), or unconfigured logging calls
# outside CLI entrypoints.

REPO_ROOT="${1:-.}"
VIOLATIONS=0

# Exclude test files, CLI entrypoints, and virtual environments
EXCLUDE_DIRS="venv|\.venv|__pycache__|\.beads|node_modules|dist|build"
EXCLUDE_FILES="cli\.py|__main__\.py|conftest\.py"

while IFS= read -r file; do
  [ -z "$file" ] && continue

  # Skip CLI entrypoints
  if echo "$file" | grep -qE "$EXCLUDE_FILES"; then
    continue
  fi

  # Check for bare print() statements
  while IFS=: read -r line_num content; do
    # Skip comments and docstrings
    stripped=$(echo "$content" | sed 's/^[[:space:]]*//')
    if echo "$stripped" | grep -qE '^#'; then
      continue
    fi
    echo "ERROR: Unstructured logging at $file:$line_num"
    echo "  Found: $stripped"
    echo "  Fix: Use the project's structured logger instead of print()."
    echo "       See docs/golden-principles.md#3-structured-logging-only"
    echo ""
    VIOLATIONS=$((VIOLATIONS + 1))
  done < <(grep -n -E '^\s*(print\(|sys\.stdout\.write|sys\.stderr\.write)' "$file" 2>/dev/null || true)

done < <(find "$REPO_ROOT" -name "*.py" -not -path "*test*" 2>/dev/null | grep -v -E "$EXCLUDE_DIRS" || true)

if [ $VIOLATIONS -gt 0 ]; then
  echo "Found $VIOLATIONS unstructured logging violation(s)."
  echo "All logging must use the project's structured logger. No bare print() calls."
  echo "See docs/golden-principles.md#3-structured-logging-only for rationale."
  exit 1
fi

exit 0
