# opensrm-1mja Implementation Plan — `add_dependency` Integration Test

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `nthlayer/test/learn-recommendations-integration.sh` with two new sections that exercise the `add_dependency` recommendation type end-to-end via the `learn recommendations --apply-to --json` CLI surface — one happy path (APPLY_CLEAN, sigil creates missing block + appends entry) and one idempotency check (ALREADY_APPLIED, semantic dep-list unchanged on re-run).

**Architecture:** Single file modification. Reuses existing `$WORK`, trap, `GIT_CONFIG_GLOBAL=/dev/null`, and PATH stub. New scenarios get an isolated `$WORK/specs-add-dep/` subdir so they don't interact with the git-committed `fraud-detect.yaml` workspace from sections 1–6. All apply-result assertions go through `jq` against `--json` stdout; manifest assertions go through Python YAML parse for structural shape and JSON-canonicalised dep-list diff for semantic idempotency.

**Tech Stack:** Bash, `jq`, Python 3 (`yaml.safe_load`, `json.dumps`), `uv run --directory`. No new file dependencies; `python -m nthlayer_workers.learn` already provides the CLI entrypoint.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-30-1mja-add-dependency-integration-test-design.md` (committed at `nthlayer@ee0ee12`).

---

## File Structure

**Modified files:**
- `nthlayer/test/learn-recommendations-integration.sh` — append `fail()` helper near top, append `jq` preflight + sections 7 + 8 after the existing section 6 (`--pr` path).

**No new files.** No new pytest files. The integration test runs as a shell script invoked from CI / local dev / future ecosystem-wide test harnesses.

**Task ordering rationale:** Land Task 1 (Section 7 happy path + preflight + helper) first — verifies the apply path on its own, smallest reviewable diff. Land Task 2 (Section 8 idempotency) second — depends on the manifest state Task 1 produces. Task 3 is the regression sweep + R5 supervise + bead close.

---

## Task 1: `fail()` helper, `jq` preflight, and Section 7 (APPLY_CLEAN)

**Files:**
- Modify: `nthlayer/test/learn-recommendations-integration.sh` (append after line 164)

- [ ] **Step 1.1: Inspect current end-of-file**

Run:

```
cat /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/test/learn-recommendations-integration.sh | tail -10
```

Expected: ends with `SUCCESS=1` on line 164 (a bare-line directive flipping the cleanup-trap guard). Anything you add must come BEFORE the existing `SUCCESS=1` line, because that line is the file's "all assertions passed" marker.

- [ ] **Step 1.2: Move the existing `SUCCESS=1` to a final guard line**

Find the existing block at the end of the file (around lines 162–164):

```bash
echo ""
echo "All integration assertions passed."
SUCCESS=1
```

Edit so that the `SUCCESS=1` line and the final `echo` move to AFTER the new sections we'll add. Replace those 3 lines with just:

```bash
echo ""
echo "All tighten_slo + --pr assertions passed."
```

(No `SUCCESS=1` here yet — we'll re-add it as the script's last line after Section 8 lands in Task 2.)

- [ ] **Step 1.3: Add `fail()` helper near top of file**

Find the `set -euo pipefail` line (around line 14). Add a `fail()` helper immediately below it:

```bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}
```

Existing sections continue to use `|| { echo "FAIL: ..."; exit 1; }` patterns — don't refactor them. The helper is for the NEW sections only.

- [ ] **Step 1.4: Append jq preflight + Section 7 to the script**

After the existing section 6 closing (the line `echo "✓ --pr path: branch + commit + stub gh pr create OK"`), and after the moved `echo "All tighten_slo + --pr assertions passed."` line from Step 1.2, append:

```bash

# ─────────────────────────────────────────────────────────────────────────
# Sections 7-8: add_dependency apply path (opensrm-1mja)
# Verifies the [+] sigil and ALREADY_APPLIED dedup end-to-end via
# --apply-to + --json, using structured jq assertions and a Python
# YAML parse for manifest shape.
# ─────────────────────────────────────────────────────────────────────────

# Preflight: jq is required for --json apply-result assertions.
# Skip-not-fail so constrained CI environments don't block on jq absence.
command -v jq >/dev/null 2>&1 || {
  echo "SKIP: jq required for add_dependency assertions (sections 7-8)"
  SUCCESS=1
  exit 0
}

