# Learn → Spec Operator Workflow Design (opensrm-jmy.6)

**Status:** Approved for implementation. Decomposition + premise approved via `/challenge-the-premise` on 2026-05-26; design decisions locked through seven brainstorming rounds. Five follow-up beads filed (jmy.21, jmy.22, jmy.23, jmy.24, jmy.25).

**Spec source:** `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 2 (Learn → Spec feedback loop).

**Foundation:**
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` — jmy.2's shipped engine: `Recommendation` + `SpecRecommendation` dataclasses, `analyze_incident()`, `_tighten_slo_recommendations`, `_add_deploy_gate_recommendations`, 22 tests.
- `nthlayer-workers/src/nthlayer_workers/learn/cli.py` — existing `nthlayer-learn` CLI with three subcommands (`accuracy`, `list`, `retrospective`); this design adds a fourth: `recommendations`.
- `nthlayer_common.manifest.load_manifest()` — canonical OpenSRM v1/v2 parser used for the manifest-discovery fallback walk.
- New runtime dependency: `ruamel.yaml>=0.18` — round-trip YAML preserving operator-authored comments. Approved per brainstorming Q1 decision (PyYAML's silent comment loss would be hostile to operator workflows).

---

## 1. Reframing context

`opensrm-jmy.6` was originally framed as four numbered items in `NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 2: `add_dependency` recommendation type, CLI integration (`--apply-to` / `--pr` / `--interactive`), spec patch generation with comment preservation, and a `financial_impact` field on recommendations.

Challenge-the-premise (2026-05-26) decomposed this into the **Learn → Spec loop foundation** (CLI + spec patches) plus four separate-concern follow-ups:

| Bead | Scope |
|---|---|
| `opensrm-jmy.21` | `add_dependency` recommendation type (requires correlator/topology integration) |
| `opensrm-jmy.22` | `--interactive` TUI walkthrough (operator UX, separate from loop foundation) |
| `opensrm-jmy.23` | `financial_impact` field on `Recommendation` (jmy.1 unblocked it; additive enrichment) |
| `opensrm-jmy.24` | Per-recommendation CLI selection (`--include` / `--exclude`) — v1.5 ships all-or-nothing |
| `opensrm-jmy.25` | Machine-readable `--json` output for CI integration |

The reframing keeps jmy.6 focused on the **operator workflow**, not the flag list: post-incident, operator inspects recommendations, applies them locally, reviews the diff, opens a PR for team review. This is the value proposition — flags are implementation.

---

## 2. Scope

### In scope

1. New `recommendations` subcommand on `nthlayer-learn` CLI with composable flags `--incident <id>` / `--from <plan.yaml>` (input) and `--output <file>` / `--apply-to <specs-dir>` / `--pr` (orthogonal outputs) plus `--force` / `--base` / `--draft` (modifiers).
2. Rename of jmy.2's plan artefact: `apiVersion: opensrm.io/v1` → `apiVersion: nthlayer.io/learn/v1`; `kind: SpecRecommendation` → `kind: RecommendationPlan`. Stable per-recommendation `id` field (`rec-<12-char-lowercase-sha256-hex>` of `incident_id|type|field`).
3. ruamel.yaml round-trip write-back preserving operator-authored manifest comments.
4. Deep-merge primitive at dotted-path target locations; type normalisation across `int`/`float`/numeric-`str`; state-machine classification of every recommendation as one of {`apply_clean`, `already_applied`, `drift_detected`, `target_path_missing`, `manifest_not_found`}.
5. `gh` CLI integration for PR creation (pre-flight checks, branch creation, atomic single-commit, PR open). GitHub-only for v1.5.
6. Cross-process integration test in `nthlayer/test/` exercising the full workflow against a real git repo + stubbed `gh`.

### Out of scope (filed)

| Bead | Why deferred |
|---|---|
| `opensrm-jmy.21` | `add_dependency` requires topology integration; orthogonal data-source concern |
| `opensrm-jmy.22` | TUI walkthrough is UX work; loop foundation lands first |
| `opensrm-jmy.23` | `financial_impact` is additive enrichment now that jmy.1 closed; lands on top of jmy.6's foundation |
| `opensrm-jmy.24` | Per-rec selection adds CLI surface; v1.5 ships all-or-nothing per Rob's risk-reduction decision |
| `opensrm-jmy.25` | Machine-readable `--json` is adopt-when-needed; not v1.5-critical |
| Pluggable git hosting (GitLab/Bitbucket) | `gh`-only for v1.5; abstraction cost is real, demo is GitHub-driven. File when an adopter requests it. |
| Structural manifest changes (key removal, restructuring) | Deep-merge suffices for `tighten_slo` / `add_deploy_gate`. File when a recommendation type needs it. |
| Auto-rollback on write failure | Rare; `git checkout` is one command away. Stage-and-write atomically is sufficient. |

### Capability boundary

After jmy.6 ships, an operator with a closed retrospective can run a single command to:
1. Inspect recommendations as a structured YAML plan with per-rec context, target path, current vs proposed values, evidence
2. (When `--specs-dir` supplied) See a unified diff preview of what would land at each target path
3. Apply the plan to manifests with comment preservation + drift detection + idempotency
4. Open a GitHub PR for team review

NthLayer never auto-modifies specs; `requires_human_review: true` is hardcoded on `SpecRecommendation` (already shipped in jmy.2). Operators always review + merge.

---

## 3. Architecture

`nthlayer-workers learn recommendations` is the fourth subcommand on the existing `nthlayer-learn` CLI. One composable subcommand with three orthogonal capability flags mapping to the three phases of the kubectl/terraform operator workflow.

```
                  ┌──────────────────────────────────────────┐
                  │ analyze_incident(retrospective_data, id) │
                  │   (existing, jmy.2 — unchanged)          │
                  │   → SpecRecommendation (in-memory)       │
                  └─────────────────┬────────────────────────┘
                                    │
       ┌────────────────────────────┼─────────────────────────────┐
       │                            │                             │
       ▼                            ▼                             │
   --output FILE             --apply-to <specs-dir>               │
   (serialise)               (read → merge → write atomically)    │
       │                            │                             │
       ▼                            ▼                             │
   plan.yaml                  modified manifests                  │
   apiVersion:                (ruamel.yaml round-trip,            │
   nthlayer.io/learn/v1       comments preserved)                 │
   kind:                            │                             │
   RecommendationPlan               │   ┌─────────────────────────┘
                                    ▼   ▼
                                  --pr (git + gh)
                                    │
                                    ▼
                                GitHub PR
                                (one commit on branch
                                 learn/recommendations/
                                 <incident-id>[-<service-name>])
```

**Two input sources** (mutually exclusive): `--incident <id>` (live regen from core's retrospective) or `--from <plan.yaml>` (consume saved plan). Either feeds the same in-memory `SpecRecommendation`.

**"Plan and apply use the same artefacts" enforced two ways:**
- Within a single invocation, `--output` and `--apply-to` operate on the identical in-memory `SpecRecommendation`.
- Across invocations, `--from` reads `plan.yaml` as canonical input, so apply uses exactly what `--output` produced. Operators can trust that what they reviewed in `plan.yaml` is what gets applied.

**`--pr` couples to `--apply-to`.** The modified manifests are what the PR contains. `--apply-to` without `--pr` is the local-only workflow.

**`--apply-to` allows dirty trees with warning** (incident-response ergonomics). Only files actually changed by recommendations get staged; uncommitted operator changes to other files are preserved. See § 7 for dirty-tree interaction with the state machine.

**Three kubectl/terraform UX conventions adopted explicitly:**
1. **Plan output is reviewable.** `--output` produces operator-readable artefacts with per-rec context (incident, rationale, evidence, optional unified-diff preview), not just a mechanical change list.
2. **Apply is idempotent.** Running `--apply-to` twice with the same plan produces the same result. Already-applied recommendations detected and skipped via state-based comparison: if current state matches proposed state, no write happens (regardless of history).
3. **Plan and apply use the same artefacts.** Enforced by code path (single in-memory object across `--output` and `--apply-to`) AND by file path (`--from` reads canonical `plan.yaml`).

---

## 4. Components

Six files: two modified, four new. Each new file has one clear responsibility and a pure-vs-impure boundary mapping to test isolation.

| File | Responsibility | Public surface | Purity |
|---|---|---|---|
| `learn/cli.py` *(modify)* | Add `recommendations` subcommand to existing argparse. Flag plumbing: `--incident` / `--from` (mutex), `--output`, `--apply-to`, `--pr`, `--force`, `--base`, `--draft`. Dispatches to `_apply.py`. | `_cmd_recommendations(args)` | I/O (argv, stdout/stderr, exit codes) |
| `learn/recommendations.py` *(modify)* | Existing engine + extend `Recommendation` with `id` field; rename apiVersion+kind; add `parse_plan_file()`; define `OutcomeKind` enum (`apply_clean`, `already_applied`, `drift_detected`, `target_path_missing`, `manifest_not_found`) — outcomes are part of the recommendation lifecycle (operator-visible in summaries, PR body), not specifically a YAML concern. | `Recommendation`, `SpecRecommendation`, `analyze_incident`, `parse_plan_file`, `OutcomeKind` | Pure |
| `learn/_yaml.py` *(new)* | ruamel.yaml round-trip setup. Pure helpers: `resolve_path(doc, dotted_path)`, `apply_at_path(doc, dotted_path, value)` (in-place on CommentedMap, comments preserved), `normalize_scalar(v)`, `classify_outcome(manifest_value, rec) -> OutcomeKind`. Internal `_yaml.py` underscored for replaceability. | `resolve_path`, `apply_at_path`, `classify_outcome`, `normalize_scalar` | Pure (no I/O) |
| `learn/_apply.py` *(new)* | Orchestration: read all targeted manifests (caching by service name), per-rec classify, deep-merge in memory, atomic write phase (alphabetical by file path), end-of-run summary builder. Manifest resolution: filename-convention + recursive `glob` fallback. | `apply_recommendations(plan, specs_dir, *, force=False) -> ApplyResult`, `ApplyResult` | I/O (file reads/writes) |
| `learn/_preview.py` *(new)* | Generate per-recommendation `preview` field (unified-diff string at target path). Drift marker when manifest's current value differs from rec's `current_value`. | `build_preview(manifest_path, rec, current_yaml) -> str` | Pure |
| `learn/_gh.py` *(new)* | Pre-flight checks (`check_gh_installed`, `check_gh_auth`, `check_git_repo`, `check_remote`, `check_branch_available`) + `create_pr_via_gh(title, body, branch, *, base="main", draft=False)`. All shell-out via `subprocess.run`. Underscored for replaceability when pluggable hosting lands. | The functions above + `PRResult`, `PreflightError` | I/O (subprocess) |

### Dual-parser strategy

Two YAML parsers operate on manifest files; the duality is intentional and documented to prevent well-meaning "simplification" later:

- **`nthlayer_common.manifest.load_manifest()`** — used only for the discovery fallback walk. Returns validated dataclasses; we only need `metadata.name` from each file to build the `{service-name → file-path}` index.
- **`ruamel.yaml` directly** — used for the read+write path on the target manifest(s). Preserves operator-authored comments on round-trip; the file we read is the file we write back.

Both are correct for their purposes. Conflating them would either lose comments (replace ruamel with `load_manifest`'s underlying PyYAML) or reimplement validation (drop `load_manifest` and parse manually).

---

## 5. Data flow

Three workflows. Same `SpecRecommendation` object throughout each.

### Flow A — Single-step (trusted-operator)

```
$ nthlayer-learn recommendations --incident inc-2026-05-21-001 --apply-to specs/ --pr
```

1. `parse args` → `InputSource = Incident("inc-...")`
2. `CoreAPIClient.get_retrospective_for_incident(...)` → retrospective dict
3. `analyze_incident(retrospective, incident_id)` → `SpecRecommendation` (in-memory)
4. Pre-flight: gh installed + authed + git repo + remote + branch available (any failure → exit 2, no apply attempted)
5. `apply_recommendations(plan, specs_dir, force=args.force)`:
   - `resolve_manifest_path(svc)`: try `specs/<svc>.yaml`, fall back to recursive `*.yaml` / `*.yml` walk excluding hidden dirs
   - Read each unique target manifest once via ruamel.yaml round-trip parse. Parse failure → fail-fast exit 2 with `file:line:col` + which recommendation triggered the read
   - For each rec: `classify_outcome(manifest_value, rec)` → one of the five `OutcomeKind` values
     - `apply_clean` → in-memory `apply_at_path(doc, rec.field, rec.proposed_value)`
     - `already_applied` → silent skip
     - `drift_detected` → skip unless `--force`; record reason
     - `target_path_missing` → skip; record reason
     - `manifest_not_found` → skip; record reason
   - Write phase (atomic): alphabetical by file path, one file at a time. Read phase succeeded for all files before any write begins.
6. Git: stage only files in `ApplyResult.modified_files`; commit with Section 7 message
7. Git: push branch `learn/recommendations/<incident-id>[-<service-name>]`
8. `_gh.create_pr_via_gh(title, body, branch, base=args.base, draft=args.draft)` — on failure after successful commit, exit 1 with operator-recovery instructions
9. stdout: `PR created: https://github.com/org/repo/pull/N`. stderr: end-of-run summary table + exit-code reasoning.

### Flow B — Audited two-step (most common)

```
# Generate plan and commit as artefact
$ nthlayer-learn recommendations --incident inc-2026-05-21-001 --output plan.yaml --specs-dir specs/
$ git add plan.yaml
$ git commit -m "plan: recommendations for inc-2026-05-21-001"

# Apply with PR
$ nthlayer-learn recommendations --from plan.yaml --apply-to specs/ --pr
```

Step 1 writes `plan.yaml` (apiVersion `nthlayer.io/learn/v1`, kind `RecommendationPlan`) with each `Recommendation` enriched by a unified-diff `preview` field because `--specs-dir` was supplied. Operator reads + commits the plan as audit artefact.

Step 2: `parse_plan_file("plan.yaml")` validates apiVersion + kind, deserialises into `SpecRecommendation`, then Flow A from step 4 onward. The PR contains both the operator's plan-commit AND the auto-generated manifest-changes-commit — reviewer sees both intent and outcome.

### Flow C — Plan-only inspection

```
$ nthlayer-learn recommendations --incident inc-...
```

Engine output streamed to stdout as YAML. Useful for piping, scripts, eyeballing before committing to file-or-apply workflows.

### State machines (per `current_value` presence)

The engine sets `current_value` for recommendations modifying existing state (e.g. `tighten_slo`) and leaves it `None` for recommendations adding new state (e.g. `add_deploy_gate`). The two cases have semantically different state machines:

**For recommendations WITH `current_value` (modifying existing):**

| Manifest state at target path | Outcome |
|---|---|
| Path missing | `target_path_missing` |
| Path = `proposed_value` | `already_applied` |
| Path = `current_value` | `apply_clean` (overwrite) |
| Path = anything else | `drift_detected` (`--force` overrides) |

**For recommendations WITHOUT `current_value` (adding new):**

| Manifest state at target path | Outcome |
|---|---|
| Path missing | `apply_clean` (create) |
| Path = `proposed_value` | `already_applied` |
| Path = anything else | `drift_detected` (`--force` overrides) |

`already_applied` is **state-based, not history-based**: current state matches proposed state regardless of how the manifest reached that state (previous application, different recommendation, manual configuration, coincidence — outcome is the same).

### Dirty-tree interaction

Per § 3, dirty trees are allowed with warning. The deep-merge operates on **current disk state including uncommitted operator changes**; classification reflects the current state, not the last-committed state.

- Operator has uncommitted change to a **different field** in the same manifest → recommendation applies cleanly; both changes end up in the auto-generated commit. Operator should review with `git diff` before pushing.
- Operator has uncommitted change to the **same field** the recommendation targets → `drift_detected` (manifest value matches neither `current_value` nor `proposed_value`). Skip unless `--force`.
- Operator has restructured surrounding YAML → may trigger `target_path_missing` if intermediate keys are gone.

Principle: the tool treats current disk state as authoritative; operators decide whether dirty-tree changes coexist with recommendations.

---

## 6. Wire shapes

### 6.1 `plan.yaml` (RecommendationPlan)

```yaml
apiVersion: nthlayer.io/learn/v1
kind: RecommendationPlan
metadata:
  incident: inc-2026-05-21-001
  generated_by: nthlayer-workers v1.6.0
  generated_at: 2026-05-26T10:00:00+00:00
  confidence: 0.7
  requires_human_review: true
recommendations:
  - id: rec-a3f8b2e1c9d4
    service: fraud-detect
    type: tighten_slo
    field: spec.slos.judgment.target
    current_value: 95.0
    proposed_value: 98.5
    rationale: |
      Calibration drift detected: reversal rate climbed from 1.2% to 4.8%
      over the 30-day window.
    confidence: 0.7
    evidence:
      - incident: inc-2026-05-21-001
        observation: reversal_rate breached for 47 minutes
    preview: |          # present iff --specs-dir was supplied to --output
      # File: specs/fraud-detect.yaml
      # Path: spec.slos.judgment.target
      -   target: 95.0
      +   target: 98.5
```

`apiVersion: nthlayer.io/learn/v1` — module-namespaced for forward compatibility; future tooling reads the version and errors clearly on mismatch. `kind: RecommendationPlan` — renamed from jmy.2's `SpecRecommendation` (the engine's internal Python dataclass name is unchanged; only the wire `kind` differs).

