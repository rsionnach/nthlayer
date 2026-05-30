# OPENSRM Spec Migration Cleanup Design (opensrm-m43k)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-30. Bead: `opensrm-m43k`. Discovered state: bead is partially complete — a prior pass already moved the OPENSRM-*.md files out of ecosystem root into the `opensrm` repo via the `chore/specs-and-docs` branch. This bead closes the remaining acceptance criteria with a much-reduced scope than the original 2026-05-05 description.

**Foundation:**
- `opensrm/OPENSRM-CORE-v2.md` — v2 core spec, present at opensrm repo root on `chore/specs-and-docs` branch.
- `opensrm/OPENSRM-RBAC-EXTENSION-v2.md` — v2 RBAC extension, same branch + location.
- `opensrm/OPENSRM-RBAC-EXTENSION.md` — v1 RBAC extension (superseded by v2), same branch + location. NO archive marker on the file; reader has no signal that v2 supersedes it.
- `nthlayer/docs/specs/NTHLAYER-SPEC-INDEX-v1.md` (lines 13, 15) — the canonical NthLayer spec index introduces the OPENSRM-* files by bold-bare filename. The only true discoverability spot in the nthlayer docs where a reader is expected to navigate to the file.
- 5 other nthlayer files mention OPENSRM-* by name (mostly section-anchor prose like `OPENSRM-CORE-v2 §5` in plans/specs). These are NOT markdown links — they're textual references that still resolve as prose.

---

## 1. Problem statement

The 2026-04-26 ecosystem-to-front-door migration deferred three OPENSRM-*.md files from being moved. A subsequent pass (chore/specs-and-docs branch, commits 30c4d99 + 575fbd8) imported them to the `opensrm` repo root. The bead's first four acceptance criteria are partially or fully satisfied:

