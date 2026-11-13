# R5 Gate v2 — NthLayer specification

**Status:** v1.11, 2026-11-13. Supersedes the 3 November hand-off and every inline amendment since, including the 9 November corpus-fidelity paragraph, which is folded into Phase A bead 2 below. From here, a change is a dated entry in §8, made in this file and mirrored in the cúramóir spec in the same pass.
**Scope:** NthLayer's part of the move to the batched R5 gate: the baseline and corpus now (Phase A), a skill-level batched gate only if cúramóir's Epic 5 is far off (Phase B), and the hand-over (Phase D). The mechanism is specified in cúramóir's `docs/r5-gate-v2-curamoir-spec.md`.
**Binds:** `docs/r5-gate.md` (the versioned gate description, `opensrm-xf73`), `r5-supervise`, `epic-executor` stage 2, the lens templates in `~/.claude/skills/rule-of-five-review/`, the ecosystem root's `.claude/hooks/r5-lock.sh`, `r5-parallel-block.sh` and `r5-state.json`, `scripts/r5_baseline.py` and `scripts/r5_corpus.py`. No file under any member repository's `src/`, `spec/` or `tests/`.

---

## 0. Assumptions still open

| # | Assumption | Discharged by |
|---|---|---|
| A1 | ~~The lens templates can emit `R5-FINDINGS:` on the last line without losing review quality.~~ Discharged 2026-11-12: 15 of 15 dry-run reports and all 8 reports of the first live gate (6kqs.3) parsed first time, `prose_unfiled` 0, and agreement across variants (0.23 any severity, 0.24 blocking) inside the spread within one variant (0.27 to 0.28 before, 0.18 to 0.27 after). Agreement ignoring severity equals agreement on blocking findings, so the runs differ in what they find, not in how they rate it. | None. |
| A2 | ~~Synthetic per-repo bundles come out small enough for a corpus store without LFS.~~ Discharged 2026-11-09: 122 MB in total, opensrm 112 MB; bundles are release assets on this repository under `corpus-v*` (§6). | Done. |
| A3 | ~~Surviving transcripts yield briefs that can be isolated verbatim.~~ Discharged 2026-11-09: reviewer prompts for 87 entries, bead descriptions for 44. | Done. |
| A4 | Phase B's parallel dispatch from the main thread works with the existing `r5-parallel-block.sh` once rekeyed; Claude Code's 20-subagent limit is never reached (five reviewers at most). | Phase B bead 1 and 6, if Phase B runs. |
| A5 | `cleanupPeriodDays` has been raised so the next twenty gates' reviewer outputs survive for the shadow period. | You, today; `/curamoir:doctor` will warn once the `harness` principle for it exists. |
| A6 | The baseline (86 records, 63 beads, 2026-11-07) and the corpus (134 entries, 66 beads at `corpus-v1`) describe the same archive; the two extra beads are either the two records the baseline excludes carried as counts_only, or gates run between the two dates. | Phase A bead 2, before the corpus PR: re-run `r5_baseline.py` over the archive snapshot the corpus was built from, publish both figures with their dates in `docs/r5-gate.md`, and state which explanation holds. |
| A7 | `curamoir run mutations` can be called from where `r5-supervise` runs, against a member repository's checkout, with cúramóir installed there. | Phase A bead 10; if it cannot, the bead waits for Phase D. |

## 1. Summary

The gate described in `docs/r5-gate.md` runs four blocking lenses one at a time, each a review-fix-suite-commit-re-review loop, then excellence once, advisory. Over the full record (86 gate records, 991 sequential model steps, median 10.5 per gate) it is slow for a reason that no longer holds: the order exists to stop fixes from different lenses colliding, and fixes collide only when each lens owns a fixer. cúramóir is building the batched form. This agent's part is smaller and comes first.

**Done (Phase A beads 1 and 8).** The baseline is published in `docs/r5-gate.md` from `scripts/r5_baseline.py`, with the 274-versus-152 discrepancy explained, and its fixtures are synthetic. Over the record, provenance produced 56 of the 81 first-review CRITICALs; clarity none in 478 findings. The "nine CRITICALs from correctness and edge-cases" was a 20-bead sample.

**Nearly done (Phase A bead 2).** The corpus. The archives hold severity counts, not findings, so every entry carries a fidelity (§6). Published as `corpus-v1` (tag at 83fa711): 134 entries over 66 beads; 23 recorded entries (16 beads), 84 blocking findings with a location and the rest with a claim only; 0 derived; 111 counts_only. Briefs from reviewer prompts for 87 entries, bead descriptions for 47. The planned floor was not met and is dropped; the recall acceptance for Phase B is the ten-gate shadow period, and the corpus is a regression test. What remains is the PR of `fixtures/r5-replay/` and `bundles.json` to cúramóir.

**Next (Phase A beads 3 to 7, 9 and 10).** Clarity becomes advisory now (bead 9), and listed kill checks run through cúramóir's mutation runner as soon as it exists (bead 10). Then the finding schema in the templates, the round record, round 0, the tree-keyed verdict, and the first amendment of the gate description, all with dispatch still sequential.

**Conditional (Phase B).** If cúramóir's Epic 5 is more than six weeks from landing when Phase A closes, prototype the batched gate in `r5-supervise`: parallel dispatch, a single fixer, a verify round, the hook rekey. Prompt-and-hook work, replaced in Phase D. Otherwise skip to Phase D.

**Later (Phase D).** `r5-supervise` becomes a thin call into `curamoir run gate`; the hooks become compatibility shims that read cúramóir's record; the gate description points at the cúramóir spec.