`id` — `rec-` + 12 lowercase hex chars of SHA-256(`incident_id|type|field`). Deterministic across tool versions; algorithm + input format pinned here so future contributors don't accidentally change the hash basis.

`preview` — present iff `--output` was invoked with `--specs-dir`. Always absent on bare `--output`. When the manifest's current value differs from the recommendation's `current_value`, the preview includes a drift warning marker (e.g. `# WARN: manifest drifted from recommendation's expected value (current=98.0, expected=95.0)`).

Type normalisation: for the idempotency / drift comparison, scalars normalise across `int(98)` / `float(98.0)` / `str("98")` / `str("98.0")` — all classify-equal IFF they round-trip to the same Python number. Non-scalar type mismatch (dict-vs-list, dict-vs-scalar) is `drift_detected`, not silently coerced.

### 6.2 End-of-run summary (stderr)

```
Applied: 3 recommendations
  rec-a3f8b2e1c9d4  fraud-detect    spec.slos.judgment.target          95.0 → 98.5
  rec-b7c2e5f8a1d6  payment-api     spec.slos.availability.target      99.0 → 99.5
  rec-c4d9f1a3b8e2  fraud-detect    spec.deployment.gates.judgment     (none) → (added)

Skipped: 1 recommendation
  rec-d5e8f2b6c9a1  notification    drift_detected
    manifest current:        98.0
    recommendation expected: 95.0
    proposed value:          99.0

    Possible causes:
      - Another operator changed this SLO since the retrospective
      - Another recommendation already applied to this field
      - Manifest was edited between retrospective and apply

    Re-run with --force to apply rec-d5e8f2b6c9a1 anyway.

Exit code: 1 (partial success)
```

