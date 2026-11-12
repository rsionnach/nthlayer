# The R5 review gate

Every task bead in the NthLayer ecosystem passes the R5 gate before its PR
merges and before `bd close`. R5 is a sequential, multi-lens code review based
on Jeffrey Emanuel's Rule of Five. This file is the versioned description of
it [opensrm-xf73]. The workspace-root `CLAUDE.md` and the skills that run the
gate hold the operational detail; when they disagree with this file, one of
them is wrong and should be fixed, not silently preferred.

> **Pending change: R5 Gate v2.** The change request for this file is
> [`superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md`](superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md).
> Each of its phases amends this description. Until an amendment lands,
> where the two disagree the spec wins (its section 2). The gate mechanism
> moves to cúramóir; Phase A (baseline, replay corpus, finding schema, round
> record, round 0, tree-keyed verdict) is the NthLayer work now.

## The roster (revised 2026-11-12)

| # | Pass | Kind | Asks |
|---|---|---|---|
| 1 | correctness | blocking | Is anything wrong, broken, or a contract mismatch with a caller? |
| 2 | edge-cases | blocking | Empty input, boundaries, concurrency, partial failure, rollback, config edges. |
| 3 | fixture provenance | blocking | Do the tests exercise reality? Mutation kill check, silent skips, fixture shapes traced to the spec. |
| — | clarity | advisory | Naming, structure, stale or misleading comments, duplication. |
| — | excellence | advisory | Docs, API design, conventions, dependencies, compatibility. |

The blocking passes run **in that order, one at a time, never in parallel**.
Each is a fix-loop: review, fix, run the suite, commit, re-review the same
lens, until it reports no CRITICAL or IMPORTANT finding. Three iterations
without converging escalates to a human. MINOR findings are fixed in passing
when trivial and otherwise listed, never looped on.

Clarity and excellence each run **once**, on the final tree, after the three
blocking passes are clean. Their findings are reported and never auto-fixed,
and neither can hold a bead open. A CRITICAL, a FAIL from clarity or a NEEDS
WORK from excellence is escalated as a question, read as a sign that a blocking
lens has a gap.

Clarity became advisory on 2026-11-12 [opensrm-6kqs.11, R5 Gate v2 spec v1.9
Phase A bead 9, R5-R12]. Over corpus-v1's 91 source records it took 256 of the
1,107 sequential model steps, with a fix round in 69 of them, and the table
below shows it raised no CRITICAL in 478 first-review findings. From 2026-08-28
to 2026-11-12 it was the second blocking pass; the archived records of that
period, and the baseline below, show it so.

### Why this order, and why excellence is advisory

Until 2026-08-28 the fourth blocking slot was excellence. The baseline below is
`scripts/r5_baseline.py` run over every archived gate record
(`.claude/r5-state-*-completed.json`, 2026-11-07) [opensrm-6kqs.1]:

86 archived gate records, 63 beads (20 schema v1, 66 v2); excluded: 1 dry run(s), 1 with no lens reviewed.

| pass | records | findings (first review) | CRITICAL | IMPORTANT | MINOR | other | unattributed | re-review findings | reviews | model steps |
|---|---|---|---|---|---|---|---|---|---|---|
| correctness | 86 | 196 | 10 | 49 | 113 | 0 | 24 | 71 | 137 | 194 |
| clarity | 83 | 478 | 0 | 119 | 299 | 0 | 60 | 131 | 156 | 240 |
| edge-cases | 83 | 319 | 14 | 59 | 183 | 0 | 63 | 108 | 164 | 255 |
| provenance | 65 | 228 | 56 | 53 | 90 | 0 | 29 | 76 | 124 | 183 |
| excellence | 82 | 318 | 1 | 31 | 256 | 0 | 30 | 0 | 93 | 110 |
| other passes | 7 | 30 | 0 | 7 | 23 | 0 | 0 | 0 | 7 | 9 |

Sequential model steps per gate: total 991, median 10.5, max 28.

Each row adds up: *findings (first review)* = the four severity columns +
*unattributed*. The severities are the first review's; findings a re-review
raised are counted apart, so a finding re-raised is not counted twice.
*Unattributed* is first-review findings recorded only as a pass total, with no
logged severity: many passes, most v1, recorded nothing else. Model steps are
reviews plus fix rounds, summed over a gate's passes. The script refuses a
record it cannot count without guessing, and then prints no table at all.

**Why the 2026-08-28 table showed 274 findings but 152 severities:** it summed
the passes' first-review totals (274) but the severities logged at every review
(152), so the 150 first-review findings with no logged severity were missing and
the 28 that re-reviews found were added.[^gap]

[^gap]: Over the 21 records that table covered (20 live beads plus the m7su dry
    run), the first reviews logged 124 CRITICAL, IMPORTANT and MINOR:
    274 − 124 = 150, and 150 − 28 = 122, the gap it showed.

On 2026-08-28, over the 20 beads then recorded, all nine CRITICALs came from
correctness and edge-cases, and excellence spent a blocking serial slot to
produce one IMPORTANT in 18 runs. The full record bears it out: first reviews
found 1 CRITICAL in 82 excellence runs and 56 in 65 provenance runs. Meanwhile
the two known escapes cleared every lens, because none asked whether the tests
touched reality:

- **opensrm-oh27** tested `spec.slos` as a list. v1 writes a mapping and v2
  has no such key, so the branch never fired for a real manifest. It survived
  five gate iterations, a 44-fixture suite and two R5 passes, because every
  fixture used the same unreal shape.
- **`test_manifest_v2_archetypes.py`** skipped its whole module when a
  layout-relative path missed, so under one worktree layout the suite stayed
  green while it tested nothing.

The provenance pass took the slot to catch exactly that.

### Sequential, not parallel

A fix made for one lens changes what the next lens reads. Parallel passes
review a diff that is about to change and produce fixes that collide. The
parallel-block hook (below) refuses a second reviewer while one is in flight.

## Fixture provenance, concretely

The provenance pass is largely mechanical, and it is the only pass that
writes to the working tree:

- **Kill check.** Each changed behaviour is broken deliberately (invert a
  condition, drop an argument, return a constant) and the narrowest test
  selection must go red. A mutation that stays green is CRITICAL: that
  behaviour has no test, whatever the coverage says. Briefs give the reviewer
  an explicit, bounded mutation list.
- **Execution check.** New tests must actually run: no SKIPPED among them, no
  module collecting zero, no parametrise list computed at collection time
  without a non-zero minimum.
- **Guard check.** Constructs that can make a test go quiet: module-level
  skips, layout-relative paths, early returns, swallowed exceptions.
- **Provenance.** Every fixture shape is traced to a spec citation or real
  artefact, not to the implementation under test. A negative fixture derived
  from an error message tests the error message.

"I could not run the kill check" is not a pass; it escalates. After the pass
the supervisor checks `git status` itself: a mutation left in place would
otherwise be committed as if it were a fix. Commit a fix **before** running a
kill check on it, since restoring with `git checkout` returns to HEAD.

## Gate before merge — always

Never merge a bead's PR before its gate has run. Measured, same reviewers and
passes, only the order varying:

| bead | order | cost after merge |
|---|---|---|
| opensrm-oh27 | gated, then merged | 0 follow-up PRs |
| opensrm-z3ab | merged, then gated | 2 PRs, 2 Criticals on `main` |
| opensrm-3470 | merged, then gated | 6 PRs, 4 releases, 2 Criticals on `main` |

For a bead spanning `nthlayer-common` and a consumer, gate and release the
common side first, then build the consumer against the released version.

## Running it

- `/r5-supervise <bead-id>` runs the roster above for one bead, from the main
  Claude Code thread (subagents cannot spawn subagents). `--dry-run` replays
  a closed bead against frozen history.
- `/epic-executor <epic-id>` runs it per task inside an epic, after a
  spec-compliance review.
- `/audit-supervise <bead-id>` is a separate, orthogonal audit (security,
  performance, documentation, style), not part of R5.

The pass templates live in `~/.claude/skills/rule-of-five-review/`
(`<pass>-reviewer.md`). `r5-supervise` and `audit-supervise` live in the
workspace root's `.claude/skills/`, `epic-executor` in `~/.claude/skills/`.

### Pre-flight

The supervisor refuses to start against a drifted workspace. It runs
`scripts/eco_doctor.py --fetch` (via the root's `.claude/bin/eco-doctor.sh`)
and aborts on a **range** finding (`STALE`, `LOCK<FLOOR`, `SIBLING>CEILING`,
`NO-CEILING`, `DUPLICATE-NAME`, `DUPLICATE-SCRIPT`, `SIBLING-MISSING`,
`PARSE-ERROR`); **currency** findings (`BEHIND`, `FETCH-FAILED`,
`NO-UPSTREAM`) are logged and do not abort. It classifies by prefix, never by
exit code. A gate run against a sibling older than the declared floor tests
the wrong version and still produces a clean record (opensrm-p3bm).

### Lock and state

- **Lock.** `.claude/hooks/r5-lock.sh` keeps one gate per member repo at a
  time, keyed by `git rev-parse --git-common-dir`, so a worktree contends with
  its parent repo while gates in different repos run concurrently. 15-minute
  lease, refreshed on every dispatch. The helper resolves the lock from the
  current directory, so acquire, refresh and release from inside the repo
  being gated.
- **Parallel-block hook.** `.claude/hooks/r5-parallel-block.sh` runs on every
  subagent dispatch and refuses one while a reviewer from another session is
  in flight. Its window opens when the supervisor logs `reviewer_dispatched`.
- **State.** The audit trail is `<ecosystem root>/.claude/r5-state.json`,
  never a worktree's own `.claude/` (reaping the worktree would delete it,
  untracked and unwarned). A completed run is archived as
  `.claude/r5-state-<bead>[-<part>]-completed.json`.

### What a clean gate means

All three blocking passes ended with zero CRITICAL and IMPORTANT findings, the
suite and lint passed after every fix commit, and the provenance kill checks
ran and went red. The supervisor then closes the bead, unless the bead has
further checkpoints, in which case it stays open and the gate record names
the checkpoint.
