# opensrm-m43k Implementation Plan — OPENSRM Spec Migration Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining acceptance criteria on opensrm-m43k after a prior chore-branch import already moved the OPENSRM-*.md files out of ecosystem root — add an inline supersedence marker to the v1 RBAC file and convert two SPEC INDEX entries to GitHub links so readers can navigate from the index.

**Architecture:** Two documentation edits across two repos. No code changes. No file moves. No branch reconciliation. The v1 RBAC marker keeps the file in place but signals supersedence; the SPEC INDEX links target the `main` branch on `rsionnach/opensrm` (future-facing, valid post-chore-merge).

**Tech Stack:** Markdown only. No build, no tests beyond grep verifications.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-30-m43k-opensrm-spec-migration-design.md` (committed at `nthlayer@4f2580f`).

---

## File Structure

**Modified files:**
- `opensrm/OPENSRM-RBAC-EXTENSION.md` — insert supersedence notice between H1 title and existing metadata block.
- `nthlayer/docs/specs/NTHLAYER-SPEC-INDEX-v1.md` — lines 13 + 15: convert bare bold filenames to GitHub-linked markdown.

**No new files. No test files.**

**Task ordering rationale:** Edits are independent and trivial. Task 1 (opensrm) and Task 2 (nthlayer) touch different repos with zero coupling — they could be fan-out parallel. Task 3 wraps R5 + bead close.

---

## Task 1: Inline supersedence marker on v1 RBAC file (opensrm repo)

**Files:**
- Modify: `opensrm/OPENSRM-RBAC-EXTENSION.md` (insert after line 1)

- [ ] **Step 1.1: Confirm current state of the v1 RBAC file**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && head -8 OPENSRM-RBAC-EXTENSION.md
```

Expected output:
```
# OpenSRM RBAC Extension: Action Authorisation

**Extension to:** OpenSRM v1
**Version:** 1.0.0-draft
**Status:** Draft
**Authors:** Rob Sionnach
**Depends on:** OpenSRM v1 core specification

```

If the header is different (e.g. someone already added an archive marker), STOP and report — the file has drifted from the spec's snapshot.

- [ ] **Step 1.2: Confirm we're on the chore/specs-and-docs branch**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && git branch --show-current
```

Expected: `chore/specs-and-docs`

The bead is rescoped explicitly to land its commits on this existing branch (branch reconciliation is out of scope per spec § 4). If on a different branch, STOP and report.

- [ ] **Step 1.3: Insert the supersedence notice**

Edit `opensrm/OPENSRM-RBAC-EXTENSION.md`. Replace the first 3 lines:

```markdown
# OpenSRM RBAC Extension: Action Authorisation

**Extension to:** OpenSRM v1
```

with:

```markdown
# OpenSRM RBAC Extension: Action Authorisation

> **⚠️ Superseded.** This is the v1 RBAC extension, retained for historical reference.
> The active specification is [`OPENSRM-RBAC-EXTENSION-v2.md`](OPENSRM-RBAC-EXTENSION-v2.md)
> in this same directory. Implementations should target v2; v1 is preserved only for
> consumers transitioning off the original draft.

**Extension to:** OpenSRM v1
```

The blockquote uses a relative path (`OPENSRM-RBAC-EXTENSION-v2.md`) because both files live in the same directory (opensrm root). The relative link resolves on GitHub and in local previews.

- [ ] **Step 1.4: Verify the marker landed correctly**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && head -12 OPENSRM-RBAC-EXTENSION.md
```

Expected:
```
# OpenSRM RBAC Extension: Action Authorisation

> **⚠️ Superseded.** This is the v1 RBAC extension, retained for historical reference.
> The active specification is [`OPENSRM-RBAC-EXTENSION-v2.md`](OPENSRM-RBAC-EXTENSION-v2.md)
> in this same directory. Implementations should target v2; v1 is preserved only for
> consumers transitioning off the original draft.

**Extension to:** OpenSRM v1
**Version:** 1.0.0-draft
**Status:** Draft
**Authors:** Rob Sionnach
**Depends on:** OpenSRM v1 core specification
```

Also confirm the spec's first acceptance grep returns ≥ 1:
```
grep -c "OPENSRM-RBAC-EXTENSION-v2.md" OPENSRM-RBAC-EXTENSION.md
```

Expected: a number ≥ 2 (the marker mentions v2 twice — once as the inline-code filename, once as the link target).

