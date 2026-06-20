# Design — release-please via GitHub App token (`opensrm-l58r`)

**Date:** 2026-06-19
**Bead:** `opensrm-l58r` (P2, labels: ci, release)
**Status:** Approved, pre-implementation

## Problem

release-please PRs across the ecosystem sit indefinitely with no CI signal,
and `release.yml` does not auto-publish to PyPI after the release PR merges.
Both were observed during `opensrm-wetn`: `nthlayer-core` PR #4 and
`nthlayer-common` PR #13 were each parked 38 days (opened 2026-05-10) until a
human manually intervened.

### Root cause — verified 2026-06-18 via `gh`

The release PR is authored by the default `GITHUB_TOKEN` identity
(`app/github-actions`). Two distinct consequences, both confirmed against
real run history:

1. **Symptom A — PR CI gated.** `pull_request` workflow runs *are* created
   but land in conclusion `action_required` (0s duration, never execute),
   waiting on a manual "Approve and run." Evidence: dozens of
   `action_required` CI/dependabot-automerge runs on the
   `release-please--branches--main--components--nthlayer-core` branch
   (2026-06-11 → 06-17); the only `success` run (27714930626, 31s) was the
   manual approval during `opensrm-wetn`.

   *(Note: an earlier hypothesis that `GITHUB_TOKEN` recursion-suppression
   prevented the runs from being created at all was refuted — the runs exist,
   they are gated, not suppressed.)*

2. **Symptom B — no auto-publish.** `release.yml` (`on: release: published`
   / `push: tags: v*`) does not fire when release-please creates the
   release/tag via `GITHUB_TOKEN`. Evidence: v1.7.0's PyPI publish ran via
   `workflow_dispatch` (manual `gh workflow run`), not the tag push; the last
   auto `release`-event publish was v1.0.0 (2026-04-28).

A non-`GITHUB_TOKEN` identity on the release-please action resolves both: a
PR authored by an App identity runs CI without the `action_required` gate,
and an App-token-created release/tag triggers downstream workflows normally.

## Decision

**Option 1 — GitHub App token.** Chosen over a fine-grained PAT (no expiry to
rotate, scoped per-install, not tied to a person), over a cron-approver
(Option 3 — fixes only Symptom A, leaves B manual, hacky), and over a repo
settings toggle (Option 2 — uncertain coverage for bot PRs, fixes neither
cleanly).

## Scope

Five repos use release-please and receive the change:
`nthlayer-core`, `nthlayer-common`, `nthlayer-generate`, `nthlayer-workers`,
`nthlayer-bench`. The target step block is **byte-identical** across all
five, so the edit is uniform.

`nthlayer-override-adapter` has **no** `release-please.yml` (manual tagging) —
no change; documented here so a future reader does not "fix" a sixth repo.

## Per-repo workflow change

In each `.github/workflows/release-please.yml`, prepend an App-token step and
pass its output to release-please via the `token:` input. Everything else
(the `on:` trigger, `permissions:`, the Release-summary step) is untouched.

```yaml
jobs:
  release-please:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/create-github-app-token@v3
        id: app-token
        with:
          app-id: ${{ secrets.RELEASE_APP_ID }}
          private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}

      - uses: googleapis/release-please-action@v4
        id: release
        with:
          token: ${{ steps.app-token.outputs.token }}
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json
      # ... existing Release-summary step unchanged ...
```

Secret names (added per repo by the operator): `RELEASE_APP_ID`,
`RELEASE_APP_PRIVATE_KEY`.

## Operator runbook (one-time, manual — not automatable by the agent)

1. **Create the App.** github.com → Settings → Developer settings → GitHub
   Apps → New GitHub App.
   - Name: `nthlayer-release-bot`.
   - Homepage URL: any (e.g. the nthlayer repo URL).
   - Uncheck "Active" under Webhook (no webhook needed).
   - **Repository permissions:** `Contents: Read and write`,
     `Pull requests: Read and write`. Leave everything else `No access`.
   - "Where can this GitHub App be installed?": **Only on this account.**
   - Create. Note the **App ID**.
2. **Generate a private key.** On the App page → "Generate a private key" →
   download the `.pem`.
3. **Install the App** on the five repos (App page → Install App → select the
   five).
4. **Add secrets** in each of the five repos (Settings → Secrets and variables
   → Actions):
   - `RELEASE_APP_ID` = the App ID (numeric).
   - `RELEASE_APP_PRIVATE_KEY` = full contents of the `.pem` (including the
     `-----BEGIN/END-----` lines).

App installation tokens expire after 1 hour but are minted fresh each run by
`create-github-app-token`, so there is **no rotation burden** — unlike a PAT.

## Parked 1.8.0 (handled this session)

A `1.8.0` release PR in `nthlayer-core` was already parked in
`action_required` as of 2026-06-17. It is drained manually this session
(approve CI → merge → dispatch `release.yml`), independent of the gate fix —
the same drill as `opensrm-wetn`. The App-token change prevents recurrence on
all *future* releases.

## Verification

No clean local unit test exists — the behaviour is a GitHub-side trigger
property. The proof is the next release in any of the five repos:
release-please re-runs on the next push to `main`, recreates the PR under the
App identity, CI runs without `action_required`, and on merge the tag push
fires `release.yml` to publish automatically. Until then, the change is
verified by inspection (correct action version, secret names, token wiring)
and by confirming the five edited files remain valid YAML with the existing
`permissions:` intact.

## Addendum — release.yml double-trigger (discovered during rollout)

Enabling auto-fire surfaced a latent defect. `release.yml` in all five
release-please repos triggered on **both** `release: published` **and**
`push: tags: v*`. Previously dormant (auto-fire never worked), this now means
every release spawns **two concurrent publish runs**; the loser fails with
PyPI `400 File already exists`. Observed live on `nthlayer-core` v1.8.0:
the `push`-triggered run published, the `release`-triggered run failed.

Fix: keep the canonical `release: [published]` trigger (+ `workflow_dispatch`
for manual fallback), drop `push: tags: v*`. Applied uniformly to the same
five repos. `nthlayer-override-adapter`'s `release.yml` uses a different model
(`push: branches: [main]` + `tags`, no release-please) and is left unchanged —
out of scope for this release-please fix.

## Review

Focused single review (proportionate for uniform config): one disciplined
pass on the canonical edit — `create-github-app-token@v3` (latest major,
verified 2026-06-19), secret
names, `permissions` sufficiency, `token:` wiring — then applied identically
to the other four.
