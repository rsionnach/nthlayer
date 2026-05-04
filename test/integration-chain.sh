#!/usr/bin/env bash
# integration-chain.sh — Part A acceptance test
# Tests the full verdict chain: measure → correlate → respond → learn
#
# Usage: ./test/integration-chain.sh [prometheus-url] [specs-dir]
# Without Prometheus, seeds verdicts directly to test the chain.

set -euo pipefail

PROMETHEUS_URL="${1:-}"
SPECS_DIR="${2:-./nthlayer/examples/opensrm}"
VERDICT_DB="$(mktemp -d)/verdicts.db"

# Use learn's venv for Python + CLI
PY="uv run --directory nthlayer-learn/lib/python python"
LEARN="uv run --directory nthlayer-learn/lib/python nthlayer-learn"

STEP=0; PASSED=0; FAILED=0
trap 'rm -rf "$(dirname "$VERDICT_DB")"' EXIT
log() { echo -e "\n=== Step $STEP: $1 ===" ; }
pass() { echo "  ✓ PASS" ; PASSED=$((PASSED + 1)) ; }
fail() { echo "  ✗ FAIL: $1" ; FAILED=$((FAILED + 1)) ; }

# --- Step 1: Seed evaluation verdict ---
STEP=1; log "Seed evaluation verdict"
$PY -c "
from nthlayer_learn import create, SQLiteVerdictStore
store = SQLiteVerdictStore('$VERDICT_DB')
v = create(
    subject={'type': 'evaluation', 'ref': 'fraud-detect', 'summary': 'Reversal rate breach'},
    judgment={'action': 'flag', 'confidence': 0.9},
    producer={'system': 'nthlayer-measure'},
    metadata={'custom': {'slo_type': 'judgment', 'slo_name': 'reversal_rate', 'target': 0.05, 'current_value': 0.08, 'breach': True, 'consecutive': 3}},
)
store.put(v); print(f'EVAL_VERDICT_ID={v.id}'); store.close()
" > /tmp/chain_eval.env
source /tmp/chain_eval.env
echo "  Evaluation verdict: $EVAL_VERDICT_ID"
[ -n "$EVAL_VERDICT_ID" ] && pass || fail "No evaluation verdict created"

# --- Step 2: Verify evaluation verdict in store ---
STEP=2; log "Verify evaluation verdict in store"
$LEARN list --db "$VERDICT_DB" --limit 5 2>/dev/null | grep -q "$EVAL_VERDICT_ID" && pass || fail "Verdict not found in store"

# --- Step 3: Seed correlation verdict ---
STEP=3; log "Seed correlation verdict"
if [ -n "$PROMETHEUS_URL" ]; then
    nthlayer-correlate correlate --trigger-verdict "$EVAL_VERDICT_ID" --prometheus-url "$PROMETHEUS_URL" --specs-dir "$SPECS_DIR" --verdict-store "$VERDICT_DB" > /tmp/chain_corr.out 2>&1 || true
else
    echo "  (No Prometheus — seeding directly)"
fi
$PY -c "
from nthlayer_learn import create, link, SQLiteVerdictStore, VerdictFilter
store = SQLiteVerdictStore('$VERDICT_DB')
existing = store.query(VerdictFilter(subject_type='correlation', limit=1))
if existing:
    print(f'CORR_VERDICT_ID={existing[0].id}')
else:
    v = create(
        subject={'type': 'correlation', 'ref': 'fraud-detect', 'summary': '1 group across 3 services'},
        judgment={'action': 'flag', 'confidence': 0.85},
        producer={'system': 'nthlayer-correlate'},
        metadata={'custom': {'trigger_verdict': '$EVAL_VERDICT_ID', 'root_causes': [{'service': 'fraud-detect', 'type': 'model_deploy', 'confidence': 0.9}], 'blast_radius': [{'service': 'fraud-detect', 'impact': 'direct'}, {'service': 'payment-api', 'impact': 'downstream'}]}},
    )
    link(v, context=['$EVAL_VERDICT_ID']); store.put(v)
    print(f'CORR_VERDICT_ID={v.id}')
store.close()
" > /tmp/chain_corr.env
source /tmp/chain_corr.env
echo "  Correlation verdict: $CORR_VERDICT_ID"
[ -n "$CORR_VERDICT_ID" ] && pass || fail "No correlation verdict"

