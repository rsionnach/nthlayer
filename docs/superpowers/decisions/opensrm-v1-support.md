# Decision: opensrm/v1 is migrate-only; srm/v1 is NthLayer's v1 dialect

**Status:** Active.
**Date decided:** 2026-10-22 (opensrm-pnmv).
**Context:** `apiVersion: opensrm/v1` — the published OpenSRM v1 schema
(`opensrm/spec/v1/schema.json`) and every example in `opensrm/examples/` —
fell through `load_manifest` to the legacy parser and failed with
"service.name is required". NthLayer's v1 parser reads `srm/v1`, which differs
from the published schema in nearly every section: judgment SLO nesting,
contract judgment keys, dependency keys, instrumentation, deployment gate keys,
`feedback_latency` bounds, and target units (0–1 ratios vs 0–100).

## Decision

- NthLayer loads two formats: `opensrm.nthlayer.io/v2` (the target) and
  `srm/v1` (NthLayer's own v1 dialect, kept for existing manifests).
- `opensrm/v1` is rejected by `load_manifest` with an error that names the
  supported formats and the migrate command.
- `nthlayer migrate-manifest` converts `opensrm/v1` to v2 following
  `opensrm/spec/v2/AUTHORING.md` §7. Fields with no v2 home are listed as
  *dropped*; the conversion refuses unless `--allow-lossy` is given. Fields
  converted using a value v1 does not declare (calibration's `bins: 10`) are
  listed as *assumed*: they warn but do not refuse (Rob, 2026-10-22).

## Canonical alternative (rejected)

A faithful `opensrm/v1` parser. Rejected: it would be a second v1 dialect,
disagreeing with `srm/v1` on units and keys, for a format v2 already
supersedes and that nothing in the ecosystem produces except the spec's own
examples.

## What's routed to no-ops

Dropped by the conversion (always reported, never silent): v1 judgment SLOs
(`reversal_rate`, `high_confidence_failure` — AUTHORING §7.7 step 8, and
opensrm-a742); throughput SLOs (a rate, not a ratio); SLO types common's
parser cannot type (opensrm-47tt) and maximum-only SLOs; `notifications`,
`deployment`, `observability`, dependency `critical` and `manifest`, and the
other rows the spec's §4 table marks unmapped.

## When the decision unwinds

When opensrm-a742 lands (a v2 judgment-SLO shape both the schema and the parser
accept), v1 judgment SLOs can be converted: move `reversal_rate` and
`high_confidence_failure` from the unmapped table to converted in
`nthlayer_common/manifest/opensrm_v1.py`. When opensrm-47tt lands, the same for
`success_rate`, `processing_time` and `lag`.

## Cross-references

- Spec: `docs/superpowers/specs/2026-10-22-pnmv-opensrm-v1-migration-design.md`
- Code: `nthlayer-common/src/nthlayer_common/manifest/opensrm_v1.py`,
  `parser/loader.py`; `nthlayer-generate/src/nthlayer_generate/cli/migrate_manifest.py`
- Spec map: `opensrm/spec/v2/AUTHORING.md` §7
- Beads: opensrm-pnmv, opensrm-a742, opensrm-47tt
