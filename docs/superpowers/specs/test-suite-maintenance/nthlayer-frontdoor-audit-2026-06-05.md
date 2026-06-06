# nthlayer (front-door) test-suite audit (Phase 1)

- **Repo:** `nthlayer` (front-door + ecosystem hub — meta-package, action, integration test infra, docs)
- **HEAD:** `fca6dafe05a417bfbc47601e9d1c0e0c4037a104` (branch `main`)
- **Working tree:** clean (`git status --short` empty pre-audit)
- **Bead:** opensrm-zfyh.6
- **Date:** 2026-06-05
- **Scope note:** this repo has **no Python test suite**. It hosts the canonical `docs/testing.md` plus integration shell scripts, a meta-package, and docs. The 6-section checklist is adapted accordingly; "no Python suite" is the framing, not a finding-of-rot.

## 1. Test count

- No `pytest` collection — only `pyproject.toml` is `./meta-package/pyproject.toml` (verified `find . -maxdepth 3 -name "pyproject.toml"`), dependency-only (`packages = []`).
- Test-shaped shell scripts: `find test demo -maxdepth 2 -name '*.sh' -type f | wc -l` → **11** (`test/`: 7 — `_three_tier_lib.sh`, `e2e-test.sh`, `integration-chain.sh`, `integration-three-tier.sh`, `learn-recommendations-integration.sh`, `test_demo_paths.sh`, `test_demo_start_lock.sh`; `demo/`: 4 — `_paths.sh`, `_start_lock.sh`, `demo.sh`, `verdict-feed.sh`).
- Python helpers in `test/` (4): `fake-service.py`, `three_tier_assertions.py`, `webhook-receiver.py`, `test_jmy18_smoke.py`. `grep` confirms `three_tier_assertions.py` + `fake-service.py` invoked **only by shell scripts** (`e2e-test.sh:48`, `integration-three-tier.sh:55,135`, `_three_tier_lib.sh:149`, `demo/demo.sh:31,33`); `test_jmy18_smoke.py` + `webhook-receiver.py` standalone (no sibling-script invocation).
- Meta-package smoke gate: **none** (`CLAUDE.md`: "dependency-only … nothing to smoke-test"). Docs-site link-check / markdownlint: none configured (§2).

## 2. Lint state

- **`bash -n`** (`ci.yml` job `shell-syntax`) against every `find demo test -maxdepth 2 -name '*.sh'`. Last 3 main runs: success / failure / failure; most recent green (2026-06-01).
- **mkdocs `--strict`** (`docs.yml`) on `docs-site/`. Verified via `grep -E "mkdocs.*strict" .github/workflows/docs.yml`.
- **No markdownlint / vale / link-checker** (`grep -rE "markdownlint|vale|lychee|linkcheck" .github/workflows/` → 0 hits). **No ruff/mypy on Python helpers** (`three_tier_assertions.py`, `fake-service.py`, `webhook-receiver.py`, `demo/render_explanation.py`, `demo/scenario-runner.py`; tally excludes `test_jmy18_smoke.py`: standalone JMY18 smoke test, not an integration helper) — no workflow runs them; root has no Python `pyproject.toml`. **0/5 helpers linted.**

## 3. Infrastructure rot

- `test/integration-chain.sh` still references **consolidated/removed** worker repos (removed from disk 2026-05-08 under `opensrm-hty.7`): `uv run --directory nthlayer-learn/lib/python …`, `nthlayer-correlate correlate …`, producers `nthlayer-measure` / `nthlayer-correlate` / `nthlayer-respond`. `test/prometheus.yml` scrapes `job_name: nthlayer-respond`. **Script cannot execute on a current checkout.**
- `test/e2e-test.sh`, `demo/verdict-feed.sh`, `demo/demo.sh` reference deprecated repos only inside header comments marked "legacy" / "deprecated" — not active code.
- Renamed-symbol scan: `grep -rE "AutonomyLevel\.FULL|slo_state" test/ demo/` → **0 hits**.
- Cross-repo path resolution: `test/test_demo_paths.sh` exercised by `demo-paths.yml` (last run green 2026-06-01) with stubbed sibling dirs at `WORKSPACE_ROOT`.

## 4. Conceptual rot indicators

- `test_<function_name>`-style filename convention used by the two regression guards (`test/test_demo_paths.sh`, `test/test_demo_start_lock.sh`). Shell-tier; bead taxonomy is Python-tier — cross-tier ambiguity, not rot.
- Both regression guards encode `cmd_start` implementation detail (probe-state file format, path-resolution). Design intent per `opensrm-oey5` / `opensrm-36es` — regression pinning, not testing.md §Lifecycle rot.
- Dangling Markdown / spec xrefs: sample below in §Divergences; exhaustive sweep deferred to Phase 2. `>20 tests in a file`: N/A — no Python tests.

## 5. CI state

Status from `gh run list --workflow=<name> --branch=main --limit 3` (release by tag):

