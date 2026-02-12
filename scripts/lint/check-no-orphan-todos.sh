#!/usr/bin/env bash
set -uo pipefail

# Golden Principle #6: No orphaned TODOs
# Every TODO must reference a Beads issue ID: TODO(bd-xxxx)

REPO_ROOT="${1:-.}"
VIOLATIONS=0

FILE_EXTS=("*.py" "*.yaml" "*.yml" "*.toml" "*.md")
EXCLUDE_DIRS="venv|\.venv|__pycache__|\.beads|node_modules|dist|build"

for ext in "${FILE_EXTS[@]}"; do
  while IFS= read -r file; do
    [ -z "$file" ] && continue
    while IFS=: read -r line_num content; do
      # Check if TODO has a beads reference
      if ! echo "$content" | grep -qE 'TODO\(bd-[a-z0-9]+\)'; then
        echo "ERROR: Orphaned TODO at $file:$line_num"
        echo "  Found: $(echo "$content" | sed 's/^[[:space:]]*//')"
        echo "  Fix: Add a Beads issue reference: # TODO(bd-xxxx): description"
        echo "       Create one with: bd create \"<description>\" -t task -p 3"
        echo "       See docs/golden-principles.md#6-no-orphaned-todos"
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
      fi
    done < <(grep -n -E '(TODO|FIXME|HACK|XXX)' "$file" 2>/dev/null | grep -v 'TODO(bd-' || true)
  done < <(find "$REPO_ROOT" -name "$ext" -not -path "*test*" 2>/dev/null | grep -v -E "$EXCLUDE_DIRS" || true)
done

if [ $VIOLATIONS -gt 0 ]; then
  echo "Found $VIOLATIONS orphaned TODO(s) without Beads issue references."
  echo "Every TODO/FIXME/HACK/XXX must reference a Beads issue: # TODO(bd-xxxx)"
  echo "See docs/golden-principles.md#6-no-orphaned-todos for rationale."
  exit 1
fi

exit 0
