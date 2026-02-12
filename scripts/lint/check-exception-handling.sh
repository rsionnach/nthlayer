#!/usr/bin/env bash
set -uo pipefail

# Golden Principle #4: Exception handling with context
# Detects bare except:pass and overly broad exception swallowing in Python.

REPO_ROOT="${1:-.}"
VIOLATIONS=0
EXCLUDE_DIRS="venv|\.venv|__pycache__|\.beads|node_modules|dist|build"

while IFS= read -r file; do
  [ -z "$file" ] && continue

  # Pattern 1: bare "except:" (catches everything including KeyboardInterrupt)
  while IFS=: read -r line_num content; do
    stripped=$(echo "$content" | sed 's/^[[:space:]]*//')
    if echo "$stripped" | grep -qE '^except\s*:'; then
      echo "ERROR: Bare except clause at $file:$line_num"
      echo "  Found: $stripped"
      echo "  Fix: Catch a specific exception type. Use 'except Exception as e:' at minimum."
      echo "       See docs/golden-principles.md#4-exception-handling-with-context"
      echo ""
      VIOLATIONS=$((VIOLATIONS + 1))
    fi
  done < <(grep -n -E '^\s*except\s*:' "$file" 2>/dev/null || true)

  # Pattern 2: "except Exception: pass" or "except: pass" without comment
  while IFS=: read -r line_num content; do
    # Read next non-blank line to check for pass
    next_line=$(sed -n "$((line_num + 1))p" "$file" 2>/dev/null | sed 's/^[[:space:]]*//')
    if echo "$next_line" | grep -qE '^pass\s*(#.*)?$'; then
      # Check if there's an "intentionally ignored" comment
      if ! echo "$next_line" | grep -q "intentionally ignored"; then
        echo "WARNING: Silently swallowed exception at $file:$line_num"
        echo "  Found: $(echo "$content" | sed 's/^[[:space:]]*//')  →  $next_line"
        echo "  Fix: Handle the exception, or add '# intentionally ignored: <reason>' comment."
        echo "       See docs/golden-principles.md#4-exception-handling-with-context"
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
      fi
    fi
  done < <(grep -n -E '^\s*except\s' "$file" 2>/dev/null || true)

done < <(find "$REPO_ROOT" -name "*.py" -not -path "*test*" 2>/dev/null | grep -v -E "$EXCLUDE_DIRS" || true)

if [ $VIOLATIONS -gt 0 ]; then
  echo "Found $VIOLATIONS exception handling violation(s)."
  echo "Exceptions must be caught specifically and handled or re-raised with context."
  echo "See docs/golden-principles.md#4-exception-handling-with-context for rationale."
  exit 1
fi

exit 0
