#!/usr/bin/env bash
set -uo pipefail

# Run all custom lint rules. Returns non-zero if any rule fails.
# Designed to be called from CI and from Claude Code hooks.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$SCRIPT_DIR")")"
EXIT_CODE=0
FAILURES=()

for script in "$SCRIPT_DIR"/check-*.sh; do
  [ -f "$script" ] || continue
  name=$(basename "$script" .sh)
  if ! bash "$script" "$REPO_ROOT"; then
    EXIT_CODE=1
    FAILURES+=("$name")
  fi
done

if [ $EXIT_CODE -ne 0 ]; then
  echo ""
  echo "=== LINT FAILURES ==="
  for f in "${FAILURES[@]}"; do
    echo "  ✗ $f"
  done
  echo ""
  echo "Fix these issues before committing. See docs/golden-principles.md for rationale."
fi

exit $EXIT_CODE