Value-change notation: `<old> → <new>` for modifications, `(none) → (added)` for additions, `<value> → (removed)` for removals (future recommendation types).

### 6.3 Commit message

Single commit per `--apply-to` run. Stages only files modified by recommendations (not the entire working tree, per § 5 dirty-tree behaviour).

```
Apply NthLayer recommendations from inc-2026-05-21-001

- rec-a3f8b2e1c9d4  tighten_slo      fraud-detect   spec.slos.judgment.target          95.0 → 98.5
- rec-b7c2e5f8a1d6  add_deploy_gate  payment-api    spec.deployment.gates.judgment     (none) → (added)
- rec-c4d9f1a3b8e2  tighten_slo      fraud-detect   spec.slos.availability.target      99.0 → 99.5

Plan: plan.yaml                       # omitted if --from not used
Generated by: nthlayer-workers v1.6.0
Tool: NthLayer learn module
```

No conventional-commit prefix — these commits land in the *operator's* specs repo, whose conventional-commits policy applies (operators can `--amend` to add `feat:` / `chore:` before push).

### 6.4 PR body (Markdown)

```markdown
## Changes

| ID | Type | Service | Target path | Change |
|---|---|---|---|---|
| `rec-a3f8b2e1c9d4` | `tighten_slo` | `fraud-detect` | `spec.slos.judgment.target` | `95.0` → `98.5` |
| `rec-b7c2e5f8a1d6` | `add_deploy_gate` | `payment-api` | `spec.deployment.gates.judgment` | *(added)* |

## Skipped

| ID | Reason | Next step |
|---|---|---|
| `rec-d5e8f2b6c9a1` | `drift_detected` — manifest current `98.0`, expected `95.0` | Investigate drift cause, re-run with `--force rec-d5e8f2b6c9a1` if appropriate |
| `rec-e1f4a8b2c5d7` | `target_path_missing` — `spec.slos.judgment` block doesn't exist in fraud-detect.yaml | Verify SLO still exists. If renamed, regenerate the recommendation; if removed intentionally, dismiss this rec. |

---

## Context

**Incident:** `inc-2026-05-21-001`
**Plan generated:** 2026-05-26T10:00:00+00:00 by `nthlayer-workers v1.6.0`
**Plan file:** `plan.yaml` (committed alongside this change)   # omitted if --from not used

## Rationale per recommendation

<details>
<summary><code>rec-a3f8b2e1c9d4</code> — tighten_slo fraud-detect</summary>

Calibration drift detected: reversal rate climbed from 1.2% to 4.8% over the 30-day window.

**Evidence:**
- Incident `inc-2026-05-21-001`: reversal_rate breached for 47 minutes

</details>

(... one details block per recommendation ...)

---

🤖 Generated by NthLayer learn module. Human review and merge required (`requires_human_review: true`).
```

