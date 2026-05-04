#!/usr/bin/env bash
# verdict-feed.sh — polls core's GET /verdicts and writes the response to a feed file
# for the topology UI to consume. Replaces the legacy nthlayer-learn polling sidecar
# (opensrm-saun.5; the legacy sidecar referenced the deprecated nthlayer-learn CLI).

set -euo pipefail

CORE_URL="${CORE_URL:-http://localhost:8000}"
FEED_FILE="${FEED_FILE:-./demo-output/verdict-feed.json}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
LIMIT="${LIMIT:-20}"

mkdir -p "$(dirname "$FEED_FILE")"

# Core returns verdicts ordered created_at DESC. The topology UI reads
# `v.timestamp`; alias created_at → timestamp via jq while keeping created_at
# for forward compat. Writes go to a temp file then atomic-rename so a reader
# polling concurrently never sees a partially-written file. On any failure
# (core down, jq error, network hiccup), write an empty array so the UI's
# poll loop sees no data rather than stale data.
TMP_FILE="${FEED_FILE}.tmp"
while true; do
  if ! curl -sf --max-time 3 "${CORE_URL}/verdicts?limit=${LIMIT}" \
        | jq 'if type == "array" then map(. + {timestamp: .created_at}) else [] end' \
        > "$TMP_FILE" 2>/dev/null; then
    echo "[]" > "$TMP_FILE"
  fi
  mv "$TMP_FILE" "$FEED_FILE"
  sleep "$POLL_INTERVAL"
done
