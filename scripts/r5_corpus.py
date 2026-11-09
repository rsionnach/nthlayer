#!/usr/bin/env python3
"""The replay corpus of the sequential R5 gate, built from its archived records.

R5 Gate v2 Phase A.2 (opensrm-6kqs.2; nthlayer/docs/superpowers/specs/
2026-11-03-r5-gate-v2-nthlayer-spec.md section 3 item 2, section 6). cúramóir's
batched gate is replayed against this corpus to show it catches what the
sequential gate caught.

One entry per archived gate record and repo (rulings on opensrm-6kqs.2,
2026-11-09): ``<out>/opensrm-<stem>/``, or ``opensrm-<stem>--<repo>/`` when the
record gated several repos. Each holds the light files:

- ``meta.json``: bead, record, repo, base and head (full SHAs) and their trees
  (``record_head`` when an escape moved the head, ``unavailable`` when the
  local repo lacks one), the roster, ``sequential_steps`` for the record and
  ``bead_sequential_steps`` for its bead (r5_baseline), ``escape``,
  ``fidelity``, ``brief_source``, per-lens severity counts per review,
  r5_baseline's per-lens totals (``baseline``), and the synthetic bundle
  commits that carry base's and head's trees.
- ``brief.md``: what the reviewers were given, by source (BRIEF_SOURCES).
- ``diff.patch``: ``git diff base head``.
- ``recorded.json``: the gate's rounds per lens, with findings in the section 6
  schema where they are known, and the escaped finding for the two escapes.

The heavy part, one git bundle per repo, is written to ``--bundles``: each
entry's base and head trees as two synthetic commits (tree SHAs exact, commit
SHAs synthetic and deterministic), published as release assets under
BUNDLE_TAG, never committed. meta.json carries the asset's name, URL
and sha256.

Fidelity, per entry (FIDELITIES), never an exclusion:

- ``recorded``: the reviewer's own findings, extracted from its report (the
  private archive below) and accepted only if every blocking iteration's
  extraction passes check_extraction and its CRITICAL and IMPORTANT counts
  equal the archive's.
- ``derived``: path and range from the lens's fix-commit hunks, claim from
  its severity bullet, one-to-one only.
- ``clean``: no CRITICAL or IMPORTANT finding in any blocking lens.
- ``counts_only``: counts, lens order, iterations and steps; nothing finer.
  An entry split from a multi-repo record is counts_only (or clean): a finding
  cannot be given to one of its repos without guessing.

Inputs: the archives (``--archive-dir``, the workspace's ``.claude/``), the
member repos (``--workspace``), and the private archive (``--private-dir``,
``.claude/r5-handbacks/``): reviewer reports, their extractions and briefs,
taken from session transcripts. Only findings and briefs leave it; the
conversation around them never does. Without it every entry is derived, clean
or counts_only.

Standard library only (and git), like r5_baseline.py, which it imports.

Usage:
    python3 scripts/r5_corpus.py --out DIR [--bundles DIR] [--archive-dir DIR]
        [--workspace DIR] [--private-dir DIR] [--no-bd]

Exit codes: 0 corpus written · 2 any one of these: a usage error, a record
r5_baseline refuses (RecordError), or an input it cannot turn into an entry
without guessing (CorpusError): a record with no diff_range, a reviewer report
whose sha256 differs from its index, a KNOWN_ESCAPES key matching no corpus
entry or whose lines are not in the tree the entry carries, or a git command
that fails.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r5_baseline  # noqa: E402  (a sibling script, not a package)

SCHEMA_VERSION = 1
FIDELITIES = ("recorded", "derived", "clean", "counts_only")
BRIEF_SOURCES = ("reviewer_brief", "bead_description", "repo_plan", "none")
BLOCKING = r5_baseline.LENS_ORDER[:4]  # the blocking roster; excellence is advisory
BUNDLE_TAG = "r5-replay-corpus-v1"
BD_TIMEOUT_S = 60
BUNDLE_URL = "https://github.com/rsionnach/nthlayer/releases/download/{tag}/{name}"

# Synthetic commits are fixed in identity and time, so the same trees give the
# same commit SHAs on every run.
SYNTHETIC_ENV = {
    "GIT_AUTHOR_NAME": "r5-corpus", "GIT_AUTHOR_EMAIL": "r5-corpus@invalid",
    "GIT_COMMITTER_NAME": "r5-corpus", "GIT_COMMITTER_EMAIL": "r5-corpus@invalid",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
}

# The two beads whose gates missed a finding found later (spec section 6). The
# missed finding is known data, keyed (bead, repo), its text taken from
# docs/r5-gate.md and its location from the gated tree named here. A key that
# matches no entry is refused (exit 2), since a mistyped one would drop an
# escape silently.
KNOWN_ESCAPES = {
    ("opensrm-oh27", "nthlayer-workers"): {
        "lens": "provenance", "severity": "CRITICAL",
        "path": "src/nthlayer_workers/learn/retrospective.py", "start_line": 321, "end_line": 326,
        "at_commit": "6605897",
        "claim": "The predicate tests spec.slos as a list, but v1 writes a mapping and v2 has no"
                 " such key, so the branch never fires for a real manifest; every fixture uses"
                 " the same unreal shape.",
    },
    ("opensrm-ih0v", "nthlayer-common"): {
        "lens": "provenance", "severity": "CRITICAL",
        "path": "tests/test_manifest_v2_archetypes.py", "start_line": 50, "end_line": 53,
        "at_commit": "28d7add",
        "claim": "The module-level skipif skips the whole module when the layout-relative spec"
                 " path misses, so under one worktree layout the suite stays green while it"
                 " tests nothing.",
    },
}

DEFAULT_WORKSPACE = Path(__file__).resolve().parents[2]
SEVERITY_WORDS = ("CRITICAL", "IMPORTANT", "MINOR")


class CorpusError(ValueError):
    """An input this script cannot turn into a corpus entry without guessing."""


def git(repo: Path, *args: str, env: dict | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        env={**os.environ, **(env or {})},
    )
    if check and result.returncode != 0:
        raise CorpusError(f"git {' '.join(args)} in {repo}: {result.stderr.strip()}")
    return result.stdout if result.returncode == 0 else ""


def resolve(repo: Path, rev: str) -> str | None:
    """A full commit SHA, or None if the repo does not hold it (a squash-merged
    branch's commits can be garbage-collected)."""
    out = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False)
    return out.strip() or None