**Not this agent's.** Phase C (the mutation runner, worktrees, the provenance reviewer rewrite): Python, built once, in cúramóir; calling its mutation runner from `r5-supervise` is this agent's (Phase A bead 10). Nothing new enters either spec until the shadow period reports: the parked list and each item's trigger are in the cúramóir spec, §10. Anything that changes dispatch before Phase B is approved. Anything in the member repositories' source trees.

## 2. Constraints

- **Skills, hooks, scripts and records only.** The files §Binds lists, plus `scripts/r5_provenance_checks.py`. The ecosystem root is not a git repository (front-door CLAUDE.md rule 5), so the hooks there stay unversioned; everything that can live in the `nthlayer` repository does.
- **Sequential dispatch stays until Phase B is approved.** Phase A changes what the gate records, not how it runs. The parallel-block hook, the lock and the lens order are untouched in Phase A. Two exceptions from v1.9, both Rob's decisions of 2026-11-12: clarity moves to the advisory roster (bead 9), and provenance's listed kill checks move to cúramóir's runner (bead 10).
- **The gate description is the versioned source.** Each phase amends it; this spec is the change request, linked from the description's pending-change note. Where they disagree before an amendment lands, this spec wins.
- **Pre-flight is untouched.** `eco_doctor --fetch` with its abort classes runs before any gate, in every phase.
- **Gate before merge, gate before close.** Nothing here moves either.
- **Lock scope is untouched in every phase.** `r5-lock.sh` keys on `git rev-parse --git-common-dir` and is held for the whole gate. The concurrency that matters comes from the hook rekey in Phase B, not the lock.
- **Record compatibility.** Every field the archived records carry today (`supervisor`, `version`, `target_bead`, `started_at`, `dry_run`, `passes`, `advisory_passes`, `status`, `completed_passes[]`, `audit_trail[]`) is kept, so old and new records compare and `r5_baseline.py` keeps reading both.
- **Publication rule.** §6. Nothing from a gate record's notes, rulings or session fields reaches a public repository, in a fixture or in the corpus.

## 3. Phase A

Seven beads under `opensrm-6kqs`, in this order; beads 1 and 8 are closed. Each closes on the acceptance beside it. Requirement ids match the cúramóir spec.

1. **Baseline (R5-R0).** Closed 2026-11-07. `scripts/r5_baseline.py` reads every `.claude/r5-state-*-completed.json` and prints, per record and per lens, reviews, findings by severity per review, model steps, lens order; `--json` feeds the corpus's `sequential_steps`. Known-data tables (`BLOCKED_DISPATCHES`, `PASSLESS_EVENTS`) hold the archive keys the format cannot distinguish; the script refuses a record it cannot count without guessing. The gate description carries the table.
2. **Replay corpus (§6 layout).** `scripts/r5_corpus.py` writes one entry per gate record and per repository to `fixtures/r5-replay/<bead>[-<repo>][-<part>]/` and one synthetic bundle per repository to the corpus store. Rules, all settled:
   - *Fidelity is provenance.* `recorded`: findings extracted from the reviewer's own report in the session transcript, by a cheap-tier extraction subagent, from the report text only, claim near-verbatim, path present in the report, range from line references or null, `extracted_by: model`, accepted only where every blocking iteration's extracted CRITICAL and IMPORTANT counts equal the archive's. `derived`: path and range from the lens's fix-commit hunks, claim from the commit's severity bullet, one-to-one only. `counts_only`: severity counts, lens order, iteration count and `sequential_steps`, nothing finer. `verification_level` is `asserted` at every fidelity. `blocking_findings` is an integer; 0 is a clean entry at whichever fidelity confirmed it.
   - *Before extraction, the irreversible step.* The raw reviewer reports for every bead with a surviving transcript are copied to the private archive at the ecosystem root, beside the state files, with their hashes recorded. They never enter a repository.
   - *Multi-repo records.* A record spanning repositories is one entry per repository, grouped by `record`; findings are assigned by path; unassignable ones are listed under `cross_repo_findings` in each sub-entry and excluded from that entry's recall; a sub-entry's own `sequential_steps` is null, since the archive cannot split it without guessing, and `record_sequential_steps` is carried on every sub-entry and counted once per record in the aggregate step ratio. `<part>` is the archive record stem's suffix after the bead id; `-<repo>` is appended only when a record spans several repositories.
   - *Bundles.* One synthetic bundle per repository (every base and head tree the corpus needs as synthetic commits via `git commit-tree`; tree SHAs exact, commit SHAs synthetic, originals in `meta.json`), published as release assets on this repository (`rsionnach/nthlayer`) under a `corpus-v*` tag, one release per corpus version, never edited after publication; the namespace is added to the front door's disjoint-tag rule and `release.yml` must ignore it. Committed to no repository (measured 122 MB in total, opensrm 112 MB, over GitHub's 100 MB file limit). The corpus PR to cúramóir carries `fixtures/r5-replay/bundles.json` with each bundle's release tag, asset URL, sha256 and size; each entry's `meta.json` records its bundle's sha256.
   - *Briefs.* By `brief_source`: the reviewer prompt isolated verbatim from the transcript, else the bead's description and acceptance from `bd`, else a plan document already in the repository, else none. The corpus PR lists the transcript-derived briefs for a human to skim once before merge.
   - *No floor.* The corpus is a regression test. Report entry and bead counts per fidelity, bundle sizes, and `brief_source` counts.
   - *Versioning.* `r5_corpus.py --release-tag corpus-v<N>` is required; the builder refuses to rebuild a published tag with different bundles and refuses an N lower than one a manifest already records. A new corpus is a new tag, never an edited release.
   - *Delivery.* One PR to cúramóir carrying only `fixtures/r5-replay/` (entries and `bundles.json`), targeting cúramóir's default branch, with the transcript-derived briefs listed in the body for a human to skim before merge.
   - *One archive, two figures.* Re-run `r5_baseline.py` over the snapshot the corpus was built from, so the baseline's bead count, record count and 991-step total and the corpus's counts are from the same archive; publish both with dates and reconcile the difference (A6).
   - *Corpus-v2, filed and not built now.* `brief.md` holds the pass-1 prompt only, and no entry records the tree a later lens reviewed (§6). One bead: per-iteration `reviewed_at`, per-finding `path_changed_since_head`, the count of recorded findings it marks, and whether a later lens's prompt differed from pass 1's by more than the template (if so, how to carry it is a §6 amendment then). Built when cúramóir's replay harness (its bead 6) needs it; `corpus-v1` is never rebuilt.
   *Closed when* every entry's bundle checks out at its synthetic head with the recorded `tree_sha`; every recorded entry's blocking findings carry a claim, and a path and range wherever the reviewer's report gave them; every entry carries counts and `sequential_steps` (null only on a multi-repo sub-entry, with `record_sequential_steps` present); the two escape beads carry `escape: true` and their missed finding under `escaped`; the publication check passes; and the entries and the store location are delivered to the cúramóir repository as one PR with no other change.
