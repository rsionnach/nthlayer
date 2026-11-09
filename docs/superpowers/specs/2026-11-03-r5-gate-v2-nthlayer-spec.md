# R5 Gate v2 NthLayer Spec

Nov 3, 2026 · @Rob

cúramóir owns the R5 gate mechanism from here on; NthLayer's job is to measure the gate it has, hand cúramóir the material to prove the new one against, and later become a caller. Phase A is the work to do now: a baseline from the twenty archived gate records, a replay corpus built from them, and the finding schema and round record wired into the existing sequential skills. Phase B is a skill-level prototype of the batched gate, to be done only if cúramóir's Epic 5 is more than six weeks out. Phase D is the hand-over. Nothing here touches product code.

## 1. Summary

The gate as described in `opensrm-xf73` runs four blocking lenses one at a time, each in a review-fix-suite-commit-re-review loop, then excellence once, advisory. It is slow for a reason that no longer holds: the sequential order exists to stop fixes from different lenses colliding, and fixes collide only when each lens owns a fixer. cúramóir is building the batched form (four read-only reviews of one SHA, one fixer, every lens verifying the final tree, provenance mutations in worktrees). This agent's part is smaller and comes first.

**Now (Phase A).** Extract the baseline from the archived `r5-state-*-completed.json` files at the ecosystem root, resolving the discrepancy in the gate description's own table (severity columns sum to 152, findings column to 274). Build the replay corpus from those twenty beads in the section 6 layout and hand it to cúramóir. Wire the section 6 finding schema into the reviewer templates and the round record into `r5-state.json`, keeping dispatch sequential, so the existing gate starts producing records the new one can be compared against. Add round 0 and the tree-keyed verdict.

**Conditional (Phase B).** If cúramóir's Epic 5 is more than six weeks from landing, prototype the batched gate in `r5-supervise` itself: parallel dispatch, a single fixer, a verify round, the hook rekey. Prompt-and-hook work, two or three evenings, replaced by cúramóir's gate in Phase D. Worth it only on that timeline; skip it otherwise.

**Later (Phase D).** When cúramóir's gate passes the replay test, `r5-supervise` becomes a thin call into `curamoir run gate`, the NthLayer hooks become compatibility shims that read cúramóir's record, and the gate description points at the cúramóir spec.

**Not this agent's.** Phase C (the mutation runner, worktrees, the provenance reviewer rewrite): that is Python and is built once, in cúramóir. Anything that changes dispatch before Phase B is approved. Anything in the seven product repos' source trees.

## 2. Constraints

- **Skills, hooks and records only.** The files this spec may change: the gate description (`opensrm-xf73`), `r5-supervise` and `epic-executor` (stage 2 only), the pass templates in `~/.claude/skills/rule-of-five-review/`, `.claude/hooks/r5-lock.sh`, `.claude/hooks/r5-parallel-block.sh`, `.claude/r5-state.json` and its archive, and a new `scripts/r5_baseline.py` plus `scripts/r5_corpus.py` at the ecosystem root. No file under any member repo's `src/`, `spec/` or `tests/` changes under this spec.
- **Sequential dispatch stays until Phase B is approved.** Phase A changes what the gate records, not how it runs. The parallel-block hook, the lock and the lens order are untouched in Phase A.
- **The gate description is the versioned source.** Each phase amends it; this spec is the change request. Where this spec and the description disagree before the amendment lands, this spec wins.
- **Pre-flight is untouched.** `eco_doctor --fetch` with its abort classes runs before any gate, in every phase.
- **Gate before merge, gate before close.** Nothing here moves either.
- **Lock scope is untouched in every phase.** `r5-lock.sh` keys on `git rev-parse --git-common-dir` and is held for the whole gate. Decided 2026-11-03; the concurrency that matters comes from the hook rekey in Phase B, not the lock.
- **Record compatibility.** Every field the twenty archived records carry today is kept, so old and new records compare.

## 3. Phase A, now

Seven beads under one epic, `r5-v2-phase-a`, in this order. Each closes on the acceptance beside it. Requirement ids match the cúramóir spec so the two can be read together.

