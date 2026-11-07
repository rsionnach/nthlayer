# r5_baseline fixtures

Synthetic gate records, one per structural pattern the archived
`.claude/r5-state-*-completed.json` records show. Each has the structure and
the numbers of a record that exhibits the pattern, with an invented bead id
(`fx-<pattern>`, except that two share `fx-checkpointed-bead`, as a bead
gated at two checkpoints has two records) and invented timestamps (`2000-01-01T…`, in event order). They
carry no free text: no notes, rulings, briefs or session fields.

They are synthetic, not trimmed copies of real records, so that nobody
"refreshes" them from the archive later with more fields in them (opensrm-6kqs.8).
The rule for what may be published from gate work: content derived from public
repositories (code, diffs, briefs in a repo, findings about that code) may be;
a gate record's free-text notes, rulings and session fields may not.

Fields present, and nothing else:

- top level: `supervisor`, `version`, `target_bead`, `started_at`, `dry_run`,
  `passes`, `advisory_passes`, `status`;
- each `completed_passes[]` entry: `name`, `findings_count_initial`,
  `findings_count_final`, `fix_iterations`;
- `audit_trail[]` events `pass_started`, `findings_received`,
  `advisory_pass_completed`, `pass_completed`, `fixes_applied`,
  `fix_dispatched`, `reviewer_dispatched`, `reviewer_dispatch_blocked` and
  `supervisor_blocked`, with `ts`, `event`, `pass`, `iteration`, `counts` and
  `fix_iterations`.

The script's known-data tables (`BLOCKED_DISPATCHES`, `PASSLESS_EVENTS`) hold
real archive keys, which match none of these. The tests swap in the synthetic
counterparts (`SYNTHETIC_BLOCKED_DISPATCHES`, `SYNTHETIC_PASSLESS_EVENTS` in
`test_r5_baseline.py`); the real keys are checked against the archive when the
script runs, by `unmatched_table_entries`.

| fixture (`r5-state-fx-…-completed.json`) | pattern |
|---|---|
| `v2-per-review-severities` | schema v2: severities logged per review, advisory excellence as `advisory_pass_completed` |
| `v1-totals-only` | schema v1 with no `findings_received`: pass totals only, so every finding is unattributed |
| `v1-fix-loops` | schema v1, totals only, multi-iteration fix loops |
| `dry-run-with-other-bucket` | a dry run (excluded from the totals), and a `counts` key outside the three severities (`missing_tests`) |
| `combined-pass` | one review covering two passes (`clarity+edge-cases`) that `completed_passes` lists separately |
| `re-run-passes` | passes re-run after the first round: reviews, fixes and the dispatch sequence across runs |
| `re-run-fixes-only-in-runs` | a re-run pass whose fix rounds only the summed runs show (events and summary hold one each) |
| `blocking-only-initial-count` | fixes applied with `fix_iterations: 0`, and `findings_count_initial` counting only blocking findings |
| `stall-and-resend` | a stalled reviewer re-dispatched: more `reviewer_dispatched` than `findings_received` |
| `blocked-dispatch-after-launch` | a dispatch the hook refused, followed by `reviewer_dispatch_blocked`, beside a real stall in another pass |
| `blocked-dispatch-before-launch` | a dispatch the hook refused, followed by `supervisor_blocked` |
| `passless-fix-events` | two counting events logged with no `pass`, and one-off re-check passes |
| `abandoned-unreviewed` | a gate abandoned after `pass_started`, nothing reviewed (excluded from the totals) |