3. **Finding schema in the templates (R5-R11).** Each lens template ends its output with `R5-FINDINGS:` and a JSON array in the §6 schema including `verification_level`; `r5-supervise` parses it with cúramóir's reference implementation (`.claude/hooks/lib/r5_findings.py` there), which `scripts/r5_findings.py` matches exactly and `r5_corpus.py` imports for the normaliser; comparisons recompute fingerprints rather than trust stored ones, so `corpus-v1` stays frozen. It refuses a reviewer whose last line is not the contract (`UNAVAILABLE`, retried once, then blocking), applies the closures rule in re-reviews, and holds a re-raise at the higher severity. Severity-to-blocking policy stays as the description has it. The templates keep their prose report and verdict word; the `R5-FINDINGS:` line is added, not substituted, so `epic-executor` stage 2 keeps reading prose until its own bead (3b, filed before this one closes and sequenced before any epic run) ports it to the same `scripts/r5_findings.py`. *Closed when* a live gate produces parsable findings from all five lenses; the `recorded.json` of three recorded corpus entries round-trips the new parser without loss, with no dispatch; A1 holds on `wo62-4-2`, on the runs already made (two before, three after, at live tiers) and with no further replay dispatches: every after dispatch parses; `prose_unfiled` is 0 with the `Not filed` heading in place (§6); and agreement between a before run and an after run falls inside the spread seen between two runs of one variant (met 2026-11-12: 0.23 to 0.24 against 0.18 to 0.28). The agreement figures, the same ignoring severity, and one fresh reviewer's adjudication, real or noise, of the blocking findings the runs raised that the recorded gate never did are recorded in `docs/r5-gate.md` by the `docs/r5-repeatability` PR, opened the day the bead closes; they are not a closing condition, but the adjudication is done before the next gate starts because two parked items wait on it; and `epic-executor`'s existing verdict extraction reads the dry-run outputs already made correctly.
4. **Round record (R5-R48).** `r5-state.json` gains `rounds[]` in the §6 shape; each sequential lens iteration is one `review` or `verify` round with one lens in `lenses`, and each fix is a `fix` round. Existing fields are kept; the archive keeps its name. *Closed when* a completed gate's archive validates against the shape and `r5_baseline.py` reads old and new archives alike.
5. **Round 0 (R5-R1).** Before the first reviewer, `r5-supervise` runs lint, the type check and the full suite on `BASE..HEAD` and ends the gate `PREFLIGHT_FAILED` with the tool output in the record when any fails. The provenance mechanical checks (R5-R33: SKIPPED or deselected new tests, zero-collecting changed modules, collection-time parametrise without a minimum, module-level skips, layout-relative paths, early returns in test bodies, swallowing excepts) run here as `scripts/r5_provenance_checks.py`; any hit is a blocking provenance finding in the record. *Closed when* the two escape corpus entries fail round 0 with no model dispatched.
6. **Tree-keyed verdict (R5-R49).** The record's `verdict` carries `tree_sha` (`git rev-parse HEAD^{tree}`) and `head_sha`. The close path in `r5-supervise` and `epic-executor` (`bd close`) and the PR merge check apply the §6 verdict check. *Closed when* a content-free rebase keeps a clean verdict and a one-line change after the gate refuses `bd close`.
7. **Gate description amendment, part 1 (R5-R62).** Done in part: the baseline table landed 2026-11-07. Remaining: a "Records" section stating the finding schema and the round record by reference to §6; the pre-flight section gains round 0; "What a clean gate means" gains the tree key. The "Sequential, not parallel" section stays until Phase B or D. *Closed when* the description, `r5-supervise` and the templates agree, as the description itself requires.
8. **Synthetic fixtures (closed 2026-11-07).** `test/fixtures/r5-baseline/`, one per archive pattern, no real records.
9. **Clarity advisory (R5-R12).** `r5-supervise` moves clarity from `passes` to `advisory_passes`: one review on the final tree, beside excellence, never looped on and never blocking; its findings are recorded and reported as excellence's are. Whatever reads the roster changes with it (the close check, `epic-executor`, `r5_baseline.py`, the gate description). Reason, from `corpus-v1`'s per-lens baseline: clarity is 256 of 1,107 sequential steps over 91 records and had a fix round in 69 of them, with no CRITICAL in 478 findings over the record. *Closed when* a live gate's record shows three `passes` and clarity under `advisory_passes`, `bd close` accepts it, and `r5_baseline.py` reads four-pass and three-pass records alike.
10. **Listed kill checks through cúramóir's runner (R5-R30 to R5-R34).** Depends on cúramóir's bead 4 and on A7. When a bead's brief carries an `r5-mutations` block (§6), `r5-supervise` runs `curamoir run mutations --repo <member repo> --base <sha> --head <sha> --brief <path>` before the provenance reviewer, in worktrees and never in the real checkout. Each green, `STALE` or `INCONCLUSIVE` entry is a blocking provenance finding in the record with the runner's output as evidence; the reviewer is given the results and hand-runs a kill check only for behaviour the list does not cover. New beads get the block where their briefs are written; a brief without one runs as today. *Closed when* a live gate's record carries `mutations[]` from the runner, a planted surviving mutation is reported with no model involved, and the real checkout's `git status` is clean throughout.