1. **Baseline (R5-R0).** `scripts/r5_baseline.py` reads every `.claude/r5-state-*-completed.json` and prints, per bead and per lens: iterations run, findings by severity per iteration, model steps on the critical path (reviews + fixes + re-reviews, in dispatch order), and the lens order used. It explains the 152-versus-274 discrepancy in the gate description's table: either a fourth severity bucket or a findings column that counts re-reviews. *Closed when* the table in the gate description is replaced by the script's output and the discrepancy has a one-sentence explanation beside it.
2. **Replay corpus (section 6 layout).** `scripts/r5_corpus.py` writes `fixtures/r5-replay/<bead>/` for each of the twenty beads: `meta.json` (with `sequential_steps` from bead 1 and `escape: true` on `opensrm-oh27` and the `test_manifest_v2_archetypes.py` bead), `brief.md`, `bundle.git` (base and head reachable), `diff.patch`, `recorded.json` (the recorded findings re-encoded in the section 6 finding schema, grouped per lens per iteration, the escaped finding under `escaped` for the two marked beads). *Closed when* every entry's bundle checks out at its `head`, every recorded CRITICAL and IMPORTANT appears in `recorded.json` with a path and a range, and the directory is delivered to the cúramóir repository as `fixtures/r5-replay/` (one PR there, no other change). Publication rule (settled 2026-11-07): an entry carries only what is derived from public repository content (code, the diff, a brief already in the repo, the reviewer findings about that code); the gate record's free-text notes, rulings and session fields never enter the corpus or any fixture, and recorded.json is built from findings alone. Test fixtures in any public repo are synthetic (same structure and numbers, invented ids and timestamps), never trimmed real records.
3. **Finding schema in the templates (R5-R11, R5-R12).** Each `<pass>-reviewer.md` ends its output with `R5-FINDINGS:` and a JSON array in the section 6 schema; `r5-supervise` parses it and refuses a reviewer whose last line is not that (`UNAVAILABLE`, retried once, then blocking). Severity-to-blocking policy stays as the description has it; excellence never blocks. *Closed when* a gate on a live bead produces parsable findings from all five lenses and `r5-supervise --dry-run` on three corpus entries reproduces their recorded findings through the new parser without loss.
4. **Round record (R5-R48).** `r5-state.json` gains `rounds[]` in the section 6 shape; each sequential lens iteration is one `review` or `verify` round with one lens in `lenses`, and each fix is a `fix` round. Existing top-level fields are kept. The archive keeps its name. *Closed when* a completed gate's archive validates against the shape and bead 1's script reads old and new archives alike.
5. **Round 0 (R5-R1).** Before the first reviewer, `r5-supervise` runs lint, the type check and the full suite on `BASE..HEAD` and ends the gate as `PREFLIGHT_FAILED` with the tool output in the record when any fails. The provenance mechanical checks (R5-R33: SKIPPED or deselected new tests, zero-collecting changed modules, collection-time parametrise without a minimum, module-level skips, layout-relative paths, early returns in test bodies, swallowing excepts) run here as a script, `scripts/r5_provenance_checks.py`, and any hit is a blocking provenance finding in the record. *Closed when* the two escape corpus entries fail round 0 with no model dispatched.
6. **Tree-keyed verdict (R5-R49).** The record's `verdict` carries `tree_sha` (`git rev-parse HEAD^{tree}`) and `head_sha`. The close path in `r5-supervise` and `epic-executor` (`bd close`) and the PR merge check compare the branch's current tree to `tree_sha` and refuse on mismatch, naming it. *Closed when* a content-free rebase keeps a clean verdict and a one-line change after the gate refuses `bd close`.
7. **Gate description amendment, part 1 (R5-R62).** The roster table gains the baseline from bead 1 in place of the 274-row table; a "Records" section states the finding schema and the round record by reference to section 6; the pre-flight section gains round 0; the "What a clean gate means" section gains the tree key. The "Sequential, not parallel" section is left as it is until Phase B or D. *Closed when* the description, `r5-supervise` and the templates agree, as the description itself requires.

