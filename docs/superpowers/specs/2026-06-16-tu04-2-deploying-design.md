# tu04.2 — Deploying nthlayer-core

**Bead:** `opensrm-tu04.2` (P2)
**Parent:** `opensrm-tu04` (Phase 3-DOC epic)
**Date:** 2026-06-16
**Repo:** deliverable lands in `nthlayer-core/`; one link added in `nthlayer/README.md`

## Problem

The only deployment material for `nthlayer-core` today is two lines in the README:

```bash
pip install nthlayer-core
nthlayer serve --host 0.0.0.0 --port 8000
```

That is not "step-by-step from zero." An evaluator on a fresh machine has no documented path to install, configure manifests, post a signal, verify a verdict, or recover from any of the failure modes a fresh install actually produces. There is also no documented hardening pattern, even though core ships with no built-in backup primitive and the WAL-mode SQLite it uses is exactly what Litestream consumes.

The bead is scoped to **core-only, evaluator audience**. Workers and bench have their own deployment surfaces and will get their own guides (future tu04 children or follow-ons). This bead's value is a doc that takes an operator from "nothing installed" to "verdict round-tripped through the running server" without reading source code.

The bead body from 2026-04-22 references an `nthlayer.yaml` config file. **No such file exists** in the current implementation — config is CLI flags + two env vars by design. The spec documents the surface that exists; it does not introduce config to match a stale bead body.

## Design

### File location and host repo

Canonical deliverable: `nthlayer-core/docs/deploying.md`.

The doc lives with the code being deployed. The principle: this is the one human-facing doc whose contents CI can mechanically validate (install commands, flag names, env-var names — content that silently rots as code moves). Put the doc where its potential CI lives, and core's pipeline can keep the doc honest. Lift it to the front-door repo and you sever it from that machinery.

Front-door discoverability handled by one line in `nthlayer/README.md` getting-started section:

```markdown
Deploying core: see [nthlayer-core/docs/deploying.md](https://github.com/rsionnach/nthlayer-core/blob/main/docs/deploying.md)
```

Absolute GitHub URL — `nthlayer/README.md` renders on PyPI and GitHub independently of core's working tree. **A link, not a summary page** — a summary would re-introduce the duplication-and-drift the core-canonical decision exists to avoid.

File name is plain `deploying.md`, not `deploying-core.md`. The repo already scopes it to core. A `-core` suffix only earns its keep next to siblings, which there are none of in core's `docs/`.

### Document structure — three Diátaxis modes

```
# Deploying nthlayer-core

## Tutorial: zero to first verdict
## Reference
  ### CLI
  ### Environment variables
  ### Manifests directory layout
  ### Troubleshooting
## How-to: hardening for production
  ### Durable storage with Litestream
```

Three top-level sections = three modes (tutorial / reference / how-to). The how-to gets its own `##` so it can graduate into a standalone document later without restructuring this one. The split is also what makes the doc CI-validatable later: tutorial → runnable script; reference → drift-checked against `cli.py` and `server.py`. Building that harness is **deferred to a followup bead** — let the doc stabilize first.

### Tutorial: zero to first verdict (~600–800 words)

Eight copy-pasteable steps, linear, ending with a verdict the reader can see in the response:

1. Install uv (link to upstream installer; do not reproduce inline).
2. `uv tool install nthlayer-core`; verify with `nthlayer --version`.
3. Pick a manifests directory — clone `opensrm/examples/` or use an empty dir (empty catalogue is valid: server starts, verdicts work, no rules match).
4. `NTHLAYER_MANIFESTS_DIR=./examples nthlayer serve` in one terminal; expected log lines.
5. `curl localhost:8000/health` → `{"status": "ok"}`. Confirms install before going further.
6. POST a signal that matches one of the example manifests; show the verdict id in the response.
7. `curl localhost:8000/verdicts/<id>` — confirm round trip.
8. `curl localhost:8000/verdicts` — confirm store is real.

