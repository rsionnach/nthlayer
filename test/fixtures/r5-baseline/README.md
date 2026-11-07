# r5_baseline fixtures

Trimmed copies of eleven real archived gate records from the workspace root's
`.claude/` (untracked, so they cannot be referenced in place). Each keeps the
record's structure and every number the baseline reads; free text (notes,
rulings, briefs) and session details are dropped, because the archives are
internal and this repository is public.

How each was made: load the archive, keep only these fields, write it back
with `json.dump(..., indent=1)`. Nothing is edited by hand; to add one, apply
the same filter to another archive.

- top level: `supervisor`, `version`, `target_bead`, `started_at`, `dry_run`,
  `passes`, `advisory_passes`, `status`;
- each `completed_passes[]` entry: `name`, `findings_count_initial`,
  `findings_count_final`, `fix_iterations`;
- `audit_trail[]` events `pass_started`, `findings_received`,
  `advisory_pass_completed`, `pass_completed`, `fixes_applied`,
  `fix_dispatched`, `reviewer_dispatched`, `reviewer_dispatch_blocked` and
  `supervisor_blocked`, keeping `ts`, `event`, `pass`, `iteration`, `counts`
  and `fix_iterations`.

| file | why it is here |
|---|---|
| `r5-state-3ntg-completed.json` | schema v2, severities logged per iteration, advisory excellence as `advisory_pass_completed` |
| `r5-state-1mja-completed.json` | schema v1, no `findings_received` at all: pass totals only, so every finding is unattributed |
| `r5-state-oh27-completed.json` | schema v1, the oh27 escape; totals only, multi-iteration fix loops |
| `r5-state-m7su-dryrun-completed.json` | the one dry run (excluded from totals), and the one `counts` key outside the three severities (`missing_tests`) |
| `r5-state-g32d-checkpointB-completed.json` | passes re-run after the first round: reviews, fixes and the dispatch sequence across runs |
| `r5-state-g35i-completed.json` | a combined `clarity+edge-cases` pass that `completed_passes` lists as two |
| `r5-state-wo62-1-checkpointA-common-completed.json` | fixes applied with `fix_iterations: 0`, and `findings_count_initial` counting only blocking findings |
| `r5-state-bnal-completed.json` | a stalled reviewer re-dispatched: more `reviewer_dispatched` than `findings_received` |
| `r5-state-ir5m-completed.json`, `r5-state-wo62-4-1-completed.json` | the two archived dispatches the hook blocked before a reviewer ran (`BLOCKED_DISPATCHES`), beside real stalls re-sent |
| `r5-state-tu04.1.2.2-completed.json` | a gate abandoned after `pass_started` with nothing reviewed (excluded from the totals) |