Incident ID stays plain text in v1.5 (no URL linking). Operators wanting incident URL linking configure PR-review tooling; if it becomes an adoption blocker, add `incident_url_template` config option.

### 6.5 Branch naming

Canonical: `learn/recommendations/<incident-id>`
Optional suffix when single-service-scoped (which retrospectives usually are): `learn/recommendations/<incident-id>-<service-name>`

Branch-name collision (same incident processed twice) refused at pre-flight with explicit delete instructions. Auto-suffix is deferred — operators wanting multiple PRs per incident can pass `--branch-suffix` (follow-up if requested).

---

## 7. Error handling

Three categories with deterministic exit-code semantics.

### Category A — Pre-flight (operator-environment + read-phase parse failures)

Detected before any merge logic runs. Fail-fast, single-line `Error: <reason>` + brief remedy. Exit 2.

| Reason code | Triggered by | Remedy hint |
|---|---|---|
| `gh_not_installed` | `subprocess.run(["gh", "--version"])` raises `FileNotFoundError` | `brew install gh` / etc. |
| `gh_not_authenticated` | `gh auth status` exits non-zero | `gh auth login` |
| `not_a_git_repo` | `git rev-parse --git-dir` exits non-zero from `--specs-dir` | Run from a git repo |
| `no_remote` | `git remote get-url origin` exits non-zero | `git remote add origin <url>` |
| `branch_exists` | `git show-ref --verify refs/heads/<branch>` succeeds OR `git ls-remote --heads origin <branch>` non-empty | `git branch -D <branch>` (local) / `git push origin --delete <branch>` (remote) |
| `manifest_parse_error` | ruamel.yaml raises during the read phase | File path + parser line/column + which rec triggered the read |
| `plan_file_unknown_version` | `--from plan.yaml` has unsupported `apiVersion` | List supported versions; upgrade path |
| `plan_file_invalid` | `--from plan.yaml` missing required keys or malformed | YAML path of the bad key + expected shape |
| `invalid_args` | `--incident` and `--from` both supplied OR `--pr` without `--apply-to` | argparse-level message |

