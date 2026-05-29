# `--include` / `--exclude` per-rec Filtering for `learn recommendations` Design (opensrm-jmy.24)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-29. Bead: `opensrm-jmy.24`.

**Foundation:**
- `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_add_recommendations_subcommand` (line 148) and `_cmd_recommendations` (line 183, pre-flight at 187/189, apply at 207).
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::parse_plan_file` — returns a mutable plan with a `recommendations: list[SpecRecommendation]`.
- `nthlayer-workers/src/nthlayer_workers/learn/_apply.py::apply_recommendations` — consumes `plan.recommendations` in order.
- Deterministic rec id mechanism: `compute_rec_id` (shipped in jmy.6); `SpecRecommendation.id` is the stable hash (`rec-<hex>`) operators copy from plan output.

---

## 1. Problem statement

`nthlayer-workers learn recommendations --apply-to <dir>` applies the entire plan in one shot. Operators routinely want to apply a subset — ship the safe ones now, hold a contentious one for review, or re-run with just the failed entry. Today the only workaround is hand-editing the plan file, which destroys the audit trail and loses the deterministic id. jmy.24 adds two flags — `--include` and `--exclude` — that filter `plan.recommendations` by `rec.id` before apply, mutually exclusive, anchored on the deterministic id already printed by jmy.6.

---

## 2. Existing surface

- `_add_recommendations_subcommand` — argparse subcommand builder; current flags include `--from`, `--apply-to`, `--pr`, `--json`, `--output`.
- `_cmd_recommendations` — orchestrator: parse plan, optional `--output` write, optional `--apply-to` apply, optional `--pr` PR path. Pre-flight rejects `--pr`/`--json` without `--apply-to` (cli.py:187/189).
- `SpecRecommendation.id` — deterministic `rec-<12-hex>` id from `compute_rec_id(service, field, current_value, recommended_value)`. Stable across runs against the same plan inputs.
- `apply_recommendations(plan, …)` — iterates `plan.recommendations`; returns `ApplyResult(applied, skipped)`. Empty input → `ApplyResult(applied=[], skipped=[])`, exit_code 0.

---

## 3. Decisions

### 3.1 Two new flags, mutually exclusive

`--include <id>[,<id>...]` and `--exclude <id>[,<id>...]` are added via argparse `add_mutually_exclusive_group`. Argparse owns the mutex error; no hand-rolled check. Rationale: a single rec cannot be both "only this one" and "everything except this one"; the orthogonal modes have orthogonal flags.

### 3.2 Requires `--apply-to`

Pre-flight rejects either flag when `--apply-to` is absent: `error: --include/--exclude requires --apply-to`. Without `--apply-to` there is nothing to filter — the plan is just printed or written. Mirrors the existing `--pr` and `--json` checks at cli.py:187/189. Rationale: filtering a non-apply path is a no-op masquerading as intent; fail loudly.

### 3.3 Unknown id → hard error, list them all

If any id passed to `--include` or `--exclude` does not match a `rec.id` in the parsed plan, raise `SystemExit("error: --include/--exclude id '<id>' not found in plan")` with exit code 2 (same as the other pre-flight failures). Multiple unknown ids are collected and reported in a single message rather than short-circuiting on the first. Rationale: silent dropping of an unknown id would silently change behaviour vs. the operator's mental model; reporting all unknowns at once avoids a fix-one-find-next loop.

### 3.4 Empty effective plan → apply 0, exit 0

When `--exclude` removes every rec (or an `--include` set that, post-pre-flight, somehow produced an empty list — impossible by construction since pre-flight requires every id match), apply runs with an empty `plan.recommendations`. `ApplyResult` already returns exit code 0 for an empty plan, and `format_summary` already emits "Applied: 0 / Skipped: 0" to stderr. This is a legitimate "preview-only" workflow. Rationale: silent no-op is the correct behaviour when the operator explicitly asked to exclude everything; there is no failure to surface.

### 3.5 `--json` reflects the filtered set

When `--include`/`--exclude` is combined with `--json`, the stdout JSON's `applied` and `skipped` arrays cover only the recs that survived the filter. Filtered-out recs do not appear in either array — they are invisible to the apply layer by the time the JSON is built. Rationale: `--json` is anchored on `ApplyResult`; filtering happens upstream of `apply_recommendations` so the JSON contract is honoured by construction.

### 3.6 Filter mechanic: mutate `plan.recommendations` in place

The filter rebinds `plan.recommendations` (or assigns a new list) before calling `apply_recommendations`. `SpecRecommendation` is a mutable dataclass; the rec list lives on the plan and is consumed by reference. No new pathway through apply, no parallel "filtered plan" type. Rationale: smallest possible diff to the apply layer; one mutation point in `_cmd_recommendations` between `parse_plan_file` and `apply_recommendations`.

### 3.7 Help-text wording

```
--include rec-ids (comma-separated) to apply; mutually exclusive with --exclude
--exclude rec-ids (comma-separated) to skip; mutually exclusive with --include
```

Rationale: short, symmetric, names the mutex partner inline so `--help` is self-explanatory.

---

## 4. CLI example

```
nthlayer-workers learn recommendations \
    --from plan.yaml \
    --apply-to specs/ \
    --include rec-abc123def012,rec-def456abc789
```

Equivalent exclude form:

```
nthlayer-workers learn recommendations \
    --from plan.yaml \
    --apply-to specs/ \
    --exclude rec-9deadbeef000
```

Combined with `--json` (filtered set reflected in the document):

```
nthlayer-workers learn recommendations \
    --from plan.yaml \
    --apply-to specs/ \
    --exclude rec-9deadbeef000 \
    --json
```

---

## 5. Out of scope

| Concern | Why deferred |
|---|---|
| Interactive selection TUI | jmy.22 owns the per-rec interactive flow; jmy.24 is the non-interactive CLI surface. |
| Regex / glob patterns for id matching | Exact id match keeps the audit trail crisp; revisit if a user reports a real need. |
| "Apply N of M" prompt | No interactive prompting in this bead; CLI flags only. |
| Filtering by `recommendation.type` or `recommendation.service` | Id-based selection only for this bead. Filtering by type/service is a different shape (predicate over the plan, not a discrete set) — file a follow-up if requested. |

---

## 6. Follow-ups

- `opensrm-jmy.22` — interactive per-rec selection (TUI / prompt). Cross-references this bead as the non-interactive sibling.

---

## 7. References

- Bead: `opensrm-jmy.24`.
- Foundation: `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations`.
- Plan parser: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::parse_plan_file`.
- Apply layer: `nthlayer-workers/src/nthlayer_workers/learn/_apply.py::apply_recommendations`.
- Deterministic id: `compute_rec_id` (shipped in jmy.6).
- Sibling precedent: `nthlayer/docs/superpowers/specs/2026-05-29-jmy25-json-output-design.md` (pre-flight pattern, additive-flag rule).
