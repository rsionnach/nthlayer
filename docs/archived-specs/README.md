# Archived specifications

These specifications are archived as of 2026-05-04. They are historical
record, not authoritative current architecture. See
[`docs/specs/`](../specs/) for the current corpus and
[`docs/roadmap/`](../roadmap/) for proposed/upcoming features.

## Why archived

Specifications land here for one of three reasons:

1. **Superseded by a newer version.** A later spec replaces this one and
   describes the current behaviour. Examples:
   - `NTHLAYER-SERVE-MODE-V2.md` → superseded by
     [`docs/specs/NTHLAYER-SERVE-MODE-v2.1.md`](../specs/NTHLAYER-SERVE-MODE-v2.1.md)
   - `NTHLAYER-BENCH-V2.md`, `NTHLAYER_BENCH_SPEC.md` → superseded by
     [`docs/specs/NTHLAYER-BENCH-v2.1.md`](../specs/NTHLAYER-BENCH-v2.1.md)
   - `SERVE-MODE-SPEC.md` (the original v1) → superseded by V2 → v2.1

2. **Component absorbed during consolidation.** The deprecated repos
   (nthlayer-observe, nthlayer-correlate, nthlayer-measure,
   nthlayer-respond, nthlayer-learn) were folded into nthlayer-workers
   on 2026-04-26. Specs describing those standalone components in their
   pre-consolidation form are archived here. The corresponding v1.5
   specs in [`docs/specs/`](../specs/) describe the current
   consolidated implementation.
   - `NTHLAYER-OBSERVE-SPEC.md` — pre-consolidation observe component

3. **Proposal that shipped (or is no longer proposed).** One-time
   proposals are archived once the work lands or is dropped. Examples:
   - `DEMO-IMPROVEMENT-SPEC.md` — proposed via opensrm-42y; shipped
   - `MAYDAY.md`, `BRIEF.md`, `ECOSYSTEM-GAPS.md`, etc. — earlier
     drafts and competitive analyses preserved for context

## Citing an archived spec

Archived specs may still be referenced from active design docs in
[`docs/superpowers/specs/`](../superpowers/specs/). Treat archived
specs as a frozen snapshot of the thinking at their time; current
behaviour is defined by [`docs/specs/`](../specs/).

If you find an archived spec referenced from current code or
documentation in a way that suggests it's still authoritative, that's
a bug — please file a follow-up.
