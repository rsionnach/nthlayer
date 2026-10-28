# opensrm-wo62.4 — route the legacy CLI stack through nthlayer-common (design)

Bead: route generate's legacy `parse_service_file`/`ServiceContext` stack
(12 CLI commands + plan/apply) through nthlayer-common. Parent epic opensrm-wo62.

## What research found (2026-10-27)

The move is not just mechanical. Common's `load_manifest` **drops three
legacy behaviours**:

| Legacy behaviour | Today | Common |
|---|---|---|
| Environment overlays (`--env`): `environments/{svc}-{env}.yaml` deep-merged into `service:` and `resources` | `specs/parser.py:81-110`, `environments.py`, `environment_merger.py` | stores `manifest.environment` only. No lookup, no merge. Backstage and docs already pass `environment` to `load_manifest`, so `--env` is already a silent no-op there |
| `template:` expansion (built-in `specs/builtin_templates/*.yaml` + `.nthlayer/templates`) | merged at parse time | stores the name only. E.g. the golden `sloth/services__api-minimal` is "No SLOs found", where legacy produces SLOs + PagerDuty. 9 corpus files use `template:` |
| `${service,team,tier,type,support_model,language,framework,env}` substitution across every spec | `render_resource_spec` | none. The manifest path substitutes 4 variables in the sloth query only. 9 corpus files use `${` |

Other gaps:
- **PagerDuty keys.** `urgency`, `auto_resolve_timeout` and
  `create_escalation_policy` are not in common's model.
- **Smaller fields.** `spec.metrics` dashboard overrides and SLO
  `latency_threshold`/`objectives[]` shapes are dropped too.
- **Dependency → technology extraction** exists in three versions (alerts,
  loki, common + `extract_dependency_technologies`). They disagree, so
  output changes for legacy files.
- **plan/apply** reads raw YAML (`ResourceDetector`, `service_def["service"]`),
  so srm/v1 and v2 files detect nothing today.
- **Unwired commands.** `dependencies` and `dashboard-validate` are not wired
  into the CLI.
- **ownership bug.** `ownership` reads `context.owner`, which doesn't exist,
  so it is always None.
- **Coverage.**
  - None of the 12 commands, and neither plan nor apply, has a golden cell.
  - No golden covers environment overlays.
  - 28 test files import the legacy stack directly, and about 19 more reach
    it through commands.
- **Format support.** srm/v1 files under `examples/services` are rejected
  by the legacy parser today, and would start working after the switch.

## Decisions for Rob

- **D1 Environment overlays.**
  - *Recommend:* implement the overlay merge in common's legacy loader
    (`load_manifest(path, environment=...)` finds and merges the env
    file). That is one implementation, and it also fixes the silent no-op
    in backstage and docs.
  - Alternatives: a generate-side pre-load step, or drop `--env`
    overlays (a breaking change).
- **D2 `template:` expansion.**
  - *Recommend:* move legacy template expansion into common, including
    the built-in templates as package data, plus a `templates_dir` for
    `.nthlayer/templates`.
  - Alternatives: keep expansion in generate as a pre-load step, or
    deprecate legacy templates in favour of v2 `ServiceManifestTemplate`.
- **D3 `${var}` substitution.**
  - *Recommend:* common, at load, for the legacy format, with the same
    variable set as today.
- **D4 PagerDuty keys.**
  - *Recommend:* add `urgency`, `auto_resolve_timeout` and
    `create_escalation_policy` to common's `ownership.pagerduty`.
- **D5 Dependency extraction.**
  - *Recommend:* one rule set, common + `extract_dependency_technologies`.
  - Accept the resulting alert/loki changes for legacy files as a listed
    golden diff, rather than porting generate's name heuristics.
- **D6 Unwired commands.**
  - *Recommend:* delete `dependencies` and `dashboard-validate` rather
    than migrate them.
  - Fix the `ownership` `context.owner` bug as part of the move.
- **D7 diff-envs / validate-env.**
  - *Recommend:* compare the two merged manifests that D1 produces,
    instead of raw resource dicts.
- **D8 Split the bead.** It is too big for one gate. Recommend turning
  wo62.4 into an epic-child set:
  - **wo62.4a (common, minor release):** D1–D4 in the legacy loader. Gated
    and released first, per the cross-repo rule.
  - **wo62.4b:** pin goldens on the legacy entry points:
    - the 6 legacy builders;
    - CLI cells for the 10 wired commands;
    - plan/apply with PagerDuty and Grafana stubbed;
    - new env-overlay cells (`payment-api-with-envs`, `examples/environments`).
  - **wo62.4c:** commands that already have a `*_from_manifest` twin
    (slo-generate/sloth, alerts, loki, recording-rules, dashboard,
    recommend-metrics). End-to-end CLI check that ai-gate threshold
    alerts appear.
  - **wo62.4d:** commands that need new manifest reads: slo, validate-slo,
    ownership, setup-pagerduty, diff-envs/validate-env.
  - **wo62.4e:** plan/apply. Manifest-based detection; handlers moved to
    the `*_from_manifest` functions.
  - **wo62.4f:** delete the legacy stack:
    - parser, `render_resource_spec`, the legacy builders, the validate
      legacy route, the `specs/__init__` exports, the unwired commands;
    - the `ServiceContext`/`Resource` adapter in dashboards only if it is
      rewritten.

    Released as generate 4.0.0.

  Each child gets its own checkpoint, golden-diff approval and R5 gate.

## Checkpoint plan (if D8 is accepted)

1. **Now:** record the rulings, create the child beads with dependencies
   (b → a, c/d/e → a and b, f → c, d and e), and write the design spec as
   a front-door PR. Stop.