Step 6 needs a concrete signal payload. During writing, pick whichever of `api-minimal.yaml` / `ai-gate-minimal.yaml` produces the cleanest matching-signal shape **without an LLM worker in the loop**. If neither cleanly produces a non-empty rule-match verdict in core-only mode, the step degrades to "POST a signal, get an empty-catalogue verdict back" and the doc is honest about that. The round trip works either way; the acceptance is that the operator sees a verdict id come back from POST and reads the same verdict back from GET.

No prose explaining what NthLayer *is* — that's the README's job. The tutorial assumes the reader already chose to deploy.

### Reference (~1k words)

**CLI subsection.** The whole CLI today is `nthlayer serve [--host HOST] [--port PORT]` and `nthlayer --version`. Defaults `0.0.0.0:8000`. One sentence flags that `--store-path` and `--manifests-dir` are env-var-only **by design** (not framed as an apology — as information), with a pointer to the env-var subsection.

**Environment variables subsection.** Two-row table:

| Env var | Purpose | Default |
|---|---|---|
| `NTHLAYER_STORE_PATH` | SQLite database path | `nthlayer.db` (cwd-relative) |
| `NTHLAYER_MANIFESTS_DIR` | Directory of OpenSRM YAML manifests | unset (catalogue empty) |

One paragraph per var: what happens when unset, what relative paths resolve against, what file modes are needed. The `README.md` env-var table gets a link pointing at `deploying.md` as the canonical home, removing duplication.

**Manifests directory layout subsection (~150 words).** Convention only: `*.yaml` at the top level of the directory; one service per file; catalogue loads everything matching `*.yaml`. Pointer to `opensrm/examples/` for samples. Mention `POST /manifests/-/reload` for hot-reload. **No** deep dive on manifest schema — that's tu04.3 territory; link to it as a forward pointer.

