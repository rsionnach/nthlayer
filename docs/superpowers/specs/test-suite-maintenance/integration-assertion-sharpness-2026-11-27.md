# Integration-test assertion sharpness review (opensrm-hyxa)

Date: 2026-11-27. Scope: `test/integration-three-tier.sh`, the helper it
drives (`test/three_tier_assertions.py`), and the other callers of that
helper (`test/e2e-test.sh`, `test/integration-thresholds.sh`,
`demo/demo.sh`, `test/_three_tier_lib.sh`).

This is a reading review. Nothing here was run: the payload shapes are
taken from the code that writes them (nthlayer-workers and nthlayer-core
at their `main` on this date), and each proposed check should be confirmed
against a real run when it is implemented.

## Why

opensrm-pa2w found that measure classified every judgment-SLO breach as
`critical`, and the three-tier test passed throughout, because it asserts
that a `quality_breach` verdict exists and not what it says. An assertion
of presence catches a wiring break. It does not catch a wrong value on a
wire that works.

## What the test asserts today

| Step in `integration-three-tier.sh` | Helper command | What is checked | Kind |
|---|---|---|---|
| Workers connected (`_three_tier_lib.sh`) | `wait-heartbeat` | a heartbeat row exists for the component | presence |
| measure | `wait-verdict-type quality_breach --service fraud-detect` | newest such verdict exists | presence |
| correlate | `wait-assessment-kind correlation_snapshot` | newest snapshot exists, any service | presence |
| respond | `wait-verdict-type triage` | newest triage verdict exists, any service | presence |
| respond | `wait-case --service fraud-detect` | a case exists for the service | presence |
| learn | `wait-assessment-kind retrospective`, else `calibration_signal` | either exists, any service | presence |
| lineage | `assert-lineage TRIAGE QUALITY_BREACH` | the breach id is among the triage verdict's ancestors | content |
| bench | `fetch-case-via-bench --state pending` | bench's read path returns at least one case | presence |
| latency | `assert-latency` | case created within 30 s of the breach | content |

Two of nine are content checks. Both have caught real bugs (the lineage
check caught the verdict_type setter bug in opensrm-saun.1.2.3).

`test/integration-thresholds.sh` (opensrm-x0r9, written later) is the
model to copy: `wait-threshold-evaluation` and `wait-threshold-breach`
match on bound, status, measured value, severity, the breaching bound
names and the parent assessment, and it has a negative control
(`assert-no-verdict`). Nothing below applies to it.

## Findings

Each row is a place where "it happened" could be "it happened with the
right content". The scenario is fixed: `fraud-detect`, `reversal_rate`
target 98.5, driven to a reversal rate of 0.08 at 100 rps, so the SLI
settles near 92.

