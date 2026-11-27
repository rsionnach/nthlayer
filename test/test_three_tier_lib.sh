#!/usr/bin/env bash
# test_three_tier_lib.sh — checks of _three_tier_lib.sh that need no stack.
#
# The quiet period the three-tier scripts give workers has a floor of 0.5
# minutes (opensrm-mtxr): tt_valid_quiet_minutes must refuse anything below
# it, and anything that is not a plain decimal number.
#
# Usage: bash test/test_three_tier_lib.sh   (run by retrospective-seam.yml)
set -euo pipefail

# shellcheck source=./_three_tier_lib.sh
source "$(dirname "$0")/_three_tier_lib.sh"

failures=0
expect() {  # expect <accepted|refused> <value>
    local want="$1" value="$2" got="refused"
    if tt_valid_quiet_minutes "${value}"; then got="accepted"; fi
    if [[ "${got}" == "${want}" ]]; then
        printf '  ok    %-10s %s\n' "'${value}'" "${got}"
    else
        printf '  FAIL  %-10s %s, expected %s\n' "'${value}'" "${got}" "${want}" >&2
        failures=$(( failures + 1 ))
    fi
}

for value in 0.5 0.50 0.75 1 2.5 10; do expect accepted "${value}"; done
for value in 0.49 0.2 0 "" abc -1 1e3 "0.5 " ".5" "1."; do expect refused "${value}"; done

if (( failures > 0 )); then
    printf '%d check(s) failed\n' "${failures}" >&2
    exit 1
fi
printf 'all checks passed\n'