**Phase A acceptance.** Beads 3 to 7, 9 and 10 closed on their own conditions, and one live gate run end to end under the amended description. There is no replay over the corpus here: the v1.0 wording asked a dry run to lose no recorded CRITICAL or IMPORTANT, which bead 3's runs showed one review cannot do even with unchanged templates.

## 4. Phase B, conditional

Do this only if cúramóir's Epic 5 is more than six weeks from landing when Phase A closes. It is a prototype in the skill, replaced in Phase D; its value is the speed-up while NthLayer work continues daily and the live shadow evidence. If Epic 5 is closer, skip to Phase D.

1. **Parallel round 1 (R5-R2).** The three blocking lenses and clarity (advisory, R5-R12) are dispatched from the main thread as four `Agent` calls in one message, same `BASE`, `HEAD`, brief and plan, each with its template, with `subagentPromptCacheTtl: 1h` set so they share the cached prefix. Provenance in Phase B is the judgment reviewer only (R5-R35), reading by SHA. Its unlisted kill checks stay as today (listed ones go through the runner, Phase A bead 10), in the real checkout with the commit-first and `git status` safeguards, serialised after the other three lenses return and before the merge, so nothing mutates a checkout while reviewers read it. *Closed when* a live gate's round-1 record shows four lenses with overlapping `started`..`ended` windows.
2. **Merge (R5-R13 to R5-R17).** `scripts/r5_merge.py`: dedupe overlapping ranges with the same normalised claim; sort by severity then lens order correctness, edge-cases, provenance, clarity; MINOR to the deferred list; merge decisions into the round record. The supervisor never merges by reading. *Closed when* the merge of three corpus entries' round-1 output is byte-identical on two runs.
3. **Single fixer (R5-R18 to R5-R23).** One fix subagent per fix round with the fix list, the deferred list, the brief, the plan and the full diff; never the raw reviewer text. Priority order; conflicting lower-priority finding marked `superseded`; edits only files named in the fix list and their tests; no dependency, no public signature change unless a finding's `fix` says so; reports per finding `fixed`, `superseded`, `could_not_fix` or `disputed`. One commit per round after the suite passes, carrying the bead id and `r5-round: n`. In Phase B the scope check is the supervisor diffing the commit against the fix list's paths. *Closed when* a planted finding naming a file the fixer then edits beyond is reported as `scope_breach`.
4. **Verify round (R5-R24 to R5-R29).** The three blocking lenses and excellence in verify mode (clarity does not re-run): full `BASE..HEAD` diff at the new HEAD, each lens's prior open set with the fixer's statuses, the fix commit. Closures, re-raises, unaccounted findings and refused downgrades per §6. Excellence runs here (or in round 1 when round 1 is clean), deferred, advisory. *Closed when* a planted regression in a fix commit is raised with `regression: true` by the lens whose domain it is.
5. **Cap (R5-R7).** Three fix rounds without a clean verify ends the gate `ESCALATED` with every round in the record; nothing reverted.
6. **Hook rekey (R5-R47).** `r5-parallel-block.sh` reads an `in_flight` set in `r5-state.json` recording (`bead`, `HEAD`, `lens`, `session`, `dispatched_at`) and refuses a dispatch only when a fix round is in progress for the same branch, or the same lens for the same bead and HEAD is already in flight. The lock is untouched. *Closed when* a second session can dispatch subagents on a different bead while a gate's round 1 is in flight, and cannot while its fix round is.
7. **Tiers (R5-R55, R5-R56).** Per-lens `model` and `effort` in the subagent frontmatter: correctness, edge-cases, provenance and the fixer on the strong model; clarity and excellence on the cheaper one in both modes. No second model family in Phase B; that arrives as cúramóir's sampling audit when a provider adapter exists.
8. **Gate description amendment, part 2.** The "Sequential, not parallel" section is replaced by a "Rounds" section stating beads 1 to 6; the lock-and-state section gains the `in_flight` set and the hook rule.

**Phase B acceptance.** Regression replay (R5-R58) is a tripwire: one dispatch per lens on five recorded entries, failing on a report that does not parse, any `prose_unfiled`, or a lens silent across all five; recall there is telemetry. Steps (R5-R60) are measured over the shadow gates, where both step counts are in the record: batched total at most a third of the sequential total, median at most a third; per gate is telemetry. Shadow (R5-R61), the recall acceptance: the first ten live gates run the sequential gate as well, after the batched one, on the same `BASE..HEAD`; the record carries both; any blocking finding the sequential gate raised that the batched one did not is an incident, explained before the next gate. No early stop on a clean run of five.