Pre-flight order: gh first, branch_exists last (depends on resolved branch name from incident id).

### Category B — Per-recommendation outcomes

The two state-machine tables from § 5. Each recommendation gets exactly one outcome. Run continues; outcomes accumulate; end-of-run summary reports all.

`--force` scope is **drift-only**. Other skip reasons represent problems `--force` doesn't address; the flag is silent on them (does not change their behaviour). Documented explicitly so future contributors don't accidentally expand `--force`.

### Category C — Post-apply (commit / push / PR)

Detected after manifest writes succeeded. Manifest changes are committed locally and the operator's specs dir is in a known-good state; the failure is in publishing. Exit 1.

**PR-creation failure:**

```
Error: PR creation failed

  gh pr create failed: <gh's stderr passed through verbatim>

  Your manifest changes are committed on branch
  learn/recommendations/inc-2026-05-21-001.

  Options:
    Retry:   gh pr create --base main --head learn/recommendations/inc-2026-05-21-001
    Discard: git branch -D learn/recommendations/inc-2026-05-21-001

  Exit code: 1
```

**Push failure (commit succeeded, push to origin failed):**

```
Error: Push to origin failed

  git push failed: <git's stderr passed through verbatim>

  Your manifest changes are committed on branch
  learn/recommendations/inc-2026-05-21-001 (local only).

  Options:
    Retry:   git push -u origin learn/recommendations/inc-2026-05-21-001
    Discard: git branch -D learn/recommendations/inc-2026-05-21-001

  Exit code: 1
```

