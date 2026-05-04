# Phase 0: Pre-Implementation Decisions

**Date:** 2026-04-21
**Status:** Draft for review (48h review window per P0.5)

---

## P0.1: Authorization Flow End-to-End Walkthrough

**Spec:** OPENSRM-RBAC-EXTENSION-v2 §12
**Scenario:** Triage agent wants to roll back payment-service after fraud-detect correlation. Demo topology: `fraud-detect` → `payment-api` → `checkout-svc`, `order-service` → `payment-api`.

### 9-Step Trace Against Three-Tier Model

**Step 1: Agent emits action_request**

- **Owning tier:** Workers (respond module's triage agent)
- **What happens:** Triage agent determines payment-service failure correlates with recent deployment. Produces `action_request` verdict referencing `payments.rollback-deployment`.
- **API call:** `POST /verdicts` to core with `type: action_request`, `service: payment-service`, `parent_ids: [correlation_verdict_id]`
- **Failure mode:** If core API unreachable, workers retry with backoff. action_request queued in workers' local state until core accepts. Triage agent does NOT execute directly — it only proposes.
- **Fail-closed:** If workers cannot submit the action_request, the action is never proposed. No ambient execution.

**Step 2: authorise receives and evaluates (v2) / respond processes directly (v1.5)**

- **v2 owning tier:** Core (authorise module). Polls verdicts table for unprocessed action_requests.
- **v1.5 owning tier:** Workers (respond module). Respond coordinator processes the action_request itself since authorise doesn't exist yet. Uses simplified approval logic (safe-actions registry).
- **API call (v2):** Core reads from its own store. No API call — authorise is in-process.
- **Failure mode (v2):** If Regorus evaluation fails, authorise writes `denial` verdict with reason "policy evaluation error." Fail-closed: error = deny.
- **Failure mode (v1.5):** If respond's approval check fails, action is not executed. Fail-closed.

**Step 3: Policy evaluation**

- **v2:** Regorus evaluates production-tightening policy. Result: `{ allow: false, required_approvals: ["dual-human"] }`. The `no-change-freeze` precondition checks ChangeFreeze documents — finds incident-driven freeze with `rollback-deploy` in exceptions → precondition passes.
- **v1.5:** Respond checks safe-actions.yaml `requires_approval: true` for rollback action. Approval required.
- **Fail-closed:** Both paths deny by default. Approval requirement is additive, never subtractive.

**Step 4: Write pending state / create case**

- **Owning tier:** Core. authorise (v2) or respond (v1.5) writes a pending-approval record.
- **API call:** `POST /cases` to core with `kind: approval_required`, `underlying_verdict: action_request_id`, `service: payment-service`
- **Case priority logic:** Priority is NOT automatically P0. It's derived from the action's blast_radius and the triggering context:
  - `blast_radius: production` + active incident → P0
  - `blast_radius: production` + no active incident → P1
  - `blast_radius: staging` → P2
  - `blast_radius: dev | ephemeral` → P3
  - The action_request verdict's metadata carries the blast_radius; the case creator maps it. Approval-required cases for routine production changes (no incident) are P1, not P0 — P0 is reserved for incident-driven urgency.
- **Failure mode:** If case creation fails, the action_request sits unprocessed. Bench shows no case, but the action_request is in the verdict store — an operator can query it directly. No execution without approval.
- **Observability for stuck action_requests:** Core must track action_requests that don't become cases within a configurable threshold (default: 60s). A background job in core monitors the verdicts table for `type: action_request` entries with no corresponding case created within the threshold. Stuck action_requests produce a `nthlayer_stuck_action_requests` metric (Prometheus gauge, labelled by service) and, if threshold exceeded by 5x (default: 5 minutes), emit an alert-level log entry. This covers the failure mode where case creation silently fails — the action_request exists but no case is surfaced to operators.

**Step 5: Operators approve**

- **Owning tier:** Bench (Tier 3). Two operators lease the case (one at a time via atomic lease), review, and approve.
- **API calls:** `PUT /cases/{id}/lease` → `POST /verdicts` (approval verdict) → `PUT /cases/{id}/resolve`
- **Failure mode:** If bench disconnects mid-approval, lease expires after 5 minutes. Another operator can claim. Approval verdicts already submitted are not lost (they're in the verdict store). Partial approval (1 of 2) is visible — case shows "1/2 approvals received."

**Step 6: Re-evaluation with approvals**

- **v2 owning tier:** Core (authorise). Detects both approvals, re-evaluates policy. Now passes. Issues Biscuit capability token signed with Ed25519 key. Writes `capability` verdict.
- **v1.5 owning tier:** Workers (respond). Detects approval, proceeds with execution.
- **API call (v2):** Internal to core. Capability verdict written to store.
- **Failure mode (v2):** If Biscuit signing fails (key unavailable), write `denial` verdict. Fail-closed.
- **Failure mode (v1.5):** If approval not found within timeout, action remains pending.

**Step 7: Execution**

- **v2 owning tier:** Core (executor module). Picks up capability, verifies Biscuit token, dispatches to kubernetes-rollout binding.
- **v1.5 owning tier:** Workers (respond module). Executes via safe-actions webhook dispatch.
- **API call (v2):** Core dispatches webhook/k8s API externally. Writes `execution` verdict to store.
- **API call (v1.5):** Workers dispatch webhook. Submit `execution` verdict via `POST /verdicts` to core.
- **Failure mode:** Execution target unreachable → write `execution` verdict with `outcome: failure`. Trigger rollback binding if configured. Fail-closed: if dispatch fails, the execution is recorded as failed — no silent failure.

**Step 8: Post-execution verification**

- **v2 owning tier:** Core (executor). Checks deployment replica count returned to expected.
- **v1.5 owning tier:** Workers (respond's remediation agent). Verifies via Prometheus.
- **Failure mode:** Verification fails → trigger rollback binding. Write `execution` verdict with `outcome: failure, verification: failed`.

**Step 9: Downstream recording**

- **Owning tier:** Workers (learn module). Records verdict chain: `action_request → approval(s) → capability → execution`.
- **API call:** Reads chain via `GET /verdicts/{id}/ancestors` from core.
- **v1.5:** Lineage index populated. Hash chain integrity via existing records system.
- **v2:** IPLD CID lineage. Daily Merkle root to Rekor.
- **Failure mode:** If learn module is down, verdicts are still in core's store. Retrospective analysis catches up when learn restarts. No data loss — only delayed analysis.

### Key Insight: Core API Is the Reliability Boundary

In both v1.5 and v2:
- **Verdict persistence is in core.** Worker or bench crash doesn't lose submitted verdicts.
- **Fail-closed is enforced at every decision point.** Error = deny/no-execute.
- **No ambient authority.** Every action requires an explicit verdict chain. Workers propose, core records, operators approve, execution is audited.

The difference between v1.5 and v2 is *where* the authorization decision happens (workers vs core), not *whether* it happens.

---

## P0.1a: Default-Allow vs Default-Deny Ratification

**Follow-up from review.** The RBAC spec §5.2 shows `default allow := false` in the compiled Rego, but §5.4's prose says "default is allow only if no rule produced a deny." These are consistent in practice (no rules matching = no deny = allow), but the *base posture* needs explicit ratification per blast radius.

### Ratified policy: default-deny for production, default-allow for dev/ephemeral

| Blast radius | Default posture | Rationale |
|-------------|----------------|-----------|
| `production` | **default-deny** | Production actions require explicit policy grant. No rule matching = denied. An action without a covering policy is not allowed by omission. |
| `staging` | **default-deny** | Staging mimics production posture. Operators shouldn't be surprised by different auth behaviour in staging vs production. |
| `dev` | **default-allow** | Dev actions permitted unless a policy explicitly denies. Friction-free experimentation. |
| `ephemeral` | **default-allow** | Same as dev. Short-lived environments don't warrant approval gates. |

### Implementation

This requires a spec update to OPENSRM-RBAC-EXTENSION-v2 §5.4. The current text says "default is allow only if no rule produced a deny" — this is a single global default. The ratified posture is blast-radius-conditional:

```rego
package nthlayer.authorisation

import future.keywords.if

# Blast-radius-conditional default
default allow := false

allow if {
    input.action.blast_radius in {"dev", "ephemeral"}
    count(deny) == 0
}
```

For production/staging, `allow` stays false unless a rule explicitly grants it (via `allow if { ... }` rule with matching conditions). For dev/ephemeral, `allow` becomes true when no deny rule fires.

**Spec change needed:** Add §5.4a "Blast-radius-conditional default posture" to OPENSRM-RBAC-EXTENSION-v2, documenting this as the NthLayer-shipped default policy. Organisations can override by providing their own base policy.

---

## P0.2: Policy Evaluation Order Validation

**Spec:** OPENSRM-RBAC-EXTENSION-v2 §5.4 (all-match with deny-wins)
**Policy under test:** `production-tightening` from §5.1

### Policy rules:

```yaml
rules:
  - match:
      action.blast_radius: production
      principal.kind: agent
    effect:
      require_approval: dual-human
      require_attributes:
        principal.team: sre
  - match:
      action.blast_radius: production
      principal.attributes.on_call: false
    effect:
      deny: "Production actions require on-call principal"
```

### Scenario A: Agent requests production rollback during change freeze with exception

**Input:**
```json
{
  "principal": { "kind": "agent", "id": "triage-agent-01", "attributes": { "team": "sre", "on_call": true } },
  "action": { "id": "rollback-deployment", "blast_radius": "production" },
  "state": {
    "change_freezes": [{
      "active": true,
      "exceptions": [{ "action_ids": ["rollback-deployment"] }]
    }]
  }
}
```

**Evaluation (all rules evaluate):**
1. Rule 1 matches: `blast_radius == production` AND `kind == agent` → effect: `require_approval: dual-human, require_attributes: {principal.team: sre}`
2. Rule 2 does NOT match: `on_call` is true → no deny
3. Precondition `no-change-freeze`: freeze is active BUT `rollback-deployment` is in exceptions → passes

**Result:** `{ allow: false, required_approvals: ["dual-human"], required_attributes: { "principal.team": "sre" }, deny_reasons: [] }`

**Verdict:** Correct. Agent can proceed after dual-human approval from SRE team members. Change freeze doesn't block because the action is excepted.

### Scenario B: Off-call human requests production action

**Input:**
```json
{
  "principal": { "kind": "human", "id": "jane.doe", "attributes": { "team": "payments", "on_call": false } },
  "action": { "id": "rollback-deployment", "blast_radius": "production" },
  "state": { "change_freezes": [] }
}
```

**Evaluation (all rules evaluate):**
1. Rule 1 does NOT match: `kind == human` (not agent) → no effect
2. Rule 2 matches: `blast_radius == production` AND `on_call == false` → deny: "Production actions require on-call principal"

**Result:** `{ allow: false, required_approvals: [], deny_reasons: ["Production actions require on-call principal"] }`

**Verdict:** Correct. deny-wins means the deny from Rule 2 takes precedence. Even if Rule 1 had matched and required_approval were satisfied, the deny would still block. This is the correct behaviour — off-call principals should not execute production actions regardless of approvals.

### Scenario C: Agent requests dev-environment action

**Input:**
```json
{
  "principal": { "kind": "agent", "id": "triage-agent-01", "attributes": { "team": "sre", "on_call": true } },
  "action": { "id": "scale-up", "blast_radius": "dev" },
  "state": { "change_freezes": [] }
}
```

**Evaluation (all rules evaluate):**
1. Rule 1 does NOT match: `blast_radius == dev` (not production) → no effect
2. Rule 2 does NOT match: `blast_radius == dev` (not production) → no effect

**Result:** `{ allow: true, required_approvals: [], deny_reasons: [] }`

**Verdict:** Correct. No rules match → default allow. Dev-environment actions by on-call agents proceed without approval.

### Composition validation

All-match with deny-wins composes correctly:
- **Multiple rules can fire.** In Scenario A, both Rule 1 (require_approval) and Rule 2 (deny) could have fired if the principal were off-call. The deny would win.
- **require_* constraints compose additively.** If two rules require different approval levels, the stricter one applies.
- **deny is absolute.** No amount of approval satisfies a deny. The principal must change their state (become on-call) to satisfy the condition.
- **No ambiguity found.** The evaluation order is deterministic for these scenarios.

---

## P0.3: Team-Based Case Filtering Validation

**Spec:** NTHLAYER-BENCH-v2.1 §5.2
**Topology:** fraud-detect (team: payments-ml), payment-api (team: payments-team), checkout-svc (team: orders-team), order-service (team: orders-team)

### Operator 1: Alice (payments-ml team)

- **Default view:** Cases for services owned by `payments-ml` → sees fraud-detect cases only
- **"Show all" toggle:** Sees all cases across all teams
- **Expected cases visible by default:** quality_breach on fraud-detect reversal rate, autonomy_change on triage agent

### Operator 2: Bob (orders-team)

- **Default view:** Cases for services owned by `orders-team` → sees checkout-svc and order-service cases
- **"Show all" toggle:** Sees all cases
- **Expected cases visible by default:** Cases triggered by cascading failures from payment-api (which orders-team's services depend on)

### Operator 3: Carol (SRE, no specific team — or team: sre)

- **Default view:** If team filtering matches exactly, Carol sees cases for services owned by `sre` — which might be none in the demo topology
- **Resolution:** The Bench should treat `sre` as a special case or Carol should default to "show all." Better: team filtering matches the operator's team against the manifest's `owner` field. If no services match, Bench shows "No cases for your team" with a prompt to "show all."
- **Alternative:** Operators can configure their team in `nthlayer.yaml` under `bench:`. If not configured, default to "show all."

### Team assignment derivation

Team is derived from manifest `owner` field:
- v1 manifests: `spec.ownership.team` (e.g., `payments-ml`)
- v2 manifests: `spec.owner.group` (Backstage entity ref, optional with fallback to inline)

### Services with no team assignment

If a manifest has no `owner`/`team` field:
- Cases for that service are visible only in "show all" mode
- They are NOT hidden — they're uncategorized, which is itself a signal worth surfacing
- Bench could show them under an "Unassigned" group

### Validation result

The team-with-toggle model works for the demo topology. Three edge cases documented:
1. Operator whose team has no services → show "no cases for your team" + encourage "show all"
2. Services with no team assignment → visible in "show all," grouped as "Unassigned"
3. Cross-team dependencies (payment-api failure creates cases for checkout-svc) → correctly shown to orders-team because the case's service is checkout-svc, not payment-api

---

## P0.4: Regorus vs regopy Decision

**Spec:** OPENSRM-RBAC-EXTENSION-v2 §5.3
**Note:** This is a v2 decision. v1.5 does not use either library.

### Assessment

| Factor | Regorus (microsoft/regorus) | regopy |
|--------|---------------------------|--------|
| **Language** | Rust + PyO3 bindings | C++ with Python bindings |
| **License** | MIT/Apache-2.0 dual | Apache-2.0 |
| **OPA Conformance** | v1.2 suite minus crypto builtins (per spec) | Partial OPA conformance |
| **PyPI availability** | Not on PyPI as of April 2026 (install from git or local wheel) | On PyPI, precompiled wheels cp3.6-cp3.14 |
| **macOS arm64** | Requires building from source (Rust toolchain) | Precompiled wheel available |
| **manylinux wheels** | Not available on PyPI | Available |
| **Maintenance** | Active (Microsoft, part of Azure Policy) | Active but smaller community |
| **Performance** | Fast (Rust core) | Fast (C++ core) |

### Decision: Regorus (default), with regopy as documented fallback

**Rationale:**
1. Regorus has stronger OPA conformance (v1.2 suite)
2. Microsoft backing provides long-term maintenance confidence
3. The wheel packaging gap is solvable: we build wheels as part of our release process (Rust toolchain in CI is standard)
4. The spec already documents regopy as fallback for platforms where Regorus wheels are unavailable
5. Both evaluate the same Rego source — switching is transparent to policy authors

**Action for v2:** Add Regorus wheel build to CI. Publish prebuilt wheels for manylinux and macOS arm64. Document regopy fallback for exotic platforms.

---

## P0.5: v1.5-First Strategy Ratification

**Spec:** Spec revision summary (v1.5 vs v2 boundary table)

### Ratified v1.5 Boundary

| Capability | v1.5 Decision | Rationale |
|-----------|---------------|-----------|
| Verdict identity | String IDs (`vrd-...`) | Functional, all consumers work with strings. CID migration is one-time but touches everything. |
| Verdict encoding | JSON TEXT | Human-readable, debuggable. CBOR adds complexity without v1.5 value. |
| Tamper evidence | SHA-256 hash chain (nthlayer-common/records) + SQLite WAL + core-exclusive store access | Operational integrity without third-party dependency. Sufficient for initial deployments. |
| Correlation engine | asyncio session windows | Functional at current scale. Bytewax adds value at higher volumes, not needed yet. |
| Authorisation | Respond owns execution (safe-actions) | Working system. v2 auth layer (Regorus/Biscuit) is significant new capability, not a bug fix. |
| LLM wrapper | `llm_call()` + Instructor additive | Existing callers stay unchanged. Instructor added as new path, not replacement. |
| Content addressing | Two parallel systems coexist | Both work. Convergence to IPLD is v2 cleanup, not v1.5 prerequisite. |
| Store access | Workers: API for both read and write | Clean tier boundary from day one. No transitional direct-DB phase. |
| Bench delivery | Local terminal | textual-serve is production hardening, not core functionality. |
| CloudEvents envelope | Adopted in v1.5 (stable, frozen across v1.5/v2) | Additive wire-format improvement. SIEM integration value from day one. |
| rekor_anchors table | Schema present but empty | Forward compatibility is cheap when planned. |

### Ratified v2 Deferrals

| Capability | Deferred to v2 | Prerequisite |
|-----------|---------------|--------------|
| IPLD CIDv1 | After v1.5 stable | lineage index working with string IDs |
| Canonical CBOR | After v1.5 stable | Coupled to CID adoption |
| Rekor anchoring | After CIDs | V2-A (CIDs required for Merkle roots) |
| Biscuit/Regorus auth | After v1.5 stable | Regorus wheel packaging, Biscuit integration |
| authorise + executor | After v1.5 stable | Full auth flow design |
| Bytewax | Optional for v2 | v1.5 asyncio correlate stable |
| Content-addressing convergence | After CIDs | V2-A |
| LLM class refactor | After v1.5 stable | Instructor additive path validated |
| textual-serve SaaS | After v1.5 Bench stable | V1.5 Bench locally |
| SPIFFE integration | After v2 auth | V2-C (authorise module) |

### Review status

This document is posted for Rob's review. Implementation proceeds after 48 hours (2026-04-23) unless objections are raised. This is a review window, not a blocking gate.

---

## Summary

All five Phase 0 tasks complete, plus three follow-up ratifications:

| Task | Status | Key finding |
|------|--------|-------------|
| P0.1 Auth flow | Complete | Core API is the reliability boundary. Fail-closed at every step. v1.5 and v2 differ in *where* auth happens, not *whether*. |
| P0.1a Default posture | **Ratified** | Default-deny for production/staging, default-allow for dev/ephemeral. Requires RBAC spec §5.4a addition. |
| P0.1 Step 4 fixes | **Ratified** | Case priority derived from blast_radius + incident context (not auto-P0). Stuck action_request observability via metric + alert log. |
| P0.2 Policy eval | Complete | All-match with deny-wins composes correctly. No ambiguity in three test scenarios. deny is absolute. |
| P0.3 Team filtering | Complete | Team-with-toggle works. Three edge cases documented: no-match teams, unassigned services, cross-team cascades. |
| P0.4 Regorus decision | Complete | Regorus default, regopy fallback. Wheel packaging gap solvable in CI. |
| P0.5 v1.5 boundary | Complete | 11 v1.5 decisions + 10 v2 deferrals ratified. 48h review window open. |

### Spec changes needed from follow-ups

1. **OPENSRM-RBAC-EXTENSION-v2 §5.4a:** Add "Blast-radius-conditional default posture" — default-deny for production/staging, default-allow for dev/ephemeral. NthLayer-shipped default policy; organisations may override.
2. **Epic tree P1-B.5 or P2-B:** Add stuck-action_request monitoring to core's background jobs — metric `nthlayer_stuck_action_requests` + alert log at 5× threshold.
3. **Epic tree P1-B.4:** Case priority derivation logic documented — blast_radius × incident context, not hardcoded P0.