## 5. Phase D, later

Starts when cúramóir's gate passes the regression replay (its E5-R26 and R5-R58). From then there is one implementation and two callers.

1. **Thin supervisor.** `r5-supervise <bead>` resolves `BASE` and `HEAD` as today (explicit `--base`/`--head` still honoured), runs `eco_doctor --fetch` as today, then calls `curamoir run gate --repo <member repo> --bead <id> --base <sha> --head <sha> --branch <name> --brief <path>` and reads the record it writes. A bead spanning repositories is one call per repository. `epic-executor` stage 2 makes the same call. `--dry-run` becomes `curamoir run gate --dry-run --corpus`.
2. **Hook shim (R5-R63).** `r5-parallel-block.sh` and the close and merge checks accept cúramóir's record (§6 verdict check) as equivalent to their own clean record, so whichever gate ran, `bd close` and the merge gate read one answer. During the overlap the NthLayer hook defers to the cúramóir record when one is present for the tree.
3. **Shadow period (R5-R61).** The first ten live gates through cúramóir also run NthLayer's sequential gate (or the Phase B batched one, if it was built) on the same `BASE..HEAD`; the record carries both. A blocking finding the NthLayer gate raised that cúramóir's did not is an incident, explained before the next gate.
4. **Hook removal.** After ten clean shadow gates, `r5-parallel-block.sh` and `r5-lock.sh` are removed (cúramóir's job lock covers the gate), the templates in `rule-of-five-review/` are archived with a pointer to cúramóir's lens files, and `r5-state.json` stops being written; `.curamoir/state/r5/` is the record.
5. **Gate description, final amendment.** The description becomes a short page: roster, severities, gate-before-merge, the pre-flight, and a pointer to the cúramóir spec for the mechanism. The baseline table and the escape history stay, as the reason the gate exists.

## 6. Shared contract with cúramóir

This section is word for word the same in both specs. A change to it is a dated amendment made in both repositories in one pass, or in neither.

**Finding.** One object per finding. A reviewer's last non-empty output line is `R5-FINDINGS:` followed by a JSON array of them; anything else is `UNAVAILABLE`. Lines end at LF, with a CR before it tolerated; U+2028, U+2029 and every other Unicode separator are content, so one inside a claim does not split the line.

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

- `status` is set by the fixer, never by a reviewer.
- `normalised claim` is computed by one function, and the reference implementation is normative: cúramóir's `gate/findings.py` (today `.claude/hooks/lib/r5_findings.py`); NthLayer's scripts import it rather than reimplement it. Its rules, in order: lower-case; replace each line reference matching `\blines?\s+~?\d+(?:\s*[-–]\s*~?\d+)?\b` (so \"line ~42\" goes as \"line 42\" does), `:\d+(?:-\d+)?\b` or `\bl\d+\b`, and each SHA-like token matching `\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b` (at least one digit, so a word like "defaced" survives), with a single space; collapse whitespace; strip. Other numbers stay: "exits 2" and "exits 4" are different claims. Where this text and the reference code disagree, the code is right and the text is fixed by a changelog line.
- A stored `fingerprint` is a cache, never a comparison key: every comparison (merge, closure matching, replay) recomputes it from `lens`, `path` and `claim` with the current normaliser. A published corpus therefore stays frozen when the normaliser changes.
- `verification_level` is the E5-R11 ladder, weakest first; `evidence` is its proof. A blocking finding below the configured floor (default `script`) is labelled `UNPROVEN` in the record and the brief; it still blocks, and the fixer verifies or disputes it before fixing it. Clarity and excellence are advisory (R5-R12) and have nothing to prove.
- Severities are the only scale. cúramóir's earlier P0 to P3 maps P0 and P1 to CRITICAL and IMPORTANT and P2 and P3 to MINOR; the lines that used it (E5-R1, E5-R4) are amended rather than carrying a mapping.

**Closures (verify mode).** A record with `resolves` set is a closure, not a finding. It is never counted toward termination, whatever `severity` it carries (copy the original's); its `path`, `start_line`, `end_line` and `evidence` are the resolving lines and its `claim` is why the prior finding no longer holds. A closure is valid only if `resolves` names a fingerprint in the previous round's open set and `evidence` is non-empty; an invalid closure is ignored and logged `closure_rejected` with the reason, and a second closure of the same fingerprint is dropped. The closure's own fingerprint is never compared to `resolves`. A re-raised finding is the prior record copied verbatim (path and claim, so the same fingerprint) with no `resolves`; it keeps the more severe of its own and the prior severity, and the held-up ones are logged `downgrades_refused`, so severity goes down only through a valid closure. The next round's open set is the previous open set minus valid closures, plus new and re-raised findings. A prior open finding with neither a closure nor a re-raise is carried forward unchanged and tagged `unaccounted`: silence never closes. Unaccounted count per lens per round is a telemetry line, and a report that closes every prior finding with empty `evidence` and re-raises none of them is `UNAVAILABLE` (R5-R9, R5-R25); a report that re-raises a finding and also closes it has that closure rejected and the re-raise kept.

**Prose and entries.** A template keeps its prose report; the array is added beside it. Every issue the prose describes, mechanical notes included, has an entry at the severity the prose implies: `verification_level` labels a finding and never decides whether it is filed or at what severity. A remark that is not a finding goes under a `Not filed` heading, one line each, ending in its reason: `out_of_scope`, `pre_existing` or `not_an_issue`. The parser logs `prose_unfiled`, as `{"heading": "", "text": ""}`, for each item under a severity heading with no matching entry and each `Not filed` line with no reason; the count per lens per round is a telemetry line. The parser cannot see an issue mentioned only in running prose, so the sampling audit (R5-R57) reads its sampled reports for one.

**Round record.** Existing top-level fields of NthLayer's `r5-state.json` are kept; these are added. cúramóir writes the same shape to `.curamoir/state/r5/<bead>/record.json`.

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
                         "tokens_in": null, "tokens_out": null, "tokens_total": 51234, "duration_s": 150.0,
                         "status": "ok | UNAVAILABLE | skipped", "skip_rule": null,
                         "findings": [], "closures": [], "closure_rejected": [],
                         "unaccounted": [], "downgrades_refused": [], "prose_unfiled": []}
      },
      "merge": {"fix_list": ["<fingerprint>"], "deferred": ["<fingerprint>"], "deduped": [["<a>", "<b>"]]},
      "fix": {"commit": "<sha>", "statuses": {"<fingerprint>": "fixed"}, "scope_breaches": []},
      "mutations": [{"path": "", "mutation": "", "result": "red | green | stale | inconclusive", "worktree": ""}]
    }
  ],
  "verdict": {"state": "CLEAN | ESCALATED | PREFLIGHT_FAILED | BUDGET",
              "tree_sha": "<sha>", "head_sha": "<sha>", "at": "<iso8601>",
              "inputs": {"brief": "sha256:<hex>", "lens:correctness": "git:<blob id>"}, "input_digest": "sha256:<hex>"}
}
```

**Measurements (v1.11).** `model`, `tier`, `tokens_in`, `tokens_out`, `tokens_total` and `duration_s` are `null` when unmeasured, never `0`: a `0` reads as measured and zero. `tokens_total` is for a dispatcher that measures only a total (the Agent result reports one, with no split); the split stays `null` beside it. `duration_s` is derived from the round's start and end timestamps where both carry a time of day. NthLayer derives `rounds[]` from the audit trail with `scripts/r5_record.py`, which is safe to re-run over every archive, so a rename here is a re-derivation there.

**Verdict check.** A close, push or merge gate passes when `verdict.state` is `CLEAN` and `git rev-parse HEAD^{tree}` equals `verdict.tree_sha`. Anything else refuses, naming the state or the mismatch. A squash, reorder or message edit that leaves the tree identical keeps its verdict; a rebase onto a moved base changes the tree and re-gates.

**Verdict inputs (R5-R75, optional).** `verdict.inputs` maps a name to a digest of each thing the verdict depended on beyond the tree: `brief`, `plan` and `mutations` (the subject), and `lens:<name>` for each lens file, `gate_config` and `runner_version` (the apparatus); the model per lens is already in `rounds[].lenses`. A whole tracked file is `git:<blob id>`; anything else is `sha256:<hex>` over its exact bytes. `input_digest` is the sha256 of the canonical JSON (UTF-8, keys sorted, no insignificant whitespace) of `tree_sha` and `inputs`. Only the runner computes a digest; one that appears in model output is discarded. The fields are informational: the verdict check reads `tree_sha` and nothing else, a gate that does not write them conforms, and nothing refuses on them.

**Mutation block.** In the brief's markdown, one fenced block with the info string `r5-mutations`; the runner extracts it at round 0, so the brief is the source and the extracted file is the record.

```yaml
- path: src/opensrm/parser/v2.py
  locate: {lines: [118, 131]}          # or {anchor: "def classify("}
  mutation: invert_condition           # invert_condition | drop_argument | return_constant
                                       # | delete_statement | swap_operator | {replace: {from: "", to: ""}}
  expect_red: "python -m pytest tests/test_parser_v2.py::test_judgment_slo_mapping -q"