The two messages differ in the `(local only)` branch-state note and `git push -u` (sets upstream).

### Exit-code rule (deterministic)

```
Exit 0  iff (zero recommendations supplied)
        OR  (every outcome ∈ {apply_clean, already_applied}
             AND post-apply phase succeeded).

Exit 1  iff at least one apply_clean AND at least one skip
                  ∈ {drift_detected, target_path_missing, manifest_not_found}.
        OR  post-apply phase failed after at least one successful local commit.

Exit 2  iff zero apply_clean AND any skip happened.
        OR  any Category A pre-flight failure (always 2).
```

Empty plans (zero recommendations from a retrospective that produced none) are legitimate; operator did nothing wrong. Exit 0 with `Applied: 0` summary.

Three states map to three CI integration tiers: 0 = ship; 1 = needs attention (partial success); 2 = blocker (nothing applied or environment unfit).

---

## 8. Testing

Six unit-test files + one cross-repo integration test. Unit tests mock subprocess + run ruamel.yaml for real; integration test runs real git + real ruamel.yaml + stubbed `gh` in a `tmp_path` repo.

### Unit test files

| File | Covers |
|---|---|
| `tests/learn/test_recommendations.py` *(extend)* | id determinism (`rec-` + 12 hex; same inputs → same hash); plan-file roundtrip; `parse_plan_file` validation (unknown apiVersion, missing recommendations, non-list recommendations) |
| `tests/learn/test_yaml.py` *(new)* | `resolve_path` happy + missing intermediate (sentinel); `apply_at_path` write + comment preservation (parse manifest with `# inline comment`, apply, re-serialise, assert comment survives); `apply_at_path` creates missing intermediates; `classify_outcome` covers all 7 cells of the two state-machine tables (parametrize per cell); `normalize_scalar` int/float/str equivalence + non-scalar type mismatch |
| `tests/learn/test_apply.py` *(new)* | Happy path (3 recs across 2 manifests → alphabetical write order); `manifest_not_found` skip; **atomicity test using filename-based failure injection** (monkeypatch `Path.write_text` with selective filename match — see below); dirty-tree behaviours (different field, same field, restructured); end-of-run summary string equality; exit-code matrix (parametrize over outcome combinations, including empty-plan → 0) |
| `tests/learn/test_preview.py` *(new)* | `build_preview` for `tighten_slo`; `build_preview` for `add_deploy_gate`; drift marker in preview when manifest current differs from rec's `current_value`; preview absent when `--specs-dir` absent |
| `tests/learn/test_gh.py` *(new)* | All 5 pre-flight scenarios from § 7 + `branch_exists`; `create_pr_via_gh` happy + failure; `base`/`draft` kwargs flow through to argv; post-apply gh-failure recovery message; post-apply push-failure recovery message (exact-string equality) |
| `tests/learn/test_cli_recommendations.py` *(new)* | `--incident` + `--from` both → `invalid_args`; `--pr` without `--apply-to` → `invalid_args`; `--output` write before `--apply-to` reads (verify by file mtime + simulated apply-failure → output exists); empty plan → exit 0; `--force` per-invocation (applies to all `drift_detected` in run) |