| AC | State |
|---|---|
| 1. Files no longer at ecosystem root | ✅ Done (verified by glob) |
| 2. Files land in opensrm/ at agreed paths | ✅ Done (at opensrm root, not the bead's originally-proposed spec/v2/ subdir) |
| 3. Cross-references in nthlayer updated | ⚠️ Partial — 1 spot of true discoverability still bare-named |
| 4. opensrm commits on a clean working tree | ⚠️ N/A — files live on chore/specs-and-docs (branch reconciliation deferred per § 4) |
| 5. SPEC INDEX renders correctly | ⚠️ Lines 13/15 are bold-name (not linked) — readers can't click through |

Plus a gap not in the original ACs: the v1 RBAC file at opensrm root carries no marker that v2 supersedes it. A reader who finds the file directly has no signal.

---

## 2. Existing surface

- `opensrm/OPENSRM-RBAC-EXTENSION.md` header currently reads:
  ```
  # OpenSRM RBAC Extension: Action Authorisation
  **Extension to:** OpenSRM v1
  **Version:** 1.0.0-draft
  **Status:** Draft
  ```
  No supersedence note.
- `nthlayer/docs/specs/NTHLAYER-SPEC-INDEX-v1.md` lines 13 and 15 introduce the v2 specs as bold-name only:
  ```
  1. **OPENSRM-CORE-v2.md** — The OpenSRM specification. ...
  2. **OPENSRM-RBAC-EXTENSION-v2.md** — Extension to OpenSRM for ...
  ```
- All other nthlayer references are textual prose / table cells (e.g. "OPENSRM-CORE §3" in tables, "Spec: OPENSRM-RBAC-EXTENSION-v2 §12" in plans). They read fine as prose; they don't pretend to be navigable links. No update needed.

---

## 3. Locked decisions

### 3.1 Keep OPENSRM-*v2 specs at opensrm repo root (no file moves)

The chore-branch import placed them at `opensrm/` root next to README/ARCHITECTURE/GOVERNANCE/REPO-SPEC. The bead originally proposed `opensrm/spec/v2/specification.md` to parallel `opensrm/spec/v1/specification.md`. We're NOT moving them: parallel structure is nice-to-have, the opensrm root already mixes spec-level docs, and a move means rewriting every internal anchor reference inside the spec files (cross-section navigation, image paths, etc.).

Rationale: minimum-viable-merge. If we later want a `spec/v2/` parallel, file a separate bead at that time.

### 3.2 Add inline archive marker to OPENSRM-RBAC-EXTENSION.md (v1)

Insert a one-block supersedence notice at the top of the file (between title and the existing metadata block):

```markdown
# OpenSRM RBAC Extension: Action Authorisation

> **⚠️ Superseded.** This is the v1 RBAC extension, retained for historical reference.
> The active specification is [`OPENSRM-RBAC-EXTENSION-v2.md`](OPENSRM-RBAC-EXTENSION-v2.md)
> in this same directory. Implementations should target v2; v1 is preserved only for
> consumers transitioning off the original draft.

**Extension to:** OpenSRM v1
**Version:** 1.0.0-draft
...
```

Rationale: a reader who lands on the v1 file via GitHub search, an old link, or directory listing immediately knows the active version exists. No file move, no rename, no behavioural change to anything depending on the v1 file's existence.

### 3.3 Make NTHLAYER-SPEC-INDEX-v1.md lines 13 + 15 navigable via GitHub URLs

Change the bare bold names to GitHub-linked text:

```markdown
1. **[OPENSRM-CORE-v2.md](https://github.com/rsionnach/opensrm/blob/main/OPENSRM-CORE-v2.md)** — The OpenSRM specification. ...
2. **[OPENSRM-RBAC-EXTENSION-v2.md](https://github.com/rsionnach/opensrm/blob/main/OPENSRM-RBAC-EXTENSION-v2.md)** — Extension to OpenSRM for ...
```

URL targets `main` branch on `rsionnach/opensrm`. The files will live on that branch once chore/specs-and-docs merges (which is § 4-out-of-scope but inevitable). A reader following the link before the merge would see "file not found"; after the merge, link works. The link is intentionally future-facing — preferable to a chore-branch URL that would itself become stale post-merge.

Rationale: only the SPEC INDEX is a discoverability spot. Other refs (plans, design docs) are prose and don't need to be clickable for the reader's mental model to work.

### 3.4 Skip updating the 5 other nthlayer files that mention OPENSRM-*

`docs/superpowers/plans/2026-04-21-phase-0-decisions.md`, `docs/superpowers/plans/2026-04-21-nthlayer-v1.5-epic-tree.md`, `docs/superpowers/specs/2026-04-20-v2-reconciliation-report.md`, `docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md`, `docs/superpowers/specs/2026-04-21-spec-revision-summary.md` all reference OPENSRM-* by name in prose / section-anchor form. None are broken; none claim to be links. YAGNI on a forced link-conversion pass. If a future doc style enforces "every spec mention must be linked," it gets its own bead.

---

## 4. Out of scope

- **Branch reconciliation:** `chore/specs-and-docs` on opensrm has 2 commits ahead of main + untracked `plans/` + `scripts/` directories (utility scripts: archive, create-audit-issue.sh, lint, sync_beads_to_github.py). Reconciling that branch + handling those untracked dirs is a separate concern; this bead operates within the existing branch state.
- **Moving files to `opensrm/spec/v2/`:** Per § 3.1, no file moves. Parallel-with-spec/v1 structure is a "nice to have" that's its own bead if ever wanted.
- **Updating prose / table-cell OPENSRM-* references in the 5 nthlayer files:** Per § 3.4, only the SPEC INDEX (true discoverability spot) gets links.
- **Archiving the v1 RBAC file to a `docs/archived-specs/` subdir:** Per § 3.1, no moves. The inline supersedence marker (§ 3.2) is the archive signal.
- **Touching the OPENSRM-* file CONTENT** other than the supersedence marker on v1 RBAC: this bead is about discoverability and migration cleanup, not spec edits.

---

## 5. Test surface

No new tests. Acceptance is:
- `grep -c "OPENSRM-RBAC-EXTENSION-v2.md" opensrm/OPENSRM-RBAC-EXTENSION.md` returns ≥ 1 (the supersedence marker mentions v2 by name).
- `grep -n "github.com/rsionnach/opensrm/blob/main/OPENSRM" nthlayer/docs/specs/NTHLAYER-SPEC-INDEX-v1.md` returns 2 lines (both v2 specs linked).
- Reading the v1 RBAC file's first 10 lines shows the supersedence notice clearly.
- Reading SPEC INDEX lines 13+15 shows them as markdown links to GitHub.

---

## 6. Implementation plan

Two edit sites:

1. **`opensrm/OPENSRM-RBAC-EXTENSION.md`** — Insert the supersedence notice (§ 3.2) between the H1 title and the existing `**Extension to:** OpenSRM v1` metadata block. Commit on the existing `chore/specs-and-docs` branch.

2. **`nthlayer/docs/specs/NTHLAYER-SPEC-INDEX-v1.md`** — Lines 13 + 15 only. Convert `**OPENSRM-CORE-v2.md**` and `**OPENSRM-RBAC-EXTENSION-v2.md**` to `**[…](https://github.com/rsionnach/opensrm/blob/main/…)**`. Commit on nthlayer main.

Two commits across two repos. No code changes. No tests added.

---

## 7. Effort

- 2 file edits, ~6 lines of diff total
- 2 commits (one per repo)
- R5 supervise (very light pass — documentation-only changes; reviewers verify markdown correctness, link target accuracy, supersedence wording)
- 0.25 session total