```

**Replay corpus.** The unit is a gate record and a repository: one bead, one repo, one checkpoint, one `BASE..HEAD`, which is what the gate itself runs on (R5-R8). A bead with checkpoints or spanning several repos has one entry per record and repo, grouped by `record`. An entry's directory is the archive record's stem, so `<part>` is whatever suffix the record carried after the bead id (a checkpoint such as `checkpointA`, or the repository the record was named for); `-<repo>` is appended only when one record spans several repositories, so that its sub-entries differ. Bundles live outside the plugin repository, because `claude plugin marketplace add` clones it and because fetching commits from the source repositories is not durable once squash-merged branches are garbage-collected.

```
<corpus store>                                 release assets on rsionnach/nthlayer under the corpus-v* tag namespace (added to the front door's disjoint
                                               tag-namespace rule), one release per corpus version; a release is never edited, a new version is a new tag.
                                               Measured 2026-11-09: the synthetic bundles total 122 MB and opensrm's alone is 112 MB, over GitHub's 100 MB
                                               in-repo file limit, so they are committed to no repository; a clone never downloads a release asset. No
                                               dedicated repository.
  <repo>.bundle (release asset)                one synthetic bundle per repo holding every base and head tree the corpus needs as synthetic commits
                                               (tree SHAs exact, commit SHAs synthetic, built with git commit-tree); each entry records its sha256
fixtures/r5-replay/bundles.json                in the plugin repo beside the entries: per repo the release tag, asset URL, sha256 and size; the harness reads
                                               this and nothing from the nthlayer repository's git content

