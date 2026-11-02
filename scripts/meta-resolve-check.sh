#!/usr/bin/env bash
# meta-resolve-check.sh — does `pip install nthlayer` get each tier's newest
# in-range release? [opensrm-z1kq]
#
# The meta-package depends on compatible ranges, one per tier. If one tier's
# newest release needs something another tier refuses (say nthlayer-common 6
# while another caps it below 6), resolvers do not fail: they fall back to an
# older in-range release, the install succeeds, and users silently get a stale
# tier. A plain resolve stays green through that, so this compares each tier
# resolved ALONE (its newest in range) with all four resolved TOGETHER, and
# fails when any tier is held back.
#
# It also fails when a tier's newest release is OUTSIDE its range (a new
# major): the ranges then need raising and a meta release cut. Exact pins went
# stale that way for majors at a time (opensrm-z1kq), and nothing noticed.
#
# Usage, from the front-door repo root: scripts/meta-resolve-check.sh
# Needs uv. Resolves against PyPI, so a PyPI outage also fails it; read the
# output before treating a red run as a regression.
#
# Exit codes: 0 every tier at its newest in-range release; non-zero otherwise
# (a tier held back or unresolvable, no requirements read, or uv itself
# failing, e.g. the four ranges do not co-resolve or PyPI is unreachable).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY=3.11
COMPILE=(uv pip compile --quiet --no-header --no-annotate --python "$PY")

# The tier requirements, straight from the pyproject (tomllib needs 3.11).
reqs=$(uv run --quiet --isolated --no-project --python "$PY" python -c '
import tomllib
for d in tomllib.load(open("meta-package/pyproject.toml", "rb"))["project"]["dependencies"]:
    print(d)
')

if [ -z "$reqs" ]; then
    echo "no dependencies read from meta-package/pyproject.toml" >&2
    exit 1
fi

together=$("${COMPILE[@]}" meta-package/pyproject.toml)

fail=0
while IFS= read -r req; do
    [ -n "$req" ] || continue
    name=${req%%[<>=!~ ]*}
    alone=$(printf '%s\n' "$req" | "${COMPILE[@]}" - | grep -E "^${name}==" || true)
    newest=$(printf '%s\n' "$name" | "${COMPILE[@]}" - | grep -E "^${name}==" || true)
    with=$(printf '%s\n' "$together" | grep -E "^${name}==" || true)
    if [ -z "$alone" ] || [ -z "$with" ]; then
        echo "UNRESOLVED $name: alone ${alone:-none}, together ${with:-none} (unsatisfiable, or a name uv spells differently)"
        fail=1
    elif [ "$newest" != "$alone" ]; then
        echo "NEW MAJOR  $name: newest release ${newest:-none} is outside the range; raise it and release the meta-package"
        fail=1
    elif [ "$alone" != "$with" ]; then
        echo "HELD BACK  $name: newest in range $alone, installed together $with"
        fail=1
    else
        echo "ok         $with"
    fi
done <<< "$reqs"

exit "$fail"
