# `--json` Output for `learn recommendations` Design (opensrm-jmy.25)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-29. Bead: `opensrm-jmy.25`.

**Foundation:**
- `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations` (current `--apply-to` / `--pr` / `--from` orchestration; pre-flight at lines 182–183; soft PR failure raise at line 312).
- `nthlayer-workers/src/nthlayer_workers/learn/apply.py::ApplyResult` (carries `applied: list[AppliedRecommendation]` and `skipped: list[SkippedRecommendation]`).
- `nthlayer-workers/src/nthlayer_workers/learn/apply.py::RecOutcome` (skipped-entry enum: `drift_detected`, `already_applied`, `manifest_missing`, etc.) — fields are `outcome` + `detail`, NOT `reason` + `details`.
- `nthlayer-workers/src/nthlayer_workers/learn/pr.py::PRResult` (carries `url`, `number`).

---

## 1. Problem statement

`nthlayer-workers learn recommendations --apply-to <dir>` (jmy.6) writes a human-readable summary to stdout describing what was applied, what was skipped, and (with `--pr`) the resulting PR URL. CI pipelines have no structured surface: they grep, regex, and break on the next copy-edit. jmy.25 adds an additive `--json` flag that emits one machine-readable document to stdout at end-of-run, mirroring the same `ApplyResult` + `PRResult` data the human summary already exposes.

---

## 2. Existing surface

- `_cmd_recommendations` — argparse subcommand; orchestrates `--from` / `--incident` plan generation, optional `--apply-to`, optional `--pr`. Hard pre-flight rejects `--pr` without `--apply-to` (cli.py:182–183).
- `ApplyResult.applied` — list of `AppliedRecommendation(id, service, field, manifest_path, ...)`.
- `ApplyResult.skipped` — list of `SkippedRecommendation(id, service, outcome: RecOutcome, detail: str)`.
- `RecOutcome` — enum on the skipped entry. No `type` field (that lives on `Recommendation` in the plan, not on the outcome).
- `_run_pr_path` — soft-failure branch raises `SystemExit(1)` internally on `gh pr create` failure (cli.py:312); refactor target.
- `format_summary` — produces the friendly multi-line summary; emits to stdout today.

---

## 3. Decisions

### 3.1 `--json` is additive

When unset, current human-readable behaviour is preserved byte-for-byte. No backward-compat shims, no env-var overrides. Rationale: zero blast radius for existing operators; CI opt-in only.

### 3.2 `--json` requires `--apply-to`

Pre-flight rejects `--json` without `--apply-to` (mirrors the `--pr` check at cli.py:182–183). Standalone `--json` (plan-generation-only JSON) is out of scope. Rationale: the JSON shape is anchored on `ApplyResult`; without apply there is no canonical document to emit. File a follow-up bead if a plan-only JSON surface is needed.

### 3.3 Dataclass-native JSON field names

Emit `outcome` and `detail` on skipped entries (the `SkippedRecommendation` field names), NOT the bead-text's `reason` / `details`. Skip `type` (not on `RecOutcome`; joining from `plan.recommendations` adds complexity for marginal CI benefit). Rationale: same precedent as jmy.23 — code names win over bead text.

### 3.4 `format_summary` still emits to stderr in `--json` mode

In `--json` mode, the human-readable summary is redirected from stdout to stderr; stdout carries only the JSON document. Rationale: zero behavioural surprise for an operator who adds `--json` while debugging — they still see the friendly summary; CI consumes only stdout. No silent loss of diagnostic information.

### 3.5 Partial-failure emits a structured document

If apply succeeds but `gh pr create` fails, stdout still emits a single JSON document with `pr_url: null`, `pr_number: null`, `pr_error: "<captured gh stderr>"`, `exit_code: 1`. CI sees both the apply outcome AND the PR failure structurally — no need to scrape stderr. Rationale: a partial success is the most operationally interesting failure mode for `--apply-to --pr` and the one most likely to need automated reaction.

### 3.6 `--json` suppresses the "PR created: <url>" stdout line

Without `--json`, `_run_pr_path` prints `PR created: <url>` to stdout (current behaviour, preserved). With `--json`, that line is suppressed because it would corrupt the single-document JSON output. The URL is recoverable from `pr_url` in the JSON. Rationale: stdout is JSON-only in `--json` mode; no exceptions.

### 3.7 Minimum refactor for soft PR failure

`_run_pr_path` raises `SystemExit(1)` internally on `gh pr create` failure (cli.py:312). Refactor that single soft-failure branch to return a `PRResult`-with-error to the caller; the caller decides whether to emit JSON (decision 3.5) or re-raise the `SystemExit` (non-JSON path, current behaviour). Hard failures (pre-flight, `git push`) keep their existing `SystemExit` semantics — they fire before apply runs, so there is no `ApplyResult` to emit and no JSON contract to honour. Rationale: smallest possible refactor that unlocks decision 3.5 without restructuring the orchestration.

---

## 4. Wire shape

Canonical success:

```json
{
  "applied": [
    {"id": "rec-abc123def012", "service": "svc-a", "field": "spec.slos.availability.target"}
  ],
  "skipped": [
    {"id": "rec-def456abc789", "service": "svc-b", "outcome": "drift_detected", "detail": "manifest value 99.5 differs from current_value 99.0"}
  ],
  "pr_url": "https://github.com/org/repo/pull/42",
  "pr_number": 42,
  "exit_code": 0
}
```

Partial failure (apply succeeded, PR creation failed):

```json
{
  "applied": [...],
  "skipped": [...],
  "pr_url": null,
  "pr_number": null,
  "pr_error": "gh pr create failed: <captured stderr>",
  "exit_code": 1
}
```

Without `--pr`, the `pr_url` / `pr_number` keys are present with `null` values; `pr_error` is omitted. Field types: `applied[]` and `skipped[]` are lists (possibly empty); `outcome` is a `RecOutcome` value (string); `exit_code` is int; `pr_url` is string or null; `pr_number` is int or null; `pr_error` is string when present.

---

## 5. Out of scope

| Concern | Why deferred |
|---|---|
| Standalone `--json` without `--apply-to` (plan-generation-only output) | The JSON shape is anchored on `ApplyResult`. File a follow-up bead if a plan-only surface is needed. |
| `type` field on `applied` / `skipped` entries | Would require joining each entry against `plan.recommendations` by id. Marginal CI benefit; file follow-up if a consumer needs it. |
| `--json` from `--from` plan parse errors | Parse errors fire early via `SystemExit`; shell `$?` already conveys the failure. JSON is end-of-run only. |
| Streaming / incremental JSON output | The single end-of-run document is the contract. Streaming is a different shape (NDJSON), not a different flag. |

---

## 6. Follow-ups

None expected. jmy.24's `--include` / `--exclude` filtering is independent — the JSON shape covers whatever `ApplyResult` produces, irrespective of which recommendations were filtered in.

---

## 7. References

- Bead: `opensrm-jmy.25`.
- Foundation: `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations`.
- Outcome dataclass: `nthlayer-workers/src/nthlayer_workers/learn/apply.py::ApplyResult` / `SkippedRecommendation` / `RecOutcome`.
- PR result: `nthlayer-workers/src/nthlayer_workers/learn/pr.py::PRResult`.
- Sibling precedent: `nthlayer/docs/superpowers/specs/2026-05-28-jmy23-financial-impact-design.md` (dataclass-native field names rule).
