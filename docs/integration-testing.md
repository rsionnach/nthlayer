# NthLayer integration testing

Five test surfaces in `test/`, two of which share a boot/teardown
library. See script headers for invocation details; this file is the
cross-reference.

## Test scripts

- `test/test_demo_paths.sh` — path-resolution regression guard
  (opensrm-oey5). Asserts `bash -n demo/demo.sh` passes and that
  `demo/_paths.sh` resolves `FRONTDOOR_ROOT` to this repo and
  `WORKSPACE_ROOT` to the parent dir containing
  `nthlayer-{core,workers,bench,common}`. Runs in <1s, no Docker.
  CI: `.github/workflows/demo-paths.yml` (push/PR to main).
- `test/test_demo_start_lock.sh` — concurrent-invocation start-lock
  regression guard (opensrm-36es). Exercises `cmd_start`'s 0a guard
  with a stub that skips the full boot, asserting: two concurrent
  invocations → exactly one wins; stale lock (PID 99999, owner-tag
  match) → reclaimed with `warn`; lock dir present but `pid`/`owner`
  missing → treated as stale; PID alive but owner-tag missing or
  mismatched → treated as stale (catches PID-recycle false
  positives); EXIT hook removes the lock on normal exit, on `exit 1`
  (0b refusal), and on SIGINT. Runs in ~5s, no Docker. CI:
  `.github/workflows/demo-start-lock.yml` (push/PR to main).
- `test/integration-three-tier.sh` — **canonical E2E** P5.1 three-tier
  ship-readiness test (real core API + workers + bench-via-API). Boots
  Docker stack, drives reversal_rate breach via fake-service, asserts
  verdict chain end-to-end. Sources `_three_tier_lib.sh` for
  preflight/boot/teardown (270 lines, down from 371). CI integration:
  `.github/workflows/integration-three-tier.yml` (workflow_dispatch +
  nightly cron 04:00 UTC, timeout 15 min). Replaced the seeded
  in-process `test/integration-chain.sh` (retired 2026-06-06 per
  `opensrm-u5dw`).
- `test/e2e-test.sh` — 9-step CLI-driven E2E test (opensrm-saun.2).
  Sources `_three_tier_lib.sh` for preflight/boot/teardown
  (391 lines, down from 458). See script header.