| # | Assertion | What a wrong system would still pass | Proposed check | Cost | Would have caught |
|---|---|---|---|---|---|
| 1 | `quality_breach` exists | any severity; the wrong SLO; a target or value in the wrong convention | On `data`: `slo_name == reversal_rate`, `judgment_type == reversal_rate`, `target == 98.5`, `current_value` below the target and above 85, and `severity` equal to what the documented thresholds give for that `target` and `current_value` (under 200% of budget low, under 500% high, else critical). The last one is a consistency check, so it does not depend on when in the window the first breach fires. | small | opensrm-pa2w (severity always critical); a ratio-versus-percent slip in `target` or `current_value` |
| 2 | `correlation_snapshot` exists, any service | a snapshot for another service, or one that does not name the breach | Pass `--service fraud-detect`; assert `data.parent_ids` contains the breach id, `data.domain.service == fraud-detect`, `data.event_count >= 1`. | small | a snapshot emitted with the wrong trigger ids (the case then anchors to the wrong verdict) |
| 3 | `triage` exists, any service | a triage verdict for another service | Pass `--service fraud-detect`. The lineage check already ties it to the breach, so nothing more is needed here. | trivial | a triage verdict filed under the wrong service |
| 4 | case exists | wrong priority; a case anchored to an unrelated verdict | `CASE_UNDERLYING_VERDICT` is printed and never compared: assert it is the snapshot id or the breach id (respond uses the snapshot when correlate ran, the breach on the fallback path). `CASE_PRIORITY` is printed and never compared: assert the value core derives for this scenario's blast radius with an active incident (not established by this review). | small, but see the open question | a case pointing at the wrong verdict, which breaks the bench briefing; a priority-map regression |
| 5 | learn output exists | a `calibration_signal` about any verdict at all satisfies the fallback | For `retrospective`: `--service fraud-detect`. For `calibration_signal`: assert `data.verdict_id` is one of this run's verdicts and `data.verdict_type` is set. | small | learn scoring a verdict from outside the incident |
| 6 | bench returns at least one case | bench returning some other case | Assert the case id from step 4 is among the returned ids (`BENCH_CASE_ID` is printed, never compared). | trivial | a bench filter or state bug that hides the new case |
| 7 | heartbeat exists | a component reporting itself unhealthy | `HEARTBEAT_HEALTH` is printed, never compared: assert it is the healthy value. | trivial | workers connected but degraded at boot |
| 8 | newest row is taken | the wrong row when more than one matches | `wait-verdict-type`, `wait-assessment-kind` and `wait-case` return `rows[0]`. Core orders verdicts and assessments newest first and cases by priority then age. With one breach per run this is safe today; a `--where key=value` style content filter (finding 1 to 5 need one anyway) removes the dependence on order. | folded into 1 to 5 | a second emitter making the test read a different row |

`test/e2e-test.sh` runs the same seven presence checks and the lineage
check, so every row above applies to it as written.

`demo/demo.sh` uses the helper to pace a narrated demo and to print what
it found. Its calls are not assertions of correctness and are out of
scope: sharpening them would make the demo fail on stage for reasons the
audience cannot see.

## Recommendation

Do, as one change to the helper and the two test scripts:

- Findings 1, 2, 3, 5, 6 and 7. They need one new optional mechanism in
  `three_tier_assertions.py` (content matching on the row a `wait-*`
  command returns, as `integration-thresholds.sh`'s commands already do
  for thresholds) and a few extra arguments at the call sites. Finding 1
  alone is the one the bead was filed for.
- Finding 8 comes free with that mechanism.

Needs a ruling before it is done:

- Finding 4, the priority half. Core derives a case's priority from the
  blast radius respond sends (the incident's environment) and whether an
  incident is active: `production` and `staging` map to `P0` to `P2`, and
  anything else, an unset environment included, to `P3`. This review did
  not establish which environment this scenario's incident carries, so
  the expected value has to be read off a run first. If it turns out to
  be `P3` by default, asserting it would pin today's behaviour, and
  whether an AI-gate breach in an unspecified environment should be `P3`
  is a product question a test should not settle by accident. The
  underlying-verdict half of finding 4 has no such question and can go
  with the rest.

Not worth doing:

- Sharpening `demo/demo.sh` (above).
- Asserting on the triage verdict's own content (severity, team,
  reasoning). Under `NTHLAYER_LLM_STUB=canned` those values are the
  stub's, so the assertion would test the stub.
- Asserting the retrospective's body beyond its service and that it
  exists. Its content is covered by nthlayer-workers' own tests, and the
  integration test's job is the seam.

## How to verify the change when it is made

The integration test runs nightly and on dispatch
(`integration-three-tier.yml`), not on pull requests. A change to its
assertions should be run once locally (`./test/integration-three-tier.sh`,
Docker required) before merge, and each new check should be shown to fail
when the value it guards is wrong: for finding 1, by forcing
`classify_severity` to return `critical` in a scratch copy of workers.
A content check nobody has seen fail is a presence check with more
arguments.