- [ ] **Step 1.5: Commit**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && git add OPENSRM-RBAC-EXTENSION.md && git commit -m "$(cat <<'EOF'
docs(rbac): inline supersedence marker on v1 spec · opensrm-m43k

Adds a blockquote at the top of OPENSRM-RBAC-EXTENSION.md noting the
file is superseded by OPENSRM-RBAC-EXTENSION-v2.md in the same
directory. Readers landing on v1 via search / old link / directory
listing now have an immediate signal that v2 is the active version.
No file move; v1 stays where it is for consumers transitioning off
the original draft.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Commit lands on the existing `chore/specs-and-docs` branch (not on main — branch reconciliation is out of scope per spec § 4).

---

## Task 2: GitHub links on SPEC INDEX entries (nthlayer repo)

**Files:**
- Modify: `nthlayer/docs/specs/NTHLAYER-SPEC-INDEX-v1.md:13,15`

- [ ] **Step 2.1: Confirm current state of the SPEC INDEX lines**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && sed -n '11,17p' docs/specs/NTHLAYER-SPEC-INDEX-v1.md
```

Expected output:
```
### Specifications

1. **OPENSRM-CORE-v2.md** — The OpenSRM specification. Declarative format for service reliability. Composes OpenSLO, Backstage, CloudEvents, OpenAPI, AsyncAPI, OTel GenAI semconv. Original contribution: judgment SLOs, reliability contracts, dependencies-with-expected-guarantees. Not tied to NthLayer implementation.