fixtures/r5-replay/<bead>[-<repo>][-<part>]/   in the plugin repo, light files only: one entry per gate record AND per repo
  meta.json        bead, record (archive stem), record_repos, repo, part, base, head (original SHAs), synthetic_base, synthetic_head, tree_sha,
                   bundle: {repo, sha256}, sequential_steps (this entry; null on a sub-entry of a multi-repo record, which the archive cannot
                   split without guessing), record_sequential_steps (the whole record; counted once per record in the aggregate step ratio),
                   fidelity: recorded | derived | counts_only (provenance of the findings, never their content),
                   blocking_findings (integer; 0 is a clean entry, selected by the clean-bead blocking rate at any fidelity; recorded when the
                   reviewer output confirmed none, counts_only when only the archive says so), escape: true|false,
                   brief_source: reviewer_prompt | bead | plan_doc | none
  brief.md         what the reviewers were given, by brief_source: the reviewer prompt isolated verbatim from the transcript and nothing around it;
                   else the bead's description and acceptance from bd; else a plan document already in the repo; else absent
  diff.patch       git diff base..head for this repo
  recorded.json    the sequential gate's blocking findings per lens per iteration, with lens order and iteration count at every fidelity;
                   recorded: findings in the Finding schema taken from the reviewer's own output in the session transcript (derived_from:
                   reviewer_transcript, extracted_by: model where a model did the extraction, accepted only where every blocking iteration's
                   extracted CRITICAL and IMPORTANT counts equal the archive's; the finding records only, never surrounding text; claim always
                   present, path and range only where the reviewer's report gave them and null otherwise, since recall matches on claim),
                   fix_commit beside each where one exists; derived: path and range from that lens's fix-commit hunks and claim from the commit's severity
                   bullet, one-to-one only (derived_from: fix_commit, fix_commit: <sha>, bullet: <text>); counts_only: severity counts per lens
                   per iteration and no findings. verification_level is asserted at every fidelity. Findings are assigned to the entry whose
                   repo their path belongs to; unassignable ones are listed under cross_repo_findings in each sub-entry and excluded from that
                   entry's recall. Recall is scored on each lens's first-review findings only; later iterations may be about that lens's own fixes.
                   A later lens's first review also ran past head, on a tree carrying the earlier lenses' fixes (checked 2026-11-11 on
                   opensrm-wo62-4-2: clarity one commit past head, edge-cases three, provenance five; src identical, 262 golden files
                   re-pinned in between), and corpus-v1 does not record which. From corpus-v2 each iteration carries reviewed_at (commit and
                   tree) and each finding path_changed_since_head; a finding whose path changed is logged tree_drift and left out of recall.