**Corpus fidelity (settled 2026-11-09).** The archived records hold severity counts, never a claim, path or range, so each entry carries a `fidelity`: *recorded* (the reviewer's own findings, extracted from its report and accepted only where every blocking iteration's CRITICAL and IMPORTANT counts equal the archive's), *derived* (path and range from the lens's fix-commit hunks, claim from its severity bullet, one-to-one only), *clean* (no blocking findings recorded) or *counts_only* (per-lens severity counts, lens order, iteration count and `sequential_steps`, nothing finer). Every derived or recorded finding is `verification_level: asserted`. An entry is one gate record and repo (ruling of 2026-11-09), and the 131 entries over 65 beads, as `scripts/r5_corpus.py` builds them, split 18 recorded (16 beads), 0 derived, 12 clean (4 beads with no other entry) and 101 counts_only. No fix commit names the one file each blocking bullet is about, so none is derived; a v1 record that logged only totals may hide a blocking finding, so it is counts_only, never clean. (The first count, by bead before entries were split, was 14 recorded, 3 derived, 16 clean and 33 counts_only.) The planned floor of twenty beads with blocking findings at recorded or derived fidelity is not met (16), so it is dropped: the replay is a regression test on what exists plus the two escape fixtures, recall (R5-R58) runs on recorded and derived entries only, where claim equivalence decides and an equivalent claim at a different location counts as recalled and is logged `location_mismatch`; the step ratio (R5-R60) runs on every entry; counts_only entries give a count-floor telemetry line, never a gate; and clean entries give a clean-bead blocking rate (a blocking finding on a bead the sequential gate passed is a catch or noise, adjudicated by a human for the first few), the precision figure recall cannot give. **The recall acceptance for Phase B is the ten-bead shadow period (R5-R61)**, not the corpus. The reviewer reports the recorded entries come from are kept in a private archive, never in the corpus. `fidelity` in `meta.json` is an addition to the section 6 layout, so it is to be made in both specs.

**Phase A acceptance, as a whole.** `r5-supervise --dry-run` over every recorded and derived corpus entry, with the new parser and record, loses no recorded CRITICAL or IMPORTANT (R5-R58 in its schema-only form). Any loss blocks hand-over of the corpus until explained.

## 4. Phase B, conditional

Do this only if cúramóir's Epic 5 is more than six weeks from landing when Phase A closes. It is a prototype in the skill, replaced in Phase D; its value is the speed-up while NthLayer work continues daily and the live shadow evidence cúramóir will otherwise have to produce for itself. If Epic 5 is closer than that, skip to Phase D.

What Phase B changes in `r5-supervise`, in bead order:

1. **Parallel round 1 (R5-R2).** The four blocking lenses are dispatched from the main thread as four `Agent` calls in one message, same `BASE`, `HEAD`, brief and plan, each with its template. Provenance in Phase B is the *judgment* reviewer only (R5-R35: mutation coverage, fixture tracing, spec-versus-implementation assertions), reading by SHA. Its kill checks stay as they are today, run in the real checkout with the commit-first and `git status` safeguards, but serialised *after* the other three lenses return and *before* the merge, so nothing mutates a checkout while reviewers read it. *Closed when* a live bead's round 1 record shows four lenses with overlapping `started`..`ended` windows.
2. **Merge (R5-R13 to R5-R17).** A script, `scripts/r5_merge.py`: dedupe overlapping ranges with the same normalised claim; sort by severity then lens order correctness, edge-cases, provenance, clarity; MINOR to the deferred list; write the merge decisions into the round record. The supervisor never merges by reading. *Closed when* the merge of three corpus entries' round-1 output is byte-identical on two runs.
3. **Single fixer (R5-R18 to R5-R23).** One fix subagent per fix round with the fix list, the deferred list, the brief, the plan and the full diff; never the raw reviewer text. It works in priority order, marks a conflicting lower-priority finding `superseded`, edits only files named in the fix list and their tests, adds no dependency and changes no public signature unless a finding's `fix` says so, and reports per finding `fixed`, `superseded`, `could_not_fix` or `disputed`. One commit per round after the suite passes, carrying the bead id and `r5-round: n`. In Phase B the scope check is the supervisor diffing the commit against the fix list's paths; the full `check_scope` lives in cúramóir. *Closed when* a planted finding naming a file the fixer then edits beyond is reported as `scope_breach` in the record.
4. **Verify round (R5-R24 to R5-R29).** After a fix round, all four blocking lenses and excellence run in verify mode: full `BASE..HEAD` diff at the new HEAD, each lens's own prior findings with the fixer's statuses, the fix commit. Each prior finding comes back `resolves`-closed with cited lines or re-raised; new findings on the fix round's changes carry `regression: true`. The verify section is appended to each template by the supervisor, not a second template. Excellence runs here (or in round 1 when round 1 is clean), deferred, advisory. *Closed when* a planted regression in a fix commit is raised with `regression: true` by the lens whose domain it is.
5. **Cap (R5-R7).** Three fix rounds without a clean verify ends the gate `ESCALATED` with every round in the record; nothing reverted. Replaces three iterations per lens.
6. **Hook rekey (R5-R47).** `r5-parallel-block.sh` reads an `in_flight` set in `r5-state.json` recording (`bead`, `HEAD`, `lens`, `session`, `dispatched_at`) and refuses a dispatch only when a fix round is in progress for the same branch, or the same lens for the same bead and HEAD is already in flight. The lock is untouched. *Closed when* a second session can dispatch subagents on a different bead while a gate's round 1 is in flight, and cannot while its fix round is.
7. **Tiers (R5-R55, R5-R56).** Per-lens `model` and `effort` in the subagent frontmatter: correctness, edge-cases, provenance and the fixer on the strong model; clarity and excellence on the cheaper one in both modes. `subagentPromptCacheTtl: 1h` in settings so the four reviewers share the cached prefix. Cross-vendor review is not available to Claude Code subagents, so no second model family is used in Phase B; that arrives as cúramóir's sampling audit in Phase D, when a provider adapter exists.
8. **Gate description amendment, part 2.** The "Sequential, not parallel" section is replaced by a "Rounds" section stating beads 1 to 6; the lock-and-state section gains the `in_flight` set and the hook rule.

**Phase B acceptance.** Replay (R5-R58), a regression test since 2026-11-09 (the recall acceptance is the shadow period below): over every recorded and derived corpus entry, batched round 1 reports every recorded CRITICAL and IMPORTANT with the same path, an overlapping range and an equivalent claim (judged by a cheap-tier call that has seen neither run). Steps (R5-R60): critical-path model steps at most a third of `sequential_steps`. Shadow (R5-R61): the first ten live beads run the sequential gate as well, after the batched one, on the same `BASE..HEAD`; the record carries both; any blocking finding the sequential gate raised that the batched one did not is an incident, explained before the next bead. No early stop on a clean run of five.

**Telemetry added to the record in Phase B:** rounds to clean; per lens per round findings by severity, `UNAVAILABLE`, tokens, duration, MINOR against blocking; `superseded` per bead beside the correctness fix count; `regression: true` per bead by raising lens and causing lens.

## 5. Phase D, later

Starts when cúramóir's gate passes the replay test on the corpus (its E5-R26 and R5-R58). From then there is one implementation and two callers.

