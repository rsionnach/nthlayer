#!/usr/bin/env bash
# Demo path resolution. Sourced by demo.sh and by
# test/test_demo_paths.sh (opensrm-oey5 regression test).
#
# Uses BASH_SOURCE so the resolved paths are correct regardless of the
# sourcing shell's $0 — i.e. the test can `source demo/_paths.sh`
# directly without needing demo.sh's $0 conventions.
#
# FRONTDOOR_ROOT vs WORKSPACE_ROOT split (opensrm-ae21c26):
#   FRONTDOOR_ROOT is this repo (hosts demo/, test/, docs/).
#   WORKSPACE_ROOT is the parent dir, where sibling component repos
#   (nthlayer-core / -workers / -bench / -common) are cloned. The split
#   keeps demo.sh's `uv run --directory` lookups correct under both the
#   local sibling-repo layout and the CI checkout layout.

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTDOOR_ROOT="$(cd "$DEMO_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$FRONTDOOR_ROOT/.." && pwd)"