2. **OPENSRM-RBAC-EXTENSION-v2.md** — Extension to OpenSRM for unified human/agent authorisation. Introduces Principals, Actions, Capability Tokens, Authorisation Policies, preconditions, ChangeFreeze. Implementation uses Rego (via Regorus), Biscuit tokens, optional SPIFFE.
```

If lines 13/15 are already linked (markdown `[...](...)` syntax), STOP and report — file has drifted from the spec's snapshot.

- [ ] **Step 2.2: Convert line 13 to a GitHub link**

Edit `nthlayer/docs/specs/NTHLAYER-SPEC-INDEX-v1.md`. Find the exact line:

```
1. **OPENSRM-CORE-v2.md** — The OpenSRM specification. Declarative format for service reliability. Composes OpenSLO, Backstage, CloudEvents, OpenAPI, AsyncAPI, OTel GenAI semconv. Original contribution: judgment SLOs, reliability contracts, dependencies-with-expected-guarantees. Not tied to NthLayer implementation.
```

Replace with:
```
1. **[OPENSRM-CORE-v2.md](https://github.com/rsionnach/opensrm/blob/main/OPENSRM-CORE-v2.md)** — The OpenSRM specification. Declarative format for service reliability. Composes OpenSLO, Backstage, CloudEvents, OpenAPI, AsyncAPI, OTel GenAI semconv. Original contribution: judgment SLOs, reliability contracts, dependencies-with-expected-guarantees. Not tied to NthLayer implementation.
```

The only change is the bold-bare `**OPENSRM-CORE-v2.md**` → `**[OPENSRM-CORE-v2.md](https://github.com/rsionnach/opensrm/blob/main/OPENSRM-CORE-v2.md)**`. Everything else on the line stays exactly the same.

- [ ] **Step 2.3: Convert line 15 to a GitHub link**

Find:
```
2. **OPENSRM-RBAC-EXTENSION-v2.md** — Extension to OpenSRM for unified human/agent authorisation. Introduces Principals, Actions, Capability Tokens, Authorisation Policies, preconditions, ChangeFreeze. Implementation uses Rego (via Regorus), Biscuit tokens, optional SPIFFE.
```

Replace with:
```
2. **[OPENSRM-RBAC-EXTENSION-v2.md](https://github.com/rsionnach/opensrm/blob/main/OPENSRM-RBAC-EXTENSION-v2.md)** — Extension to OpenSRM for unified human/agent authorisation. Introduces Principals, Actions, Capability Tokens, Authorisation Policies, preconditions, ChangeFreeze. Implementation uses Rego (via Regorus), Biscuit tokens, optional SPIFFE.
```

- [ ] **Step 2.4: Verify both links present**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && grep -c "github.com/rsionnach/opensrm/blob/main/OPENSRM" docs/specs/NTHLAYER-SPEC-INDEX-v1.md
```

Expected: `2`

Also visually confirm:
```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && sed -n '13p;15p' docs/specs/NTHLAYER-SPEC-INDEX-v1.md
```

Expected: both lines start with `1. **[OPENSRM-CORE-v2.md](https://...` and `2. **[OPENSRM-RBAC-EXTENSION-v2.md](https://...` respectively.

- [ ] **Step 2.5: Commit**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && git add docs/specs/NTHLAYER-SPEC-INDEX-v1.md && git commit -m "$(cat <<'EOF'
docs(spec-index): link OPENSRM-* v2 specs to GitHub · opensrm-m43k

Converts the two SPEC INDEX entries that introduce the v2 OpenSRM
specs from bold-bare filenames to GitHub-linked names. The SPEC
INDEX is the discoverability spot where a reader expects to click
through to the spec; bare filenames break that affordance now that
the files live in the opensrm repo, not ecosystem root.

URL targets main on rsionnach/opensrm — valid after chore/specs-and-
docs merges (branch reconciliation is its own concern, out of scope
for this bead).

Other nthlayer files mention OPENSRM-* in prose / section-anchor
form (e.g. "OPENSRM-CORE §5"); those read fine as text and are not
updated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: R5 supervise + bead close

**Files:** None modified. Validates the bead is shippable.

- [ ] **Step 3.1: Confirm both commits landed**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && git log --oneline -1
echo "---"
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer && git log --oneline -3
```

Expected: opensrm HEAD = Task 1 commit (on chore/specs-and-docs); nthlayer HEAD = Task 2 commit, HEAD~1 = plan commit (next step), HEAD~2 = spec commit `4f2580f`.

- [ ] **Step 3.2: Invoke /r5-supervise m43k**

```
/r5-supervise m43k
```

R5 expectations for this bead (documentation-only):
- **Correctness:** markdown syntax valid (blockquote + link); GitHub URL targets exist (paths correct); supersedence wording is accurate (v1 is in fact superseded by v2).
- **Clarity:** supersedence notice wording is helpful (not just "deprecated" — explains WHY v1 is retained); link text matches the URL's file basename (no surprise navigation).
- **Edge cases:** What happens if `chore/specs-and-docs` never merges? The GitHub link 404s until then — acceptable per spec § 3.3. What if v2 ever gets a v3? The marker's link points at v2 specifically (not a "latest" alias); future supersedence would need its own bead.
- **Excellence:** small, focused, no scope creep. The bead is a cleanup; cleanups should be boring.

Expect few or zero findings.

- [ ] **Step 3.3: (If R5 doesn't auto-close) manually close the bead**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && bd close m43k --reason "OPENSRM spec migration cleanup. Prior chore-branch import (commits 30c4d99 + 575fbd8 on chore/specs-and-docs) already moved the 3 OPENSRM-*.md files out of ecosystem root into opensrm repo root. This bead added the remaining two pieces: (1) inline supersedence marker on the v1 RBAC file so readers landing there know v2 is active, (2) GitHub links on the 2 SPEC INDEX entries that introduce v2 (the discoverability spot). Files stayed at opensrm root (no spec/v2/ move); 5 other nthlayer prose / section-anchor refs left unchanged (not broken, not links). Branch reconciliation of chore/specs-and-docs deferred per spec § 4. R5 reviewed."
```

Verify:
```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && bd show m43k | head -5
```

Expected: `[● P2 · CLOSED]`.

---

## Self-Review Notes

**Spec coverage map:**
- § 3.1 (no file moves) → Tasks 1 + 2 modify only existing files in place; no creates, no moves
- § 3.2 (supersedence marker on v1 RBAC) → Task 1 (Steps 1.3 + 1.4 verify)
- § 3.3 (SPEC INDEX lines 13 + 15 to GitHub links) → Task 2 (Steps 2.2 + 2.3 + 2.4 verify)
- § 3.4 (skip the 5 prose-reference files) → no task; intentionally not addressed
- § 4 (branch reconciliation out of scope) → Task 1.2 confirms we land commits on existing branch
- § 5 (acceptance is grep + visual) → Steps 1.4, 2.4 are the grep verifications

**Placeholder scan:** No "TBD" / "TODO" / "fill in" markers. Every exact-string replacement shows both before and after. Every grep has a concrete expected value.

**Type / value consistency:** GitHub URLs use the same `https://github.com/rsionnach/opensrm/blob/main/<basename>` shape on both lines. The relative link in the supersedence marker uses the same `OPENSRM-RBAC-EXTENSION-v2.md` basename used by the SPEC INDEX link. Bead ID `opensrm-m43k` consistent across commit messages and the bd-close reason.