# 7. add_dependency — APPLY_CLEAN happy path
ADD_DEP_SPECS="$WORK/specs-add-dep"
mkdir -p "$ADD_DEP_SPECS"

# Minimal seed manifest with NO spec.dependencies block.
# The [+] sigil must CREATE the block AND append the entry — the
# maximally demanding APPLY_CLEAN path.
cat > "$ADD_DEP_SPECS/payments-api.yaml" <<'EOF'
# Minimal manifest for add_dependency apply testing.
# Lacks tier/type/SLO fields that real manifests would have.
# Intentional: testing apply layer in isolation, not full manifest
# schema validation.
metadata:
  name: payments-api
  team: payments-platform
spec:
  slos:
    availability:
      target: 99.9
      window: 30d
EOF

# Build plan with one add_dependency recommendation.
# All values hardcoded for deterministic test runs.
PLAN_FILE_ADD_DEP="$WORK/plan-add-dep.yaml"
uv run --directory "$WORKERS_ROOT" python <<EOF
from datetime import datetime, timezone
from pathlib import Path
from nthlayer_workers.learn.recommendations import (
    SpecRecommendation, Recommendation, compute_rec_id,
)

incident_id = "inc-add-dep-test"
rec = Recommendation(
    id=compute_rec_id(incident_id, "add_dependency", "spec.dependencies[+].svc-new"),
    service="payments-api",
    type="add_dependency",
    rationale="Integration test add_dependency recommendation",
    field="spec.dependencies[+]",
    current_value=None,
    proposed_value={"name": "svc-new", "type": "api"},
    confidence=0.5,
)
plan = SpecRecommendation(
    incident=incident_id,
    generated_by="integration-test",
    generated_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
    confidence=0.5,
    recommendations=[rec],
)
Path("$PLAN_FILE_ADD_DEP").write_text(plan.to_yaml())
EOF
echo "✓ plan-add-dep.yaml generated"

# Apply with --json (structured stdout for jq).
APPLY1_JSON="$WORK/apply1.json"
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE_ADD_DEP" \
      --apply-to "$ADD_DEP_SPECS" \
      --json > "$APPLY1_JSON"

# Apply-result assertions via jq.
[ "$(jq '.exit_code' "$APPLY1_JSON")" = "0" ] || fail "apply1 exit_code != 0"
[ "$(jq '.applied | length' "$APPLY1_JSON")" = "1" ] || fail "apply1 applied != 1"
[ "$(jq '.skipped | length' "$APPLY1_JSON")" = "0" ] || fail "apply1 skipped != 0"

# Structural manifest assertion via Python YAML parse.
# Verifies the dep exists at spec.dependencies[].{name, type} — not a
# string-pattern match (which would false-positive on comment text).
uv run --directory "$WORKERS_ROOT" python <<EOF
import yaml
from pathlib import Path
doc = yaml.safe_load(Path("$ADD_DEP_SPECS/payments-api.yaml").read_text())
deps = doc.get("spec", {}).get("dependencies", [])
matching = [d for d in deps if d.get("name") == "svc-new"]
assert len(matching) == 1, f"expected 1 matching dep, got {len(matching)}: {matching}"
assert matching[0].get("type") == "api", f"expected type=api, got {matching[0]}"
EOF
echo "✓ Section 7: add_dependency APPLY_CLEAN path"
```

- [ ] **Step 1.5: Re-add the success marker at the new end-of-file**

Append at the very end of the file:

```bash

echo ""
echo "All integration assertions passed."
SUCCESS=1
```

- [ ] **Step 1.6: Sanity-check the script syntax**

```
bash -n /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/test/learn-recommendations-integration.sh && echo "syntax OK"
```

Expected: `syntax OK`.

- [ ] **Step 1.7: Run the script end-to-end**

```
bash /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/test/learn-recommendations-integration.sh
```

Expected: all 6 existing sections pass (✓ messages for plan generation, apply, --pr) + new Section 7 (✓ Section 7: add_dependency APPLY_CLEAN path) + "All integration assertions passed."

If Section 7 fails, inspect the apply1.json that's preserved in the tmp work dir (printed in the failure trap), or the resulting `payments-api.yaml` to understand the actual shape.

- [ ] **Step 1.8: Commit**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && git add test/learn-recommendations-integration.sh && git commit -m "$(cat <<'EOF'
test(integration): add_dependency APPLY_CLEAN scenario · opensrm-1mja

Extends learn-recommendations-integration.sh with section 7: seeds a
minimal manifest with no spec.dependencies block, runs the apply
path via --apply-to --json, asserts the [+] sigil both creates the
block and appends the entry. Structural assertions only (jq on the
JSON apply-result, Python YAML parse on the manifest).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Section 8 — ALREADY_APPLIED idempotency

**Files:**
- Modify: `nthlayer/test/learn-recommendations-integration.sh` (insert before the final `SUCCESS=1` block from Task 1.5)

- [ ] **Step 2.1: Insert Section 8 before the success marker**

Find the trailing block from Task 1.5:

```bash
echo ""
echo "All integration assertions passed."
SUCCESS=1
```

Insert the following BEFORE that block:

```bash