# --- the section 6 finding --------------------------------------------------

_LINE_REFS = re.compile(r"(?::~?\d+(?:\s*[-–]\s*\d+)?|\blines?\s+~?\d+(?:\s*[-–]\s*\d+)?|\bL\d+)", re.I)
_SHA = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")


def normalise_claim(claim: str) -> str:
    """Section 6: lower-cased, whitespace-collapsed, line numbers and SHAs removed."""
    text = _SHA.sub("", _LINE_REFS.sub("", claim.lower()))
    return " ".join(text.split())


def fingerprint(lens: str, path: str | None, claim: str) -> str:
    raw = f"{lens}|{path or ''}|{normalise_claim(claim)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def schema_lens(lens: str) -> str:
    return lens.replace("-", "_")


def finding(lens: str, severity: str, path: str | None, start: int | None, end: int | None,
            claim: str, **provenance: object) -> dict:
    """One finding in the section 6 schema, plus where it came from. Every
    archived finding is ``asserted``: no evidence was recorded with it."""
    return {
        "lens": schema_lens(lens), "severity": severity, "path": path,
        "start_line": start, "end_line": end if end is not None else start,
        "claim": claim, "evidence": None, "fix": None,
        "fingerprint": fingerprint(schema_lens(lens), path, claim),
        "verification_level": "asserted", "resolves": None, "regression": False, "status": None,
        **provenance,
    }


# --- accepting a model extraction (ruling 3) ---------------------------------

_MARKUP = str.maketrans("", "", "*`\"'“”‘’")
_REPORT_REFS = re.compile(r"(?::~?|(?<=\d)/|\(~?|\bL|\blines?\s+~?)(\d+)(?:\s*[-–]\s*L?(\d+))?", re.I)


def _norm_text(text: str) -> str:
    return " ".join(text.translate(_MARKUP).lower().split())


def report_line_refs(report: str) -> set[int]:
    """Every number the report writes as a line reference."""
    refs: set[int] = set()
    for first, last in _REPORT_REFS.findall(report):
        refs.add(int(first))
        if last:
            refs.add(int(last))
    return refs