1. **Thin supervisor.** `r5-supervise <bead>` resolves `BASE` and `HEAD` as today (explicit `--base`/`--head` still honoured), runs `eco_doctor --fetch` as today, then calls `curamoir run gate --repo <member repo> --bead <id> --base <sha> --head <sha> --branch <name> --brief <path>` and reads the record it writes. The fix loop, the merge, the templates and the kill checks are no longer in the skill. `epic-executor` stage 2 makes the same call. `--dry-run` becomes `curamoir run gate --dry-run --corpus`.
2. **Hook shim (R5-R63).** `r5-parallel-block.sh` and the close and merge checks accept cúramóir's record (section 6 verdict check: `verdict.state` is `CLEAN` and the branch's `HEAD^{tree}` equals `verdict.tree_sha`) as equivalent to their own clean record, so whichever gate ran, `bd close` and the merge gate read one answer. During the overlap both NthLayer's hook and cúramóir's gate guard exist; the NthLayer hook defers to the cúramóir record when one is present for the tree.
3. **Shadow period (R5-R61).** The first ten live beads gated through cúramóir also run NthLayer's sequential gate (or the Phase B batched one, if it was built) on the same `BASE..HEAD`; the record carries both. A blocking finding the NthLayer gate raised that cúramóir's did not is an incident, explained before the next bead.
4. **Hook removal.** After ten clean shadow beads, `r5-parallel-block.sh` is removed, `r5-lock.sh` is removed (cúramóir's job lock covers the gate), the templates in `rule-of-five-review/` are archived with a pointer to cúramóir's, and `r5-state.json` stops being written; cúramóir's `.curamoir/state/r5/` is the record.
5. **Gate description, final amendment.** The description becomes a short page: roster, severities, gate-before-merge, the pre-flight, and a pointer to the cúramóir spec for the mechanism. The baseline table and the escape history stay, as the reason the gate exists.

## 6. Shared contract with cúramóir

This section is word-for-word the same in the cúramóir spec. A change to it is made in both or in neither.

**Finding.** One object per finding; a reviewer's last output line is `R5-FINDINGS:` followed by a JSON array of them.

```json
{
  "lens": "correctness | clarity | edge_cases | provenance | excellence",
  "severity": "CRITICAL | IMPORTANT | MINOR",
  "path": "src/opensrm/parser/v2.py",
  "start_line": 118, "end_line": 131,
  "claim": "one sentence: what is wrong",
  "evidence": "the lines, or the test output, that show it",
  "fix": "one sentence: what would resolve it, or null",
  "fingerprint": "first 16 hex of sha256(lens|path|normalised claim)",
  "verification_level": "asserted | cited | walked | script | reproduced",
  "resolves": "fingerprint of the prior finding this closes, or null (verify mode)",
  "regression": false,
  "status": "open | fixed | superseded | could_not_fix | disputed | fixed_in_passing"
}
```

`status` is set by the fixer, never by a reviewer. `normalised claim` is lower-cased, whitespace-collapsed, with line numbers and SHAs removed. verification\_level is the E5-R11 ladder from the v0.4 spec, with evidence as its proof; a blocking finding below the configured floor (default script) is labelled UNPROVEN in the record and the brief, still blocks, and the fixer verifies or disputes it before fixing it.

**Closures (verify mode).** A record with `resolves` set is a closure, not a finding. It is never counted toward termination, whatever `severity` it carries (copy the original's); its `path`, `start_line`, `end_line` and `evidence` are the resolving lines and its `claim` is why the prior finding no longer holds. A closure is valid only if `resolves` names a fingerprint in the previous round's open set and `evidence` is non-empty; an invalid closure is ignored and logged `closure_rejected` with the reason, and a second closure of the same fingerprint is dropped. The closure's own fingerprint is never compared to `resolves`. A re-raised finding is the prior record copied verbatim (path, claim, fingerprint) with no `resolves`. The next round's open set is the previous open set minus valid closures, plus new and re-raised findings. A prior open finding with neither a closure nor a re-raise is carried forward unchanged and tagged `unaccounted`: silence never closes. Unaccounted count per lens per round is a telemetry line, and a lens that closes every prior finding with empty `evidence` is `UNAVAILABLE` (R5-R25). (Settled 2026-11-07, from cm-70j.)

**Round record.** Existing top-level fields of NthLayer's `r5-state.json` are kept; these are added.

```json
{
  "bead": "opensrm-6w9d", "repo": "opensrm", "branch": "feat/6w9d",
  "base": "<sha>", "head": "<sha>",
  "rounds": [
    {
      "n": 1, "kind": "preflight | review | fix | verify", "head": "<sha>",
      "started": "<iso8601>", "ended": "<iso8601>",
      "lenses": {
        "correctness": {"model": "<id>", "tier": "deep", "mode": "review | verify",
                         "tokens_in": 0, "tokens_out": 0, "duration_s": 0,
                         "status": "ok | UNAVAILABLE | skipped", "skip_rule": null,
                         "findings": []}
      },
      "merge": {"fix_list": ["<fingerprint>"], "deferred": ["<fingerprint>"], "deduped": [["<a>", "<b>"]]},
      "fix": {"commit": "<sha>", "statuses": {"<fingerprint>": "fixed"}, "scope_breaches": []},
      "mutations": [{"path": "", "mutation": "", "result": "red | green | stale | inconclusive", "worktree": ""}]
    }
  ],
  "verdict": {"state": "CLEAN | ESCALATED | PREFLIGHT_FAILED | BUDGET",
              "tree_sha": "<sha>", "head_sha": "<sha>", "at": "<iso8601>"}
}
```

**Verdict check.** A close, push or merge gate passes when `verdict.state` is `CLEAN` and `git rev-parse HEAD^{tree}` equals `verdict.tree_sha`. Anything else refuses, naming the state or the mismatch.

**Mutation block.** In the brief's markdown, one fenced block with the info string `r5-mutations`:

```yaml
- path: src/opensrm/parser/v2.py
  locate: {lines: [118, 131]}          # or {anchor: "def classify("}
  mutation: invert_condition           # invert_condition | drop_argument | return_constant
                                       # | delete_statement | swap_operator | {replace: {from: "", to: ""}}
  expect_red: "python -m pytest tests/test_parser_v2.py::test_judgment_slo_mapping -q"
```

**Replay corpus.** One directory per recorded bead.

```
fixtures/r5-replay/<bead>/
  meta.json        bead, repo, base, head, tree_sha, roster version, sequential_steps (model steps on the recorded critical path), escape: true|false
  brief.md         the bead's brief as given to the reviewers, mutation block included if it had one
  bundle.git       git bundle with base and head reachable, so replay needs no network
  diff.patch       git diff base..head, for readers without git
  recorded.json    the sequential gate's findings in the Finding schema, grouped per lens per round, with the lens order and iteration count
```

`escape: true` marks the two beads whose recorded findings missed something later found (`opensrm-oh27`; the `test_manifest_v2_archetypes.py` module skip); `recorded.json` for those also carries the missed finding under `escaped`.

## 7. Decisions already made

Settled on 2026-11-03 against the full spec; not to be reopened during implementation.

| Decision | Binds |
| --- | --- |
| Verdict keyed to the tree SHA, not the commit | Phase A bead 6 |
| A lens that fails twice is `UNAVAILABLE` and blocks; no waiver path | Phase A bead 3 |
| Three fix rounds total, then escalate | Phase B bead 5 |
| No in-checkout mutation path once cúramóir's runner exists; until then the old safeguards stay, serialised after the other lenses | Phase B bead 1, Phase D |
| Clarity on the cheap tier in both modes, with the MINOR-rate telemetry line | Phase B bead 7 |
| Lock held for the whole gate, keyed on the git common dir, in every phase | section 2 |
| Mutation list is a fenced `r5-mutations` block in the brief | section 6 |
| Shadow period of ten live beads, no early stop | Phase B and Phase D |
| Excellence stays advisory, runs once on the final tree | Phase B bead 4 |
| No batching across beads; no landing on main before the gate | section 2 |
| Phase B is built only if cúramóir's Epic 5 is more than six weeks out | section 4 |
| No cross-vendor review on NthLayer in any phase; it arrives as cúramóir's sampling audit (one gate in ten, never blocking) once a provider adapter exists. (Added 2026-11-05.) | Phase B bead 7, Phase D |
| The v0.4 verification ladder (E5-R11) joins the shared finding schema as verification\_level; UNPROVEN findings still block. Phase A bead 3 adds the field to the templates; recorded.json entries without it carry asserted. (Added 2026-11-07.) | section 6, Phase A bead 3 |
| Corpus fidelity recorded / derived / clean / counts\_only; no floor; Phase B recall acceptance is the shadow period (R5-R61), the corpus a regression test. (Added 2026-11-09.) | Phase A bead 2, Phase B acceptance |