- `test/_three_tier_lib.sh` — shared boot/teardown library
  (opensrm-saun.2.1). Sourced by `integration-three-tier.sh` and
  `e2e-test.sh`. Four helpers:
  - `preflight_required_commands [extra...]` (checks
    docker/uv/curl/python3/jq/lsof + optional extras).
  - `preflight_port_conflicts CORE_PORT FAKE_PORT` (EADDRINUSE
    catcher; skips Prometheus 9090 since that's inside Docker).
  - `boot_three_tier_stack ...` (Docker compose + Prometheus poll +
    fake-service + core + workers + heartbeat wait; sets globals
    CORE_PID / WORKERS_PID / FAKE_PID / DOCKER_UP).
  - `teardown_three_tier_stack ...` (disarms INT/TERM trap to
    prevent recursive teardown, ordered SIGTERM
    workers → core → fake-service, `docker compose down
    --remove-orphans`; success removes WORK_DIR, failure preserves
    logs at `/tmp/<save-prefix>-debug-<ts>` and calls optional
    `tt_known_blockers` hook).

  Hook pattern: callers define
  `tt_log` / `tt_info` / `tt_pass` / `tt_fail` / `tt_known_blockers`
  before sourcing; fallbacks provided. Normalises two inconsistencies
  from the originals: trap-disarm for recursive teardown is now
  centralised; known-blocker text is an optional caller hook instead
  of hardcoded.

## `demo/demo.sh` — `cmd_start` guard sequence

Three ordered guards at the top of `cmd_start` (opensrm-m7su +
opensrm-36es):

- **0a — `.start.lock` concurrent-invocation mutex.** Lock dir at
  `$OUTPUT_DIR/.start.lock` holding `pid` (owning shell
  `${BASHPID:-$$}`) + `owner` (literal `demo.sh-start-lock`).
  `mkdir` is the atomic primitive (shell `mv` into an existing
  directory moves *into* it rather than failing, so an `mv`-rename
  dance does not give atomicity for directory names). After `mkdir`
  succeeds, pid + owner are written in two `echo`s; a concurrent
  reader uses `_read_lock_state` to poll up to ~200ms for the
  metadata to appear before making a decision (tolerates the
  establish window). Stale-lock reclaim requires the recorded PID to
  fail `kill -0` AND the owner tag to match the literal — protects
  against PID recycling pointing the cleanup logic at the user's
  IDE. If the 200ms poll completes with empty pid or owner, the
  caller refuses with a manual-cleanup hint rather than
  auto-reclaiming (false refusal costs one `rm -rf`; false reclaim
  under load would produce concurrent boots — the exact bug this
  guard prevents). Cleanup via the `_demo_cleanup` registry
  (single EXIT trap, composable hooks) so future cleanup-needing
  code can append rather than clobber. A
  `_DEMO_START_LOCK_ESTABLISHING` sentinel lets the cleanup hook
  also rm a half-built lock when SIGINT lands between `mkdir` and
  the metadata `echo`s. Refuses to run if `$OUTPUT_DIR` is a
  symlink.
- **0b — live-process refusal.** Walks the canonical PID files
  (`fake-*.pid`, `workers.pid`, `core.pid`, `http-server.pid`); if
  any process is alive, refuse with the recovery hint to run
  `./demo.sh teardown` first.
- **0c — stale PID file reconciliation.** Same canonical PID files;
  for any PID file whose process is dead, clean up via
  `stop_pid_file` before binding new processes.

For worker pipeline architecture see
`docs/superpowers/specs/2026-04-25-p3-e1-respond-coordinator-worker-design.md`.
For demo orchestration see `demo/demo.sh` header and
`demo/scenario-cascading-failure.yaml`.

## `test/integration-three-tier.sh` — harness details

Boot/teardown logic (preflight, stack startup, trap disarm, log
preservation) is now in `test/_three_tier_lib.sh`. The details below
describe the full behaviour; the library owns the implementation.

Env overrides: `CORE_PORT` (default 8000), `FAKE_PORT` (default
8001), `PROMETHEUS_URL` (default `http://localhost:9090`),
`LATENCY_BUDGET_SECONDS` (default 30).

Repo resolution: `FRONTDOOR_ROOT` = this repo root; `WORKSPACE_ROOT`
= `FRONTDOOR_ROOT/..` — resolves sibling repos the same way in both
local sibling-repo layout and CI checkout layout.

`RUN_BENCH` (`uv run --directory nthlayer-bench`) is used for running
the assertions helper (not just bench commands) because
`test/three_tier_assertions.py` imports
`nthlayer_bench.sre.case_bench`.

`test/three_tier_assertions.py` surface — integration-test
subcommands `wait-heartbeat`, `wait-verdict-type`,
`wait-assessment-kind`, `wait-case`, `assert-lineage`,
`fetch-case-via-bench`, `assert-latency` (all KEY=value-on-stdout
for `eval`-capture by `cmd_scenario`); plus the demo-only
`render-portfolio` (opensrm-42y.3) which prints the canonical Step 1
portfolio table by joining latest `portfolio_status` + per-service
`slo_status` assessments. `render-portfolio` is fail-open with exit
0 on any error — do not reuse in assertions.

Step 4 is rendered by `demo/render_explanation.py` (opensrm-42y.4),
a standalone helper invoked via `$RUN_WORKERS` rather than
`$RUN_BENCH` because the `ExplanationEngine` it drives lives in
`nthlayer-workers` and is not in the bench venv. Same fail-open /
stdout=narrative / stderr=diagnostic / not-for-assertions contract
as `render-portfolio`. Fetches `slo_status` + `drift_signal` via
core's HTTP API into a `MemoryAssessmentStore`, runs
`ExplanationEngine.explain_service(service, store)`, formats each
`BudgetExplanation` via
`nthlayer_common.explanation.format_explanation` table form.
Empty-`--service` guarded at the argparse boundary; `limit=200` on
the per-kind fetch caps results; `limit=0` is NOT a "fetch all"
sentinel for the core HTTP API — it returns zero rows (regression
introduced under 42y.4 R5 Pass 3, caught and fixed in 42y.9 E2E
sign-off, commit c1307a4).

### Boot sequence (always-fresh)

1. `docker compose up -d prometheus` — Prometheus only;
   Grafana/AlertManager omitted (flaky file-mount, not queried by
   assertions).
2. Poll Prometheus `/-/ready` (60s).
3. Start `fake-service.py --name fraud-detect --type ai-gate` (15s
   health check).
4. Start `nthlayer serve` with `NTHLAYER_STORE_PATH` +
   `NTHLAYER_MANIFESTS_DIR`; poll `/health` (30s); sanity-check
   `GET /manifests` returns ≥1 manifest.
5. Start `nthlayer-workers serve` with `NTHLAYER_LLM_STUB=canned`
   and all cycle intervals 5s
   (`--collect-interval 5 --measure-interval 5
   --correlate-interval 5 --respond-interval 5`); poll for first
   heartbeat (30s).

Trigger:
`POST /control {"reversal_rate": 0.08, "rps": 100}` to fake-service.

### Verdict chain assertions

Timeouts chosen for the Prometheus 2m window:

1. `wait-verdict-type quality_breach --service fraud-detect` (180s).
2. `wait-assessment-kind correlation_snapshot` (30s).
3. `wait-verdict-type triage` (60s).
4. `wait-case --service fraud-detect` (60s).
5. `wait-assessment-kind retrospective` (60s) — falls back to
   `calibration_signal` (60s) if no retrospective yet.

Strong lineage:
`assert-lineage TRIAGE_ID QUALITY_BREACH_ID` walks
`GET /verdicts/{id}/ancestors`. `correlation_snapshot` is an
assessment (not a verdict), so the ancestry is walked transitively
through verdicts.

Bench-via-API: `fetch-case-via-bench --state pending` directly
imports `nthlayer_bench.sre.case_bench.fetch_case_bench` — proves
the bench logic layer reads through core API.

Latency budget:
`assert-latency QUALITY_BREACH_AT CASE_AT LATENCY_BUDGET_SECONDS` —
defined as `quality_breach.created_at` → `case.created_at`; excludes
Prometheus window staleness and bench-fetch overhead.

### Runtime patterns

`run_assertion()` pattern: `output=$(...) || fail; eval
"${output}"` — the two-step form is load-bearing; the compact
`eval "$(…)"` silently swallows assertion failures when the helper
produces empty stdout.

Teardown trap (EXIT/INT/TERM): kills workers → core → fake-service
in order; runs `docker compose down --remove-orphans`; on failure
moves work dir to `/tmp/three-tier-debug-$(date +%s)` and prints
known-blocker guidance.

## `.github/workflows/integration-three-tier.yml`

- Triggers: `workflow_dispatch` + cron `0 4 * * *` (nightly 04:00
  UTC). NOT on push/PR (takes ~5 min, boots Docker).
- Checks out all 5 repos (`nthlayer`, `nthlayer-common`,
  `nthlayer-core`, `nthlayer-workers`, `nthlayer-bench`) at
  `ref: main`. Pinning trade-off: `main` is correct while
  components co-evolve in v1.5; switch to released versions
  post-v1.0.
- Installs: `uv` via `astral-sh/setup-uv@v7`; `jq` via apt;
  `prometheus-client` via pip3 (for fake-service).
- On failure: prints `core.log` (last 100 lines) and `workers.log`
  (last 200 lines) inline, then uploads `/tmp/three-tier-debug-*`
  as artifact `three-tier-debug-logs` (7-day retention,
  `if-no-files-found: ignore`).
- Security: no untrusted GitHub event input flows into shell
  commands.

## Known blockers (auto-failure expected until closed)

<!-- Drop when opensrm-saun.1.2 and opensrm-saun.1.3 close. -->

- `opensrm-saun.1.2` — CloudEvents envelope contract mismatch:
  respond verdicts rejected by core (HTTP 422 missing_fields).
  Symptom: test reaches "Wait for respond → triage verdict" and
  times out.
- `opensrm-saun.1.3` — AttributeError in RemediationAgent on
  canned-LLM responses. Worker keeps running but remediation hits
  the degraded path.