# 8. add_dependency — ALREADY_APPLIED idempotency
# Re-run the SAME plan against the now-modified manifest. The apply
# layer must report skip (not append), and the parsed dep list must
# be semantically unchanged. Byte-identical comparison would be brittle
# to ruamel.yaml's serialisation choices; we compare the parsed Python
# list canonicalised through json.dumps(sort_keys=True) instead.

# Snapshot the dep list semantically BEFORE the idempotent re-run.
DEPS_BEFORE="$WORK/deps-before.json"
uv run --directory "$WORKERS_ROOT" python <<EOF > "$DEPS_BEFORE"
import json, yaml
from pathlib import Path
doc = yaml.safe_load(Path("$ADD_DEP_SPECS/payments-api.yaml").read_text())
print(json.dumps(doc.get("spec", {}).get("dependencies", []), sort_keys=True))
EOF

# Re-run the SAME plan against the now-modified specs dir.
APPLY2_JSON="$WORK/apply2.json"
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE_ADD_DEP" \
      --apply-to "$ADD_DEP_SPECS" \
      --json > "$APPLY2_JSON"

# Apply-result assertions: 0 applied, 1 skipped, outcome=already_applied.
[ "$(jq '.exit_code' "$APPLY2_JSON")" = "0" ] || fail "apply2 exit_code != 0"
[ "$(jq '.applied | length' "$APPLY2_JSON")" = "0" ] || fail "apply2 applied != 0"
[ "$(jq '.skipped | length' "$APPLY2_JSON")" = "1" ] || fail "apply2 skipped != 1"
[ "$(jq -r '.skipped[0].outcome' "$APPLY2_JSON")" = "already_applied" ] || \
  fail "apply2 skipped[0].outcome != already_applied"

# Semantic manifest comparison: parsed dep list unchanged.
DEPS_AFTER="$WORK/deps-after.json"
uv run --directory "$WORKERS_ROOT" python <<EOF > "$DEPS_AFTER"
import json, yaml
from pathlib import Path
doc = yaml.safe_load(Path("$ADD_DEP_SPECS/payments-api.yaml").read_text())
print(json.dumps(doc.get("spec", {}).get("dependencies", []), sort_keys=True))
EOF

diff -u "$DEPS_BEFORE" "$DEPS_AFTER" || fail "dep list changed on idempotent re-run"
echo "✓ Section 8: add_dependency ALREADY_APPLIED idempotency"
```

- [ ] **Step 2.2: Sanity-check syntax**

```
bash -n /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/test/learn-recommendations-integration.sh && echo "syntax OK"
```

Expected: `syntax OK`.

- [ ] **Step 2.3: Run the full script**

```
bash /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/test/learn-recommendations-integration.sh
```

Expected: all sections pass, ending with:

```
✓ Section 7: add_dependency APPLY_CLEAN path
✓ Section 8: add_dependency ALREADY_APPLIED idempotency

All integration assertions passed.
```

Common failure modes to debug if it fails:
- Section 8's `apply2 skipped[0].outcome` != `already_applied` → check the OutcomeKind value in `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` (should be lowercase `already_applied` per the StrEnum definition).
- Section 8's `diff -u "$DEPS_BEFORE" "$DEPS_AFTER"` reports a difference → the second apply DID mutate the manifest; the [+] sigil's dedup-on-name check in `_yaml.py` may have regressed (check `_yaml.py:classify_outcome` for the `ALREADY_APPLIED` branch).

- [ ] **Step 2.4: Commit**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && git add test/learn-recommendations-integration.sh && git commit -m "$(cat <<'EOF'
test(integration): add_dependency ALREADY_APPLIED idempotency · opensrm-1mja

Section 8: re-runs the same add_dependency plan against the now-modified
manifest from section 7. Asserts the apply layer reports skip
(outcome=already_applied) and the parsed dep list is semantically
unchanged via JSON-canonicalised comparison (not byte diff, which would
be brittle to ruamel.yaml serialisation choices).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: R5 supervise + bead close

**Files:** None modified. Verifies the bead is shippable end-to-end.

- [ ] **Step 3.1: Re-run the integration test from a clean state**

```
bash /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/test/learn-recommendations-integration.sh
```

Expected: PASS (all sections green, "All integration assertions passed.").

- [ ] **Step 3.2: Check git status across affected repos**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem && for d in nthlayer nthlayer-common nthlayer-workers; do echo "--- $d ---"; (cd $d && git status --short && git log --oneline -3); done
```