**Troubleshooting subsection (~600 words).** Seven-row table; each row gets one expanded paragraph below it (what to look for in logs, what's the underlying invariant):

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `nthlayer: command not found` after install | uv tool-shim dir not on `PATH` | `uv tool update-shell` (or add `~/.local/bin` to `PATH`) |
| 2 | `OSError: [Errno 48] Address already in use` | Port 8000 taken | `nthlayer serve --port 8001` or kill the prior process |
| 3 | `sqlite3.OperationalError: unable to open database file` | Cwd not writable, or `NTHLAYER_STORE_PATH` points at a missing dir | `NTHLAYER_STORE_PATH=/tmp/nthlayer.db` or chdir to a writable dir |
| 4 | `sqlite3.OperationalError: database is locked` (persistent, not transient) | Two `nthlayer serve` processes on the same DB | Kill the duplicate; one writer per store. WAL + 5s busy-timeout handles transient contention, not two writers |
| 5 | `GET /manifests` returns `[]` despite `NTHLAYER_MANIFESTS_DIR` set | Relative path resolved from wrong cwd, or dir is empty | Use an absolute path; check server logs for the load summary |
| 6 | One manifest missing from `GET /manifests` even though the file exists | Invalid YAML or schema mismatch; catalogue skips bad manifests rather than crashing the server | Check server logs for the parse error; fix the YAML; `POST /manifests/-/reload` |
| 7 | Local `curl` works, remote `curl` times out | Cloud firewall / security group / host firewall blocks 8000 | Open the port, or bind `--host 127.0.0.1` and SSH-tunnel |

Explicitly out of scope for the troubleshooting table, called out in a one-liner so the reader knows it is not an oversight:
- LLM provider keys / worker failures — workers aren't deployed in core-only.
- TLS / reverse-proxy setup — see the hardening how-to.
- Authentication — core has none in v1.5; mentioned in the how-to as "put this behind your own gateway."

### How-to: hardening for production (~400 words)

Three subsections:

**4a. What this section is for** — two sentences. Core in v1.5 ships zero auth, single-process SQLite, no built-in backup. This how-to covers the **one** prod-hardening step with an upstream-recommended pattern (durable storage). Everything else (auth, TLS, supervision, multi-region) is one-line pointers to "your existing infra owns this."

**4b. Durable storage with Litestream — sidecar pattern.** Five mini-sections:

1. **Why Litestream specifically.** One sentence: it streams SQLite WAL to S3-compatible object storage with no app changes; core writes to SQLite normally and Litestream replicates underneath. We recommend it because v1.5 core has no backup primitive of its own and the WAL mode it already uses is exactly what Litestream consumes.
2. **The two processes.** `nthlayer serve` and `litestream replicate` run side-by-side pointing at the same `NTHLAYER_STORE_PATH`. Show both the raw two-process pattern and Litestream's `replicate` wrapper around the serve command; recommend the wrapper.
3. **Minimal `litestream.yml`.** ~10-line config block: one `dbs` entry, S3 replica with `bucket` / `path` / `endpoint` / `access-key-id` / `secret-access-key`. Placeholders, not real values.
4. **Restore procedure.** Single command: `litestream restore -o ./nthlayer.db s3://...`. Two-sentence narrative on when you'd run it (cold-start a new VM; recover from disk loss).
5. **What this does NOT give you.** Explicit: not HA, not point-in-time-with-zero-data-loss, not multi-writer. Last-replicated-WAL-frame is the recovery bound. If you need stronger guarantees, that's not Litestream's job and not core's either.

**4c. Things this how-to deliberately does not cover.** Bulleted list — auth / TLS / reverse proxy; process supervision (systemd / compose / k8s); multi-region / HA; migrating an existing `nthlayer.db` into a Litestream setup. Each is a future how-to bead, not a TODO in this one.

**Honesty disclaimer at the top of section 4b** — one line: *"This procedure is documented from upstream sources; end-to-end validation against S3 is tracked in followup bead opensrm-tu04.2.2."* The Tutorial section is validated against a clean tmpdir locally as part of this bead's acceptance; the Litestream how-to is a documented pattern, not a tested one. Do not claim tested when not tested.

## Acceptance mapping

The bead's four acceptance criteria map to specific sections:

| Acceptance | Where satisfied |
|---|---|
| Step-by-step from zero | Tutorial section (8 steps) |
| Config reference | Reference → CLI + Environment variables + Manifests directory subsections |
| 5+ failure modes | Reference → Troubleshooting subsection (7 rows) |
| Tested on fresh machine | Tutorial validated in a clean tmpdir during writing; commit message documents the run-through. **Not** validated against a cloud VM with real S3 — that's how-to scope, deferred to follow-up. |

## Out of scope (this bead)

- **CI drift gate.** `assert_parity()`-style test that the env-var table in `deploying.md` matches `os.environ.get(...)` calls in `server.py`, plus same for CLI flags vs. `cli.py`. Deferred to `opensrm-tu04.2.1` — the parity check should be written against a doc that has stabilized, not one whose reference table is still churning.
- **End-to-end Litestream validation.** Requires real S3 credentials and a clean VM. Deferred to `opensrm-tu04.2.2`, filed only if/when needed.
- **Workers + bench deployment.** Out of bead scope by audience decision (core-only, evaluator).
- **Manifest authoring depth.** Belongs in `opensrm-tu04.3` (P3-DOC.3 manifest authoring guide).
- **Auth / TLS / process supervision / multi-region / HA.** Listed explicitly in the how-to's "does not cover" list as future-bead candidates.

## Followups filed at close

- **`opensrm-tu04.2.1`** (P3) — Wire deploying.md to CI. Drift-check the env-var table against `server.py` and the CLI flag list against `cli.py`. Optional stretch: shell harness running the Tutorial section in a tmpdir.
- **`opensrm-tu04.2.2`** (P3) — Validate Litestream sidecar end-to-end on a fresh VM with real S3. File only if a real user needs the procedure validated.

## Why this scope, not bigger

Three-tier deployment, multi-component runbooks, prod hardening beyond Litestream, and authoring-grade manifest documentation are all valuable. None of them belong in this bead. The principle is "split when it earns it" applied in advance: each topic excluded above is shaped so that when it does earn its own treatment, the seam is already cut. The how-to graduates to its own doc; workers and bench get sibling `deploying.md` files in their own repos; the front-door accumulates links. No central doc to maintain, no cross-repo synchronization, no drift surface beyond what each repo's CI already polices.