def check_extraction(report: str, findings: list) -> list[str]:
    """Why an extraction is not the report's own record, or [] if it is.

    The claim is a near-verbatim quote (at least 90% of it one contiguous span
    of the report, markup and quote marks aside); the path appears in the
    report; a line is one the report gives as a reference, and only with a
    path; the severity is the report's own word."""
    if not isinstance(findings, list):
        return ["not a list"]
    errors, refs, text = [], report_line_refs(report), _norm_text(report)
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"{i}: not an object")
            continue
        sev, claim, path = f.get("severity"), f.get("claim") or "", f.get("path")
        if sev not in SEVERITY_WORDS or not re.search(rf"\b{sev}\b", report, re.I):
            errors.append(f"{i}: severity {sev!r} is not the report's word")
        quote = _norm_text(claim)
        match = difflib.SequenceMatcher(None, text, quote, autojunk=False).find_longest_match(
            0, len(text), 0, len(quote))
        if not quote or match.size < 0.9 * len(quote):
            errors.append(f"{i}: claim is not a near-verbatim quote")
        if path is not None and (not isinstance(path, str) or path not in report):
            errors.append(f"{i}: path {path!r} is not in the report")
        for key in ("start_line", "end_line"):
            value = f.get(key)
            if value is not None and (path is None or value not in refs):
                errors.append(f"{i}: {key}={value!r} is not a line reference the report gives")
        if isinstance(f.get("start_line"), int) and isinstance(f.get("end_line"), int) \
                and f["end_line"] < f["start_line"]:
            errors.append(f"{i}: end_line before start_line")
    return errors


def blocking_counts(findings: list) -> tuple[int, int]:
    sev = Counter(f.get("severity") for f in findings)
    return sev["CRITICAL"], sev["IMPORTANT"]


# --- the private archive ----------------------------------------------------