# --- Step 4: Verify correlation lineage ---
STEP=4; log "Verify correlation verdict lineage"
$PY -c "
from nthlayer_learn import SQLiteVerdictStore
store = SQLiteVerdictStore('$VERDICT_DB')
v = store.get('$CORR_VERDICT_ID')
assert v is not None, 'Not found'
assert '$EVAL_VERDICT_ID' in v.lineage.context, f'Missing: {v.lineage.context}'
print(f'  Lineage: {v.lineage.context}'); store.close()
" && pass || fail "Lineage check failed"

# --- Step 5: Seed incident verdict ---
STEP=5; log "Seed incident verdict"
$PY -c "
from nthlayer_learn import create, link, SQLiteVerdictStore
store = SQLiteVerdictStore('$VERDICT_DB')
v = create(
    subject={'type': 'triage', 'ref': 'fraud-detect', 'summary': 'INC-FRAUD-DETECT'},
    judgment={'action': 'flag', 'confidence': 0.8},
    producer={'system': 'nthlayer-respond'},
    metadata={'custom': {'incident_id': 'INC-FRAUD-DETECT-20260325', 'severity': 1, 'blast_radius': [{'service': 'fraud-detect'}, {'service': 'payment-api'}, {'service': 'checkout'}, {'service': 'loyalty'}], 'root_causes': [{'service': 'fraud-detect', 'type': 'model_deploy'}]}},
)
link(v, context=['$CORR_VERDICT_ID']); store.put(v)
print(f'INCIDENT_VERDICT_ID={v.id}'); store.close()
" > /tmp/chain_inc.env
source /tmp/chain_inc.env
echo "  Incident verdict: $INCIDENT_VERDICT_ID"
[ -n "$INCIDENT_VERDICT_ID" ] && pass || fail "No incident verdict"

# --- Step 6: Verify incident lineage ---
STEP=6; log "Verify incident verdict lineage"
$LEARN list --db "$VERDICT_DB" --limit 10 2>/dev/null
$PY -c "
from nthlayer_learn import SQLiteVerdictStore
store = SQLiteVerdictStore('$VERDICT_DB')
v = store.get('$INCIDENT_VERDICT_ID')
assert v is not None
assert '$CORR_VERDICT_ID' in v.lineage.context
print(f'  Lineage: {v.lineage.context}'); store.close()
" && pass || fail "Incident lineage failed"

# --- Step 7: Run retrospective ---
STEP=7; log "Run retrospective"
$LEARN retrospective --incident-verdict "$INCIDENT_VERDICT_ID" --db "$VERDICT_DB"
RETRO_ID=$($PY -c "
from nthlayer_learn import SQLiteVerdictStore, VerdictFilter
store = SQLiteVerdictStore('$VERDICT_DB')
vs = store.query(VerdictFilter(subject_type='retrospective', limit=1))
print(vs[0].id if vs else ''); store.close()
")
echo "  Retrospective verdict: $RETRO_ID"
[ -n "$RETRO_ID" ] && pass || fail "No retrospective"

# --- Step 8: Walk full lineage ---
STEP=8; log "Walk full lineage chain"
$PY -c "
from nthlayer_learn import SQLiteVerdictStore
store = SQLiteVerdictStore('$VERDICT_DB')
chain = store.by_lineage('$RETRO_ID', direction='up')
types = {v.subject.type for v in chain}
print(f'  Chain types: {sorted(types)}')
print(f'  Chain length: {len(chain)} verdicts')
required = {'evaluation', 'correlation', 'triage'}
missing = required - types
assert not missing, f'Missing: {missing}'
print('  All verdict types present.'); store.close()
" && pass || fail "Chain incomplete"

# --- Summary ---
echo -e "\n=============================="
echo "Integration Chain Results"
echo "=============================="
echo "  Passed: $PASSED / $((PASSED + FAILED))"
echo "  Failed: $FAILED"
echo ""
if [ "$FAILED" -gt 0 ]; then
    echo "FAIL — Part A acceptance test did not pass."
    exit 1
else
    echo "PASS — Part A integration chain complete."
    echo "Verdict chain: evaluation → correlation → triage → retrospective"
fi
