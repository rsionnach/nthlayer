#!/usr/bin/env bash
# eco-doctor.sh — detect stale sibling checkouts and dependency-range drift
# across the NthLayer ecosystem workspace [opensrm-8hn3].
#
# This wrapper does one thing: find an interpreter that has `tomllib`, then hand
# off to scripts/eco_doctor.py, which holds all the logic. Stock macOS python3
# is 3.9 and has no tomllib, so `python3 eco_doctor.py` fails on a default
# machine — the reason this wrapper exists rather than a shebang.
#
# Usage, from the workspace root (the directory holding the member repos):
#   eco-doctor.sh [--fetch] [repo ...]
#
# Exit codes: 0 no findings · 1 drift found · 2 usage error or no interpreter.
#
# See the module docstring in eco_doctor.py for what it checks and why each
# fact is read from the working tree or from git HEAD.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYSER="$HERE/eco_doctor.py"

[[ -f "$ANALYSER" ]] || {
    echo "eco-doctor: missing $ANALYSER" >&2
    exit 2
}

# Ordered by preference: whatever `python3` already is, if new enough, then the
# usual homebrew names, then uv's managed interpreter. uv last because it may
# download on first use, and a diagnostic tool should not surprise you with that.
find_interpreter() {
    local candidate
    for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c 'import tomllib' >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

if PYTHON="$(find_interpreter)"; then
    exec "$PYTHON" "$ANALYSER" "$@"
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run --quiet --python 3.12 python "$ANALYSER" "$@"
fi

echo "eco-doctor: no interpreter with tomllib found (needs Python >= 3.11)." >&2
echo "eco-doctor: tried python3, python3.14, python3.13, python3.12," >&2
echo "eco-doctor: python3.11, then 'uv run'. Install one, or install uv." >&2
exit 2