#### Atomicity test pattern (filename-based injection)

```python
def test_atomicity_partial_write_failure(tmp_path, monkeypatch):
    # Setup: two manifests, recs target both
    (tmp_path / "a-service.yaml").write_text(...)
    (tmp_path / "b-service.yaml").write_text(...)
    plan = ...

    original_write_text = Path.write_text
    def selective_fail(self, content, **kwargs):
        if self.name == "b-service.yaml":
            raise OSError("simulated write failure")
        return original_write_text(self, content, **kwargs)
    monkeypatch.setattr(Path, "write_text", selective_fail)

    result = apply_recommendations(plan, tmp_path)

    # Assert: a-service.yaml modified on disk
    # Assert: b-service.yaml retained original content
    # Assert: ApplyResult flags partial failure
```

Filename-based injection is more readable and more robust than call-count-based (resilient to implementation changes in alphabetical-order traversal).

### Integration test

`nthlayer/test/learn-recommendations-integration.sh` — lives in `nthlayer/test/` per the cross-repo integration-test convention (matches the existing three-tier integration test pattern). Triggered via `workflow_dispatch` + nightly cron.

Drives the audited two-step workflow end-to-end:

```
1. tmp_path/specs/ = copy of nthlayer/demo/specs/
2. seed retrospective JSON for a known incident (fixture)
3. nthlayer-learn recommendations --incident <id> --output plan.yaml --specs-dir tmp_path/specs/
     → assert plan.yaml exists, parseable, contains rec-* ids + preview fields
4. nthlayer-learn recommendations --from plan.yaml --apply-to tmp_path/specs/
     → assert manifests modified at expected paths
     → assert comment preservation: pre-existing inline comments survive round-trip
     → assert exit 0
5. cd tmp_path && git log → assert single commit with expected message shape
6. PATH=/path/to/stub-gh:$PATH nthlayer-learn recommendations --from plan.yaml --apply-to tmp_path/specs/ --pr
     → assert stub-gh received correct argv (title, body, branch, base)
     → assert stdout has "PR created: <stub URL>"
```