```

**Publication rule.** An entry carries only what is derived from public repository content: code, the diff, a brief as given to the reviewers, the reviewer findings about that code. A gate record's free-text notes, rulings and session fields never enter the corpus or any fixture. Test fixtures in any public repository are synthetic (same structure and numbers, invented ids and timestamps), never trimmed real records. The raw reviewer reports that `recorded` entries come from stay in NthLayer's private archive. cúramóir's intake refuses an entry that carries notes, rulings or session fields.

## 7. Decisions

| Decision | Date | Binds |
|---|---|---|
| Verdict keyed to the tree SHA, not the commit | 11-03 | Phase A bead 6 |
| A lens that fails twice is `UNAVAILABLE` and blocks; no waiver path | 11-03 | Phase A bead 3 |
| Three fix rounds total, then escalate | 11-03 | Phase B bead 5 |
| No in-checkout mutation path once cúramóir's runner exists; until then the old safeguards stay, serialised after the other lenses | 11-03 | Phase B bead 1, Phase D |
| Clarity on the cheap tier in both modes, with the MINOR-rate telemetry line | 11-03 | Phase B bead 7 |
| Lock held for the whole gate, keyed on the git common dir, in every phase | 11-03 | §2 |
| Mutation list is a fenced `r5-mutations` block in the brief | 11-03 | §6 |
| Shadow period of ten live gates, no early stop; it is the recall acceptance | 11-03, 11-09 | Phase B, Phase D |
| Excellence stays advisory, runs once on the final tree | 11-03 | Phase B bead 4 |
| No batching across beads; no landing on main before the gate | 11-03 | §2 |
| Phase B only if cúramóir's Epic 5 is more than six weeks out | 11-03 | §4 |
| No cross-vendor review on NthLayer in any phase; it arrives as cúramóir's sampling audit | 11-05 | Phase B bead 7 |
| `verification_level` joins the schema; UNPROVEN still blocks; corpus entries carry `asserted` | 11-07 | §6, Phase A bead 3 |
| Closures never count; silence never closes; re-raises keep the higher severity | 11-07, 11-09 | §6 |
| Publication rule; synthetic fixtures; raw reports stay in the private archive | 11-07 | §6, Phase A bead 2 |
| Blocked dispatches are known data in the baseline script, not a rule | 11-07 | Phase A bead 1 |
| Corpus fidelity recorded / derived / counts_only with `blocking_findings`; no floor; corpus is a regression test | 11-09 | Phase A bead 2 |
| Corpus unit is a gate record and repository; bundles in a separate store; briefs by source | 11-09 | §6, Phase A bead 2 |
| Raw reports copied to the private archive before any extraction; `cleanupPeriodDays` raised | 11-09 | Phase A bead 2 |
| Step ratio is an aggregate test, per entry telemetry | 11-09 | Phase B acceptance |
| ~~A1 and replay recall are judged on the union of three runs per variant~~ (superseded 11-12) | 11-11 | |
| A1 closes on `wo62-4-2` with no further replay dispatches; replay is a tripwire; recall and the step ratio are proven only in the shadow period | 11-12 | Phase A bead 3, Phase B acceptance |
| Clarity is advisory, in the live sequential gate now and in the batched one | 11-12 | Phase A bead 9, §6 |
| Listed kill checks run through cúramóir's mutation runner under today's gate | 11-12 | Phase A bead 10 |
| Verdict inputs are optional in the record and never refuse | 11-12 | §6 |
| Scope is frozen until the shadow period reports; the parked list is in the cúramóir spec | 11-12 | §1 |
| Prose and entries: every described issue is filed, `Not filed` carries a reason, `prose_unfiled` is logged | 11-11 | §6, Phase A bead 3 |
| Recall scores first-review findings; corpus-v2 records the tree each lens reviewed | 11-11 | §6, Phase A bead 2 |

## 8. Changelog and amendment rule

A change to this file after v1.0 is one dated line here, the edit it names, and the same change in the cúramóir spec when it touches §6 or a shared decision. Both agents are told in the same message. Nothing is edited in place without a line here.

- **v1.11, 2026-11-13.** From bead 4 (6kqs.4). §6 Round record: a lens entry gains `tokens_total` beside `tokens_in` and `tokens_out` (E1); an unmeasured `model`, `tier`, token count or `duration_s` is `null`, never `0`, and the example shows it (E2); `duration_s` is derived from the round's timestamps. Both are errata against the shape cúramóir owns: mirrored as a cúramóir bead (E1, E2) for its spec, not edited there from here.
- **v1.10, 2026-11-12.** From the first three-pass gate (6kqs.3). A1 discharged; bead 3's agreement criterion is restated as falling inside the within-variant spread, and its `docs/r5-gate.md` figures move to the docs PR. §6: an output line ends at LF only; the line-reference pattern takes `~`; a re-raise beside an empty closure keeps the re-raise. `scripts/r5_findings.py` takes those three from cúramóir's parser once it has them. Mirrored in the cúramóir spec at its v1.10.
- **v1.9, 2026-11-12.** Rob's five decisions. New Phase A beads 9 (clarity advisory, now) and 10 (listed kill checks through `curamoir run mutations`), with A7; Phase B's roster follows. A1 drops the clarity criterion. Phase A's acceptance no longer asks a corpus dry run to lose no recorded finding, and bead 3's parser check is a round-trip with no dispatch: both were the unmeetable test v1.8 removed elsewhere. §6: clarity advisory, optional `verdict.inputs` (R5-R75). Scope frozen. Mirrored in the cúramóir spec at its v1.9.
- **v1.8, 2026-11-12.** Rob's ruling that more replay dispatches cost more than they prove. A1 and bead 3 close on the `wo62-4-2` runs already made; `wo62-2` and `wo62-4-3` are not run. Phase B: R5-R58 is a tripwire with recall as telemetry, and the step ratio is measured over the shadow gates. §6 unchanged. Mirrored in the cúramóir spec at its v1.8.
- **v1.7, 2026-11-11.** From A1's runs on `wo62-4-2` (25 dispatches; within-variant agreement 0.19 to 0.29, across 0.26): A1 and bead 3's closing condition are restated over three runs per variant with a silent-lens check; Phase B's recall acceptance follows; the corpus-v2 bead is filed under bead 2. §6: `prose_unfiled` in the lens record, the prose-and-entries rule with a `Not filed` heading, recall on first-review findings only, and the corpus-v2 fields `reviewed_at` and `path_changed_since_head`. Mirrored in the cúramóir spec at its v1.7.
- **v1.6, 2026-11-10.** Bead 3: templates add the line rather than replace prose; `epic-executor` stage 2 moves in bead 3b; A1's dry-run design (three entries, before and after, pilot first, variance floor) and the epic-executor prose check join the closing condition. NthLayer only; the cúramóir spec stays at v1.5.
- **v1.5, 2026-11-10.** §6: claim normaliser stated as an algorithm with cúramóir's implementation normative; fingerprints recomputed on comparison; bead 3 imports the normaliser rather than reimplementing it. From 6kqs.3.
- **v1.4, 2026-11-10.** §1 restated from the published `corpus-v1`; bead 2 gains the builder's tag rule and the delivery rule (default branch, fixtures only).
- **v1.3, 2026-11-10.** Corpus store corrected: no dedicated repository. Bundles are release assets on this repository under `corpus-v*`; `bundles.json` goes to cúramóir with the entries. Bundle total corrected to the measured 122 MB.
- **v1.2, 2026-11-09.** From the cúramóir agent's review of v1.1: A6 and a bead-2 rule to re-run the baseline over the corpus's archive snapshot so the 63-bead and 65-bead figures are reconciled with dates.
- **v1.1, 2026-11-09.** From this agent's review of v1.0 against the built corpus: §1 states the built corpus (131 entries, 18 recorded, 0 derived, 113 counts_only) in place of the bead-level count; bead 2's closed-when no longer requires a path and range the report never gave; `<part>` defined; a multi-repo sub-entry's `sequential_steps` is null with `record_sequential_steps` counted once per record; bundles are release assets on the corpus repository (116 MB total, opensrm 112 MB); A2 and A3 discharged. Mirrored in the cúramóir spec's §11 and §13.
- **v1.0, 2026-11-09.** Consolidates the 3 November hand-off and the amendments of 5, 7 and 9 November, including the agent's corpus-fidelity paragraph, into one text. New against the amended text: §0 assumptions; the baseline stated from the full record; Phase A bead 1 and 8 marked closed and bead 7 part-done; bead 2 restated with every settled rule (fidelity as provenance with `blocking_findings`, private archive first, multi-repo split, per-repo synthetic bundles in a separate store, briefs by source, no floor); the step ratio made an aggregate; re-raises keep the higher severity (from the cúramóir bridge's implementation); the ecosystem-root hooks noted as unversioned by design.