2. **wo62.4a** (common). Stop after the release.
3. **wo62.4b** (pins only, no behaviour change). Stop.
4. **wo62.4c → 4d → 4e**, each one a gate with an approved golden diff.
   Stop between each.
5. **wo62.4f** + generate 4.0.0. Stop.

## Rulings (Rob, 2026-10-27)

- D8: the bead is split. The children are wo62.4.1 (=4a, common), .2 (=4b, pins),
  .3 (=4c), .4 (=4d), .5 (=4e, plan/apply) and .6 (=4f, delete + 4.0.0).
  wo62.4 is now their umbrella.
- D1: environment overlays go in common's loader.
- D2: template expansion moves into common.
- D5: common's single dependency rule set wins.
- D3, D4: shipped as recommended in nthlayer-common 5.6.0 (wo62.4.1). D3 became
  an exact port of generate's two `${var}` passes (an environment pass before
  template lookup, then a per-spec pass), after the edge-cases review found that
  one pass broke parity.
- D6 (Rob, 2026-10-28): delete the unwired `dependencies` and `dashboard-validate`
  commands in wo62.4.6 rather than migrate them; fix ownership's
  `context.owner` (always None) during the wo62.4.4 move.
- D7 (Rob, 2026-10-28): diff-envs / validate-env compare the two merged
  manifests that common's overlays produce (field-level differences). The
  wo62.4.2 goldens for these commands are expected to change in wo62.4.4.
- Correction to the plan: 4.2 (pins) does not depend on 4.1. It pins today's
  legacy behaviour. The dependencies are .3/.4/.5 → .1 and .2, and .6 → .3,
  .4 and .5.

## Rulings (Rob, 2026-10-28), from wo62.4.3's golden review and gates

wo62.4.3's first golden diff showed three more legacy-loader parity gaps.
Following the cross-repo rule, they were split into a common child,
**wo62.4.7**, which was gated and released as nthlayer-common 5.7.0 before
wo62.4.3 resumed.

- **R1 — latency threshold.** `SLODefinition` gains `threshold_ms`. The
  legacy loader reads three keys, in this order:
  1. `spec.indicator.threshold_ms`
  2. `spec.threshold_ms`
  3. `spec.latency_threshold`

  generate's own legacy code disagreed on which key to use:
  - sloth read only the first key;
  - recording rules read only the third, which no corpus file uses, so they
    always got 500 ms;
  - `nthlayer setup` writes the second.

  Without the field, generate's manifest path used the 0–100 objective as
  the bound, so "99% under 500ms" became `> 0.099`. A value that is not a
  number, not finite, or not positive is a `ManifestLoadError`.
- **R2 — cache/queue technology.** A legacy cache's or queue's `type:` is
  stored in `Dependency.database_type`, as a database's already was. The
  name is kept and the field redocumented as the dependency's technology;
  `database_type` is an NthLayer extension, not part of the spec.
- **R3 — alias.** `stream-processor → stream` goes into
  `SERVICE_TYPE_ALIASES` and applies to every format, alongside
  `background-job` and `pipeline`.
- **R4 (mid-gate, wo62.4.7 edge-cases).** An environment overlay that
  declares any threshold key first removes the base's threshold keys.
  - Without this, the deep merge kept both values and R1's order picked the
    base one: payment-api with `--env prod` got 500 where the overlay said
    300.
  - This departs from generate's merger, which lost the overlay value too.
- **Golden diff for wo62.4.3 approved.** 255 goldens changed and 23 are new:
  analytics-stream now loads, so it joins every library and CLI cell.
  - No cell moves from success to failure.
  - srm/v1 and v2 files that the legacy parser rejected now generate.
  - Recording rules follow the declared `indicator.type`, not the SLO's
    name, and use the declared bound.
  - Alert, loki and dashboard content follows the single dependency rule
    set (D5). An untyped `redpanda` queue defaults to kafka; Redpanda speaks
    the Kafka protocol.
  - email-worker's override with no objective is dropped.
  - Any manifest that starts to load adds new goldens. A golden review has
    to include untracked files, not just `git diff`.
- **Untemplated technology (mid-gate, wo62.4.3 edge-cases).** If a cache or
  queue has a technology with no dashboard template, generate-dashboard
  leaves it out with a warning instead of failing the whole dashboard, as
  alerts already did. notification-service and `opensrm/worker.reliability`,
  whose sqs queues have no template, now get a dashboard. Legacy failed on
  both.
- **Recording-rule formatting (mid-gate, wo62.4.3 edge-cases).**
  - `le` is written with `prometheus_le` (Go `%g`).
  - The `threshold` label uses `%g`, so it reads `500ms` as the legacy
    builder wrote it.
- **Pre-flight override (wo62.4.3 gate).** eco-doctor reported `STALE` for
  generate's main checkout. That checkout's lock pinned common 5.6.0, and
  the floor bump was the branch under review, so it could not clear before
  merge.
  - The gated worktree had no range finding and resolved common 5.7.0.
  - The gate ran, and the override is recorded in
    `.claude/r5-state-wo62-4-3-completed.json`.
- **Follow-ups filed:**
  - **wo62.4.8:** plural `indicators:` lists and `message_queues:`, which
    neither common nor the legacy builders read.
  - **wo62.4.9:** `migrate` drops `threshold_ms`.
  - **wo62.4.10:** common raises a bare `AttributeError` on a malformed
    resource spec. generate's CLIs catch it at their boundary until it is
    fixed.

Shipped: nthlayer-common 5.7.0 (rsionnach/nthlayer-common#111). Floor bumps:
core#29, bench#28, workers#30 and adapter#27. generate is
rsionnach/nthlayer-generate#54.