**Integration test isolation guarantees** (pinned to prevent the "works locally for the author, breaks elsewhere" failure mode):
- All filesystem operations confined to `tmp_path`
- `gh` stubbed via PATH injection (no real `gh` config, no real API calls)
- git operations use `tmp_path` repo with local config only (operator's `~/.gitconfig` untouched via `GIT_CONFIG_GLOBAL=/dev/null`)
- No network access required
- Cleanup via pytest fixture teardown or shell `trap` on exit

### Test isolation strategies summary

| Concern | Strategy |
|---|---|
| ruamel.yaml | Runs for real (cheap, no I/O outside `tmp_path`) |
| Filesystem | `tmp_path` pytest fixture; never `/tmp` or repo root |
| subprocess (gh / git) | `monkeypatch` at module-level function boundary (`_gh.check_gh_installed`, etc.) |
| nthlayer-core API | Mock `CoreAPIClient.get_retrospective_for_incident` |
| Time | `analyze_incident` already accepts `generated_at` as parameter for testability |

### Fixture data

Reuse `nthlayer/demo/specs/` as the canonical manifest source for realism. Add small focused fixtures under `tests/learn/fixtures/` for edge cases (manifests with comments to verify preservation, malformed YAML to trigger parse errors, retrospectives that produce empty recommendation sets).

---

## 9. Performance assumptions

Not enforced by tests; pinned here for future contributors to know which behaviours are v1.5 design choices vs v2 enhancement opportunities.

- Designed for **small workloads: 1–10 recommendations across 1–20 manifests** per `--apply-to` invocation.
- At larger scale (100+ manifests, 50+ recommendations), the **discovery fallback walk** (per-call `glob` + `load_manifest` parse of every YAML) and **per-rec classification** (one ruamel.yaml parse per unique manifest read once + classification dispatch) become noticeable.
- Future optimisation paths (none of which are v1.5 concerns):
  - Pre-built `{service-name → file-path}` index cached on disk
  - Parallel manifest reads (`asyncio.gather` or `concurrent.futures`)
  - Bulk classify with shared YAML parse cache
- Memory: each manifest is ≤ ~10 KB in practice; `apply_recommendations` holds all touched manifests in memory simultaneously (per § 5 atomicity model). Even at 100-manifest scale, ~1 MB resident is trivial.

---

## 10. References

- Bead: `opensrm-jmy.6` (Spec patch generation + CLI `--apply-to` / `--pr` — Learn → Spec follow-up).
- Filed follow-up beads: `opensrm-jmy.21` / `.22` / `.23` / `.24` / `.25`.
- Spec source: `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 2.
- Foundation commit: `nthlayer-workers/learn/recommendations.py` (jmy.2 close — `analyze_incident`, `Recommendation`, `SpecRecommendation`).
- Predecessor design pattern: `nthlayer/docs/superpowers/specs/2026-05-20-jmy18-override-verdict-binding-design.md` (same brainstorming + R5 workflow shape).
- ruamel.yaml docs: https://yaml.readthedocs.io/en/latest/ (round-trip API, comment preservation).
- `gh` CLI reference: https://cli.github.com/manual/gh_pr_create.