Expected: `nthlayer-common` and `nthlayer-workers` clean (no changes from this bead). `nthlayer` HEAD = Task 2 commit. Spec commit `ee0ee12` and plan commit (next step) should also be on `nthlayer`.

- [ ] **Step 3.3: Invoke /r5-supervise 1mja**

```
/r5-supervise 1mja
```

Expected: 4 sequential R5 passes. Since this bead is bash-only (no Python source change, no production logic), reviewers should focus on:
- Correctness: quote escaping, exit-on-error discipline, trap correctness, jq query syntax
- Clarity: section numbering, comment quality, variable naming
- Edge cases: jq absent (preflight covers it), partial-state cleanup (trap covers it), apply2 stderr noise from idempotent skip
- Excellence: shell-script test discipline, OutcomeKind value coupling

Expect few findings — this is additive test code, not production. R5 supervisor will close the bead on all-passes-clean.

- [ ] **Step 3.4: (If R5 supervisor doesn't auto-close) manually close the bead**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && bd close 1mja --reason "Integration test for add_dependency end-to-end. Section 7 (APPLY_CLEAN) seeds manifest with no spec.dependencies block, asserts [+] sigil creates block + appends entry. Section 8 (ALREADY_APPLIED) re-runs same plan, asserts skip + semantic dep-list unchanged. Structured jq + Python YAML parse assertions; no raw-text matching. R5 reviewed."
```

Verify:

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && bd show 1mja | head -5
```

Expected: `[● P3 · CLOSED]`.

---

## Self-Review Notes

**Spec coverage map** (every § in the spec is implemented by a numbered step):
- § 3.1 (extend script, isolated subdir) → Task 1.4 (`ADD_DEP_SPECS="$WORK/specs-add-dep"`)
- § 3.2 (two scenarios, skip DRIFT + --pr) → Task 1 (Section 7) + Task 2 (Section 8); no DRIFT/--pr coverage tasks
- § 3.3 (manifest with no spec.dependencies + inline comment) → Task 1.4 (manifest heredoc)
- § 3.4 (hardcoded stable plan values) → Task 1.4 (plan-building Python heredoc with `incident_id`, `datetime(2026, 5, 30, ...)`, `compute_rec_id` deterministic id)
- § 3.5 (jq + Python YAML parse for Section 7) → Task 1.4 (jq assertions + Python heredoc)
- § 3.6 (semantic dep-list comparison for Section 8) → Task 2.1 (DEPS_BEFORE / DEPS_AFTER JSON snapshots + `diff -u`)
- § 3.7 (jq preflight, SKIP-not-fail) → Task 1.4 (preflight at top of new block)

**Placeholder scan:** No "TBD" / "TODO" / "fill in" / "similar to" markers. Every code block contains complete shell + Python snippets ready to paste. Expected outputs are concrete.

**Type / value consistency:**
- `PLAN_FILE_ADD_DEP` used consistently in Task 1.4 (plan build + apply1) and Task 2.1 (apply2).
- `ADD_DEP_SPECS` used consistently in Task 1.4 (mkdir + manifest seed + apply1 --apply-to) and Task 2.1 (apply2 --apply-to + Python YAML parse).
- `APPLY1_JSON` and `APPLY2_JSON` distinct variables in distinct sections.
- `DEPS_BEFORE` / `DEPS_AFTER` introduced in Task 2.1, no collision with anything in Task 1.
- `OutcomeKind` value `already_applied` matches the verified lowercase StrEnum value in `recommendations.py:73` (per spec § 3.6).
- `Recommendation(field="spec.dependencies[+]", ...)` matches the verified jmy.21 contract (`recommendations.py:485`).