- `ci.yml` (shell-syntax, post-`opensrm-0buj`): last 3 = success / failure / failure; most recent green (2026-06-01).
- `docs.yml` (mkdocs strict + Pages): last 3 all success; most recent 2026-04-11 (no doc-site pushes since).
- `demo-paths.yml`, `demo-start-lock.yml`: last runs success (2026-06-01 each).
- `integration-three-tier.yml` (nightly cron + dispatch): last 3 cron runs all success (2026-06-05, -04, -03).
- `release.yml` (`meta-v*` tags): last 3 success — `meta-v1.0.0`, legacy `v0.1.0a20`, `v0.1.0a19`.
- `publish-docker.yml`: last 3 all failure (2026-06-01, 2026-05-19, 2026-05-14). **Sustained red signal — surface, do not triage.**
- Aux out-of-scope: `release-please.yml`, `dependabot-automerge.yml`.

## 6. Documentation state

- Root: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`, `ATTRIBUTION.md`, `LICENSING_COMPLIANCE.md` all present.
- `docs/`: 9 files + 4 dirs (`archived-specs/`, `plans/`, `roadmap/`, `specs/`, `superpowers/`). Notable: `testing.md` (17,682 bytes, 2026-05-02 per `stat -f %Sm`), `integration-testing.md`, `release-runbook.md`, `metrics-contract.md`. `docs-site/` (mkdocs) built strict by `docs.yml`. The 5 prior sibling audits sit alongside this file under `docs/superpowers/specs/test-suite-maintenance/`.
- `docs/testing.md` xref sample: L15/L209 `test/integration-chain.sh` (exists, but body deprecated — see §3); L274 `nthlayer-common/tests/contracts/fixtures/` (absent — matches `opensrm-zfyh.1`); L327 `ci.yml` (present here; cross-tier validity in §Divergences).

## Divergences from testing.md

> **Note:** this audit covers the repo that *hosts* `testing.md` itself (`docs/testing.md`, 17,682 bytes, 2026-05-02). All §Divergences below evaluate against that file. The front-door has no Python test suite, so most §-claims map differently than for sibling library repos — surfaced as cross-tier ambiguity.

- **§CI workflow filename (line 327)** —
  - Doc says: every active repo has `ci.yml` running `uv` + `ruff` + `pytest`.
  - Repo reality: `ci.yml` present but runs `bash -n` only (header comment post-`opensrm-0buj` acknowledges this).
  - Unfamiliar pattern: cross-tier ambiguity — no Python suite to run.
- **§Unit / §Fixtures / §Integration (`tests/integration/`) / §Contract (`tests/contracts/`) / §Naming (`_test_` helper) / §Async** —
  - Doc says: `tests/test_*.py`, `tests/conftest.py`, `tests/integration/`, `tests/contracts/`, `_test_*` helpers, "all worker module tests are async."
  - Repo reality: **no `tests/` dir** (`find . -maxdepth 2 -type d -name tests` → 0). None evaluable.
  - Unfamiliar pattern (cross-tier): every claim is library-tier-shaped; the front-door is meta-package + scripts + docs. Treat as N/A-by-tier.
- **§E2E `test/integration-chain.sh` (line 15 / 209)** —
  - Doc says: canonical E2E, measure → correlate → respond → learn.
  - Repo reality: file exists; references `nthlayer-{measure,correlate,respond,learn}` repos consolidated 2026-04-26 + removed 2026-05-08. Not executable on current layout.
  - Unfamiliar pattern; needs human review: retain as historical, or rewrite against `nthlayer-workers`?
- **§Contract fixtures (line 274) — `nthlayer-common/tests/contracts/fixtures/`** —
  - Doc says: shared contract fixtures live there. Repo reality: directory absent (also flagged by `opensrm-zfyh.1`). Stale at source.
- **§Maintenance — "Once a year, every active repo gets a test suite audit"** —
  - Doc does not prescribe how to audit a non-Python repo. This epic (`opensrm-zfyh`) is the first ecosystem-wide pass; the front-door case (this file) is the one the doc did not anticipate.

## Validation

- Working tree clean: `cd nthlayer && git status --short` empty pre-audit; this audit is the sole addition.
- No files outside `docs/superpowers/specs/test-suite-maintenance/` modified.
- Reproducers: `find test demo -maxdepth 2 -name '*.sh' -type f`, `grep -rn "three_tier_assertions\|fake-service\|webhook-receiver" test/ demo/ .github/workflows/`, `grep -rE "nthlayer-(observe|measure|correlate|respond|learn)\b" test/ demo/`, `grep -rE "AutonomyLevel\.FULL|slo_state" test/ demo/`, `gh run list --workflow=<each>.yml --branch=main --limit 3`, `stat -f "%Sm" docs/testing.md`, `ls ../nthlayer-common/tests/contracts/`.
- testing.md cross-referenced against the 5 sibling audits closed under `opensrm-zfyh.{1..5}`; corrected location (in-repo, not absent) upheld as canonical anchor.