class PrivateArchive:
    """The reviewer reports, extractions and briefs kept outside every repo."""

    def __init__(self, root: Path | None):
        self.root = root
        self.pairings: dict[tuple[str, str, str], dict] = {}
        self.briefs: dict[str, dict] = {}
        if root is None or not (root / "index.json").is_file():
            return
        try:
            index = json.loads((root / "index.json").read_text(encoding="utf-8"))
            for p in index.get("pairings", []):
                for key in ("record", "lens", "findings_received_ts", "sha256", "file"):
                    if not isinstance(p.get(key), str):
                        raise CorpusError(f"{root / 'index.json'}: a pairing has no string {key!r}")
                self.pairings[(p["record"], p["lens"], p["findings_received_ts"])] = p
            brief_index = root / "briefs" / "index.json"
            if brief_index.is_file():
                self.briefs = json.loads(brief_index.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            raise CorpusError(f"{root}: unreadable private archive index ({exc})") from exc

    def recorded(self, record: str, lens: str, ts: str, counts: Counter) -> tuple[list, dict] | None:
        """The accepted extraction for one review, with its provenance, or None."""
        pairing = self.pairings.get((record, lens, ts))
        if pairing is None or self.root is None:
            return None
        short = pairing["sha256"][:16]
        report_path = self.root / pairing["file"]
        extraction = self.root / "extractions" / f"{short}.json"
        if not report_path.is_file() or not extraction.is_file():
            return None
        raw = report_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pairing["sha256"]:
            raise CorpusError(f"{report_path}: content does not match its index sha256")
        try:
            report = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CorpusError(f"{report_path}: not UTF-8 ({exc})") from exc
        try:
            found = json.loads(extraction.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None  # an unusable extraction: the review is not recorded
        if check_extraction(report, found):
            return None
        if blocking_counts(found) != (counts["critical"], counts["important"]):
            return None
        return found, {"derived_from": "reviewer_transcript", "extracted_by": "model",
                       "handback_sha256": pairing["sha256"]}

    def brief(self, stem: str) -> str | None:
        if self.root is None or stem not in self.briefs:
            return None
        path = self.root / "briefs" / f"{stem}.md"
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else None
        except UnicodeDecodeError as exc:
            raise CorpusError(f"{path}: not UTF-8 ({exc})") from exc


# --- the archived record ----------------------------------------------------

def blocking_lenses(record: dict) -> set[str]:
    """The lenses that blocked in this record's roster: the four, and in a v1
    record excellence too when it ran as a pass (the roster before 2026-08-28)."""
    lenses = set(BLOCKING)
    if record.get("version", 1) == 1 and "excellence" in (record.get("passes") or []):
        lenses.add("excellence")
    return lenses


def lens_blocks(lens: str, blocking: set[str]) -> bool:
    """A roster lens, or a one-off pass that names one ("clarity+edge-cases",
    "delta-clarity", "scoped(correctness+edge)")."""
    return lens in blocking or any(name in lens or name.split("-")[0] in lens for name in blocking)


def reviews(record: dict) -> list[dict]:
    """Every review the record logs (findings_received), in dispatch order, with
    the commit that followed it before the next review or the pass's end: that
    lens's fix for that iteration, if one was made."""
    out: list[dict] = []
    iteration: Counter = Counter()
    pending: dict | None = None
    blocking = blocking_lenses(record)
    for event in record.get("audit_trail") or []:
        kind, lens = event.get("event"), event.get("pass")
        if not isinstance(lens, str):  # placed as r5_baseline places it, or not at all
            lens = r5_baseline.PASSLESS_EVENTS.get((record.get("target_bead"), kind, event.get("ts")))
        if kind == "findings_received" and isinstance(lens, str):
            iteration[lens] += 1
            pending = {"lens": lens, "iteration": iteration[lens], "ts": event.get("ts"),
                       # r5_baseline's own reading of a counts value, so the two
                       # scripts can never disagree on one.
                       "counts": r5_baseline._counts(event.get("counts")), "fix_commit": None,
                       "fix_repo": None, "blocking_lens": lens_blocks(lens, blocking)}
            out.append(pending)
        elif kind == "commit_made" and pending is not None:
            if isinstance(event.get("sha"), str):
                pending["fix_commit"], pending["fix_repo"] = event["sha"], event.get("repo")
            pending = None
        elif kind in ("pass_started", "pass_completed", "advisory_pass_completed"):
            pending = None  # a commit after the pass ends is not this review's fix
    return out


def raised_blocking_finding(review: dict) -> bool:
    """A review in a blocking lens that raised a CRITICAL or IMPORTANT."""
    return review["blocking_lens"] and review["counts"]["critical"] + review["counts"]["important"] > 0


def severities_complete(row: dict) -> bool:
    """Whether every finding the baseline counts has a logged severity. A v1
    record that logged only totals (``unattributed``), or a lens with findings
    and no findings_received, may hide a blocking finding, so it is never
    clean or recorded."""
    return all(lens["unattributed"] == 0 and (lens["findings_by_review"] or not lens["findings_first_review"])
               for lens in row["lenses"].values())


_BULLET = re.compile(r"^\s*(?:[-*]\s*)?(CRITICAL|IMPORTANT)(?:\s+\d+)?\s*(?:[:—-]|\()\s*(.*)$")


def severity_bullets(message: str) -> list[tuple[str, str]]:
    """Each CRITICAL or IMPORTANT bullet of a commit message with its wrapped
    continuation lines, up to a blank line or the next bullet."""
    out: list[tuple[str, list[str]]] = []
    for line in message.splitlines():
        m = _BULLET.match(line)
        if m:
            out.append((m.group(1), [m.group(2).strip()]))
        elif not line.strip() or re.match(r"^\s*[-*]\s", line):
            out.append(("", []))  # a blank line or another bullet ends it
        elif out:
            out[-1][1].append(line.strip())
    return [(sev, " ".join(parts).strip()) for sev, parts in out if sev]


def derive_from_commit(repo: Path, review: dict) -> list[dict] | None:
    """The review's blocking findings from its fix commit, one-to-one, or None.

    One severity bullet per counted CRITICAL and IMPORTANT, each given a path:
    the changed file its text names, else the only file the commit changed.
    Its range is that file's changed lines on the new side."""
    sha = resolve(repo, review["fix_commit"]) if review["fix_commit"] else None
    if sha is None:
        return None
    bullets = severity_bullets(git(repo, "log", "-1", "--format=%B", sha))
    want = (review["counts"]["critical"], review["counts"]["important"])
    got = Counter(sev for sev, _ in bullets)
    if (got["CRITICAL"], got["IMPORTANT"]) != want:
        return None
    changed = [p for p in git(repo, "show", "--format=", "--name-only", sha).split("\n") if p]
    out = []
    for sev, text in bullets:
        named = [p for p in changed if p in text or Path(p).name in text]
        path = named[0] if len(named) == 1 else (changed[0] if len(changed) == 1 else None)
        if path is None or not text:
            return None
        span = changed_span(repo, sha, path)
        out.append(finding(review["lens"], sev, path, *(span or (None, None)), text,
                           derived_from="fix_commit", fix_commit=sha, bullet=text))
    return out


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_span(repo: Path, sha: str, path: str) -> tuple[int, int] | None:
    """First and last new-side line the commit changed in ``path``."""
    lines = []
    for line in git(repo, "show", "--format=", "-U0", sha, "--", path).splitlines():
        if m := _HUNK.match(line):
            start, length = int(m.group(1)), int(m.group(2) or 1)
            if length:
                lines += [start, start + length - 1]
    return (min(lines), max(lines)) if lines else None


# --- entries ----------------------------------------------------------------

def entry_name(stem: str, repo: str, repos: int) -> str:
    return f"opensrm-{stem}" + (f"--{repo}" if repos > 1 else "")


def build_entry(entry: str, stem: str, record_file: str, record: dict, row: dict, bead_steps: int,
                repo_name: str, rng: dict, multi: bool, workspace: Path,
                private: PrivateArchive, use_bd: bool) -> dict:
    """The light files of one entry, as data, plus the trees its bundle needs."""
    repo = workspace / repo_name
    base, head = (resolve(repo, rng.get("base") or ""), resolve(repo, rng.get("head") or "")) \
        if repo.is_dir() else (None, None)
    bead = record.get("target_bead")
    escape = KNOWN_ESCAPES.get((bead, repo_name))
    record_head = head
    if escape and repo.is_dir():
        # The escaped code can be in the gate's last tree rather than the
        # recorded head (oh27's predicate came in during its fix loop), so the
        # entry carries that tree, or replay could not reach it.
        head = resolve(repo, escape["at_commit"])
        check_escape(repo, head, escape)
    revs = reviews(record)
    if not severities_complete(row):
        fidelity, rounds = "counts_only", None
    elif not any(raised_blocking_finding(r) for r in revs):
        fidelity, rounds = "clean", None
    elif multi:
        fidelity, rounds = "counts_only", None  # a finding cannot be given to one repo
    else:
        fidelity, rounds = classify(record_file, revs, private, repo, head)
    rounds = rounds or [_round(r, None) for r in revs]
    brief, brief_source = choose_brief(stem, bead, repo, private, use_bd)
    brief = mask_workspace(brief, workspace) or ""
    meta = {
        "schema_version": SCHEMA_VERSION, "entry": entry, "bead": bead, "record": record_file,
        "repo": repo_name, "base": base, "head": head,
        "record_head": record_head if record_head != head else None,
        "base_tree": git(repo, "rev-parse", f"{base}^{{tree}}").strip() if base else None,
        "tree_sha": git(repo, "rev-parse", f"{head}^{{tree}}").strip() if head else None,
        "unavailable": None if base and head else "base or head is not in the local repo",
        "roster": {"record_version": record.get("version", 1), "passes": record.get("passes")},
        "lens_order": row["lens_order"], "sequential_steps": row["sequential_steps"],
        "bead_sequential_steps": bead_steps, "escape": escape is not None,
        "fidelity": fidelity, "brief_source": brief_source,
        "counts": {lens: [dict(r["counts"]) for r in revs if r["lens"] == lens]
                   for lens in dict.fromkeys(r["lens"] for r in revs)},
        # The baseline's per-lens view, which has the totals a v1 record kept
        # when it logged no severities.
        "baseline": {lens: {k: v[k] for k in ("reviews", "fix_rounds", "findings_first_review",
                                              "unattributed", "steps")}
                     for lens, v in row["lenses"].items()},
        "bundle": None,
    }
    recorded = {
        "schema_version": SCHEMA_VERSION, "entry": entry, "fidelity": fidelity,
        "lens_order": row["lens_order"],
        "iterations": {lens: len(v) for lens, v in meta["counts"].items()},
        "rounds": rounds,
        "escaped": [finding(escape["lens"], escape["severity"], escape["path"], escape["start_line"],
                            escape["end_line"], escape["claim"], derived_from="known_escape",
                            at_commit=escape["at_commit"])] if escape else [],
    }
    diff = git(repo, "diff", base, head) if base and head else ""
    return {"meta": meta, "recorded": recorded, "brief": brief, "diff": diff}


def _round(review: dict, findings: list | None) -> dict:
    return {"lens": schema_lens(review["lens"]), "iteration": review["iteration"],
            "counts": dict(review["counts"]), "findings": findings}


def check_escape(repo: Path, head: str | None, escape: dict) -> None:
    """Refuse an escape whose lines are not in the tree the entry carries."""
    text = git(repo, "show", f"{head}:{escape['path']}", check=False) if head else ""
    if not text or len(text.splitlines()) < escape["end_line"]:
        raise CorpusError(f"KNOWN_ESCAPES {escape['path']}:{escape['end_line']} is not in"
                          f" {escape['at_commit']} of {repo.name}")


def tree_paths(repo: Path, head: str) -> set[str]:
    return {p for p in git(repo, "ls-tree", "-r", "--name-only", head).split("\n") if p}


def repo_path(path: str | None, files: set[str], repo_name: str) -> tuple[str | None, bool]:
    """A reported path as a path in the head tree, and whether it is one.

    Reviewers write paths as they saw them: repo-relative, prefixed with the
    repo or a worktree directory, absolute, or a bare file name. The path is
    the unique tree path the reported one ends with; failing that, a local
    absolute path is cut to what follows the repo's directory, so the
    finding's ``path`` is never a local one (``reported_path`` is masked by
    mask_workspace). Nothing is chosen between two candidates."""
    if path is None or path in files:
        return path, path is not None
    clean = path.strip()
    while clean.startswith(("./", "/")):
        clean = clean[2:] if clean.startswith("./") else clean[1:]
    matches = [f for f in files if clean == f or clean.endswith("/" + f) or f.endswith("/" + clean)]
    if len(matches) == 1:
        return matches[0], True
    if path.startswith("/"):
        parts = Path(path).parts
        tail = [i for i, part in enumerate(parts) if part.startswith(repo_name)]
        path = "/".join(parts[tail[-1] + 1:]) if tail else Path(path).name
    return path, False


# The end of a path component: a sibling sharing a name prefix ("nthlayer"
# and "nthlayer-common") is a different path.
_PATH_END = r"(?=/|$|[^\w.-])"


def mask_workspace(text: str | None, workspace: Path) -> str | None:
    """``text`` with the local workspace's absolute path written ``<workspace>``.
    Reviewer reports and briefs name files by where they sat on one machine;
    that path says nothing about the code and is not published."""
    if text is None:
        return None
    # Absolute forms only: a relative workspace ("..") would match every "..".
    for root in sorted({str(workspace.resolve()), str(workspace.absolute())}, key=len, reverse=True):
        text = re.sub(re.escape(root) + _PATH_END, "<workspace>", text)
    return re.sub(re.escape(str(Path.home())) + _PATH_END, "~", text)


def classify(record_file: str, revs: list[dict], private: PrivateArchive, repo: Path,
             head: str | None) -> tuple[str, list | None]:
    """A single-repo entry with blocking findings: ("recorded", rounds) when
    every blocking review's extraction is accepted, else ("derived", rounds)
    when every one derives from its fix commit, else ("counts_only", None)."""
    recorded = []
    for r in revs:
        if not raised_blocking_finding(r):
            recorded.append(_round(r, None))
            continue
        got = private.recorded(record_file, r["lens"], r["ts"], r["counts"])
        if got is None:  # no accepted extraction: the entry cannot be recorded
            recorded = None
            break
        found, prov = got
        fix = resolve(repo, r["fix_commit"]) if r["fix_commit"] and repo.is_dir() else None
        files = tree_paths(repo, head) if head else set()
        out = []
        for f in found:
            path, in_tree = repo_path(f.get("path"), files, repo.name)
            out.append(finding(r["lens"], f["severity"], path, f.get("start_line"), f.get("end_line"),
                               f["claim"], **prov, fix_commit=fix,
                               reported_path=mask_workspace(f.get("path"), repo.parent),
                               path_in_tree=in_tree))
        recorded.append(_round(r, out))
    if recorded is not None:
        return "recorded", recorded
    derived = []
    for r in revs:
        if not raised_blocking_finding(r):
            derived.append(_round(r, None))
            continue
        found = derive_from_commit(repo, r) if repo.is_dir() else None
        if found is None:
            return "counts_only", None
        derived.append(_round(r, found))
    return "derived", derived


def choose_brief(stem: str, bead: str | None, repo: Path, private: PrivateArchive,
                 use_bd: bool) -> tuple[str, str]:
    """What the reviewers were given, by BRIEF_SOURCES order."""
    text = private.brief(stem)
    if text:
        return text, "reviewer_brief"
    if use_bd and bead:
        desc = bead_description(bead, repo.parent / "opensrm")
        if desc:
            return desc, "bead_description"
    if bead and repo.is_dir():
        plans = sorted(p for p in (repo / "docs" / "superpowers" / "plans").glob("*.md")
                       if bead in p.read_text(encoding="utf-8", errors="replace"))
        if plans:
            return plans[0].read_text(encoding="utf-8"), "repo_plan"
    return "", "none"


def bead_description(bead: str, beads_repo: Path) -> str | None:
    if shutil.which("bd") is None or not beads_repo.is_dir():
        return None
    try:
        result = subprocess.run(["bd", "show", bead, "--json"], cwd=beads_repo,
                                capture_output=True, text=True, timeout=BD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None  # a hung bd (a held Dolt lock) gives no brief, not a stalled build
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    item = data[0] if isinstance(data, list) and data else data
    if not isinstance(item, dict):
        return None
    parts = [f"# {item.get('id', bead)}: {item.get('title', '')}", item.get("description") or ""]
    if item.get("acceptance_criteria"):
        parts += ["## Acceptance", item["acceptance_criteria"]]
    return "\n\n".join(p for p in parts if p).strip() + "\n"


# --- bundles ----------------------------------------------------------------

def write_bundles(entries: list[dict], workspace: Path, out: Path) -> None:
    """One bundle per repo: each entry's base and head trees as a synthetic
    two-commit history under refs/r5/<entry>/{base,head}. Fills each meta's
    ``bundle``."""
    out.mkdir(parents=True, exist_ok=True)
    by_repo: dict[str, list[dict]] = {}
    for e in entries:
        if e["meta"]["base_tree"] and e["meta"]["tree_sha"]:
            by_repo.setdefault(e["meta"]["repo"], []).append(e)
    for repo_name, group in sorted(by_repo.items()):
        source = (workspace / repo_name).resolve()
        objects = git(source, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            git(scratch, "init", "-q", "--bare")
            (scratch / "objects" / "info").mkdir(parents=True, exist_ok=True)
            (scratch / "objects" / "info" / "alternates").write_text(f"{objects}/objects\n")
            for e in group:
                meta = e["meta"]
                base_commit = git(scratch, "commit-tree", meta["base_tree"], "-m",
                                  f"{meta['entry']} base {meta['base']}", env=SYNTHETIC_ENV).strip()
                head_commit = git(scratch, "commit-tree", meta["tree_sha"], "-p", base_commit, "-m",
                                  f"{meta['entry']} head {meta['head']}", env=SYNTHETIC_ENV).strip()
                git(scratch, "update-ref", f"refs/r5/{meta['entry']}/base", base_commit)
                git(scratch, "update-ref", f"refs/r5/{meta['entry']}/head", head_commit)
                meta["bundle"] = {"asset": f"{repo_name}.bundle", "base_commit": base_commit,
                                  "head_commit": head_commit}
            target = out / f"{repo_name}.bundle"
            # One pack thread: a threaded delta search orders objects
            # differently run to run, and the published sha256 must hold.
            git(scratch, "-c", "pack.threads=1", "bundle", "create", "-q",
                str(target.resolve()), "--all")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        for e in group:
            e["meta"]["bundle"].update(
                sha256=digest, url=BUNDLE_URL.format(tag=BUNDLE_TAG, name=f"{repo_name}.bundle"))


# --- the corpus -------------------------------------------------------------

def build(archive_dir: Path, workspace: Path, private: PrivateArchive, use_bd: bool) -> list[dict]:
    records = r5_baseline.load_records(archive_dir)
    rows = {name: dict(r5_baseline.analyse_record(data), file=name) for name, data in records}
    beads = r5_baseline.bead_steps(list(rows.values()))
    counted = {r["file"] for r in r5_baseline.baseline_rows(list(rows.values()))}
    entries = []
    for name, record in records:
        if name not in counted:
            continue
        if not isinstance(record.get("target_bead"), str):
            raise CorpusError(f"{name}: has no target_bead")
        stem = name.removeprefix("r5-state-").removesuffix("-completed.json")
        ranges = record.get("diff_range")
        if not isinstance(ranges, dict) or not ranges:
            raise CorpusError(f"{name}: no diff_range")
        bead_total = beads[record.get("target_bead")]["sequential_steps"]
        for repo_name, rng in ranges.items():
            entries.append(build_entry(entry_name(stem, repo_name, len(ranges)), stem, name, record,
                                       rows[name], bead_total, repo_name, rng, len(ranges) > 1,
                                       workspace, private, use_bd))
    found = {(e["meta"]["bead"], e["meta"]["repo"]) for e in entries}
    missing = sorted(set(KNOWN_ESCAPES) - found)
    if missing:
        raise CorpusError(f"KNOWN_ESCAPES entries {missing} match no corpus entry")
    return entries


def is_corpus_entry(path: Path) -> bool:
    """A directory this script wrote: its meta.json names it as an entry."""
    try:
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(meta, dict) and "schema_version" in meta and meta.get("entry") == path.name


def write_entries(entries: list[dict], out: Path) -> None:
    """Write every entry, replacing the entries a previous run left. Refuses
    an --out holding an opensrm-* directory it did not write (the private
    archive and sibling worktrees share that prefix) rather than delete it."""
    out.mkdir(parents=True, exist_ok=True)
    olds = [p for p in out.glob("opensrm-*") if p.is_dir()]
    strangers = [p.name for p in olds if not is_corpus_entry(p)]
    if strangers:
        raise CorpusError(f"{out} holds opensrm-* directories that are not corpus entries:"
                          f" {strangers[:3]}; choose another --out")
    for old in olds:
        shutil.rmtree(old)
    for e in entries:
        target = out / e["meta"]["entry"]
        target.mkdir(parents=True, exist_ok=True)
        for file, text in (("meta.json", json.dumps(e["meta"], indent=1) + "\n"),
                           ("recorded.json", json.dumps(e["recorded"], indent=1) + "\n"),
                           ("brief.md", e["brief"]), ("diff.patch", e["diff"])):
            (target / file).write_text(text, encoding="utf-8")


def summary(entries: list[dict]) -> dict:
    by_fidelity = Counter(e["meta"]["fidelity"] for e in entries)
    return {
        "entries": len(entries),
        "beads": len({e["meta"]["bead"] for e in entries}),
        "fidelity": {f: by_fidelity[f] for f in FIDELITIES},
        "unavailable": sorted(e["meta"]["entry"] for e in entries if e["meta"]["unavailable"]),
        "reviewer_briefs": sorted(e["meta"]["entry"] for e in entries
                                  if e["meta"]["brief_source"] == "reviewer_brief"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bundles", type=Path)
    parser.add_argument("--archive-dir", type=Path, default=r5_baseline.DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--private-dir", type=Path)
    parser.add_argument("--no-bd", action="store_true", help="skip bead descriptions as a brief source")
    args = parser.parse_args(argv)
    private_dir = args.private_dir or args.archive_dir / "r5-handbacks"
    try:
        entries = build(args.archive_dir, args.workspace,
                        PrivateArchive(private_dir if private_dir.is_dir() else None), not args.no_bd)
        if args.bundles:
            write_bundles(entries, args.workspace, args.bundles)
        write_entries(entries, args.out)
    except (CorpusError, r5_baseline.RecordError) as exc:
        print(f"r5-corpus: {exc}", file=sys.stderr)
        return 2
    json.dump(summary(entries), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
