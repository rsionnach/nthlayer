"""Tests for scripts/r5_corpus.py (opensrm-6kqs.2).

Every input is synthetic and built here: a small git repo, archive records in
the v2 audit-trail shape r5_baseline reads (findings_received with counts,
commit_made with sha and repo, pass_started), and a private archive in the
shape the extraction step writes (index.json pairings keyed by record, lens and
findings_received ts; the report; its extraction). Expected values are read off
these inputs, never off the script's output.

Run: uv run --no-project --with pytest pytest -q test/test_r5_corpus.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
_spec = importlib.util.spec_from_file_location("r5_corpus", HERE.parent / "scripts" / "r5_corpus.py")
assert _spec and _spec.loader
r5_corpus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r5_corpus)

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t"}


def run(repo: Path, *args: str) -> str:
    import os
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={**os.environ, **ENV}).stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (repo / name).write_text(text)
    run(repo, "add", "-A")
    run(repo, "commit", "-q", "-m", message)
    return run(repo, "rev-parse", "HEAD")


@pytest.fixture
def workspace(tmp_path):
    """A workspace with one member repo, "demo": base, head, then a fix."""
    ws = tmp_path / "ws"
    repo = ws / "demo"
    repo.mkdir(parents=True)
    run(repo, "init", "-q")
    base = commit(repo, {"app.py": "a = 1\nb = 2\n", "other.py": "x = 0\n"}, "base")
    head = commit(repo, {"app.py": "a = 1\nb = 3\n"}, "feat: change b")
    fix = commit(repo, {"app.py": "a = 1\nb = 3\nc = 4\n"},
                 "r5(correctness): 1 finding\n\n- IMPORTANT: app.py drops c on the\n  write path\n")
    (ws / ".claude").mkdir()
    return {"ws": ws, "repo": repo, "base": base, "head": head, "fix": fix}


def record(bead: str, ranges: dict, reviews: list[tuple[str, dict, str | None]]) -> dict:
    """A v2 archive record: each review is (lens, counts, fix sha or None)."""
    trail, ts = [], 0

    def event(**kw):
        nonlocal ts
        ts += 1
        trail.append({"ts": f"2000-01-01T00:00:{ts:02d}Z", **kw})
        return trail[-1]["ts"]

    stamps, started = [], set()
    for lens, counts, fix in reviews:
        if lens not in started:
            started.add(lens)
            event(event="pass_started", **{"pass": lens})
        event(event="reviewer_dispatched", **{"pass": lens})
        stamps.append(event(event="findings_received", counts=counts, **{"pass": lens}))
        if fix:
            event(event="commit_made", sha=fix, repo=next(iter(ranges)))
    return {"version": 2, "target_bead": bead, "dry_run": False, "passes": sorted(started),
            "diff_range": ranges, "audit_trail": trail, "completed_passes": [], "_stamps": stamps}


def write_record(ws: Path, stem: str, rec: dict) -> list[str]:
    stamps = rec.pop("_stamps")
    (ws / ".claude" / f"r5-state-{stem}-completed.json").write_text(json.dumps(rec))
    return stamps


REPORT = """## Correctness review

### IMPORTANT
1. `app.py:2` drops c on the write path, so a saved record loses its third field.

### MINOR
2. `other.py` has an unused name.
"""

EXTRACTION = [
    {"severity": "IMPORTANT", "path": "app.py", "start_line": 2, "end_line": 2,
     "claim": "drops c on the write path, so a saved record loses its third field."},
    {"severity": "MINOR", "path": "other.py", "start_line": None, "end_line": None,
     "claim": "has an unused name."},
]


def private_archive(root: Path, record_file: str, lens: str, ts: str,
                    report: str = REPORT, extraction=None) -> Path:
    sha = hashlib.sha256(report.encode()).hexdigest()
    (root / "bead").mkdir(parents=True, exist_ok=True)
    (root / "extractions").mkdir(exist_ok=True)
    (root / "bead" / f"{sha[:16]}.md").write_text(report)
    (root / "extractions" / f"{sha[:16]}.json").write_text(json.dumps(EXTRACTION if extraction is None else extraction))
    (root / "index.json").write_text(json.dumps({"pairings": [{
        "record": record_file, "lens": lens, "findings_received_ts": ts, "sha256": sha,
        "file": f"bead/{sha[:16]}.md"}]}))
    return root


def build(ws: Path, private: Path | None = None) -> dict[str, dict]:
    entries = r5_corpus.build(ws / ".claude", ws, r5_corpus.Private(private), use_bd=False)
    return {e["meta"]["entry"]: e for e in entries}


@pytest.fixture(autouse=True)
def _no_known_escapes(monkeypatch):
    monkeypatch.setattr(r5_corpus, "KNOWN_ESCAPES", {})


# --- the section 6 finding --------------------------------------------------

def test_normalised_claim_drops_line_numbers_shas_case_and_spacing():
    assert r5_corpus.normalise_claim("At app.py:12-14 the  Guard\nFAILS since 3f2a9c1") == \
        "at app.py the guard fails since"
    assert r5_corpus.normalise_claim("Line 7 and L9 differ") == "and differ"


def test_a_fingerprint_survives_moved_lines_but_not_another_claim():
    a = r5_corpus.fingerprint("correctness", "app.py", "app.py:2 drops c")
    assert a == r5_corpus.fingerprint("correctness", "app.py", "app.py:40 DROPS  c")
    assert a != r5_corpus.fingerprint("correctness", "app.py", "app.py:2 drops d")
    assert a != r5_corpus.fingerprint("clarity", "app.py", "app.py:2 drops c")
    assert len(a) == 16 and int(a, 16) >= 0


def test_a_finding_carries_the_section_6_fields():
    f = r5_corpus.finding("edge-cases", "IMPORTANT", "a.py", 3, None, "a claim")
    assert set(f) >= {"lens", "severity", "path", "start_line", "end_line", "claim", "evidence",
                      "fix", "fingerprint", "verification_level", "resolves", "regression", "status"}
    assert (f["lens"], f["end_line"], f["verification_level"]) == ("edge_cases", 3, "asserted")


# --- accepting an extraction ------------------------------------------------

def test_a_faithful_extraction_is_accepted():
    assert r5_corpus.check_extraction(REPORT, EXTRACTION) == []


@pytest.mark.parametrize("bad, why", [
    ({"claim": "drops c, and the guard is wrong too, as other.py shows"}, "claim"),
    ({"path": "elsewhere.py"}, "path"),
    ({"start_line": 3, "end_line": 3}, "start_line"),
    ({"path": None}, "start_line"),  # a range needs a path
    ({"severity": "CRITICAL"}, "severity"),
    ({"start_line": 2, "end_line": 1}, "end_line"),
])
def test_an_extraction_that_is_not_the_report_s_own_is_refused(bad, why):
    errors = r5_corpus.check_extraction(REPORT, [dict(EXTRACTION[0], **bad)])
    assert errors, bad
    assert any(why in e for e in errors)


@pytest.mark.parametrize("ref, n", [
    ("scorecard.md:~22", 22), ("Line 35: too long", 35), ("in worker.py (~322-335)", 335),
    ("orchestrator.py:196/226", 226), ("lines 768-774", 774), ("x.py:L12", 12),
])
def test_the_line_reference_forms_reports_use(ref, n):
    assert n in r5_corpus.report_line_refs(ref)


# --- fidelity ---------------------------------------------------------------

def test_a_record_whose_extraction_passes_is_recorded(workspace, tmp_path):
    ws = workspace["ws"]
    rec = record("opensrm-aaa", {"demo": {"base": workspace["base"][:7], "head": workspace["head"][:7]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 1}, workspace["fix"]),
                  ("correctness", {"critical": 0, "important": 0, "minor": 0}, None)])
    stamps = write_record(ws, "aaa", rec)
    private = private_archive(tmp_path / "p", "r5-state-aaa-completed.json", "correctness", stamps[0])
    e = build(ws, private)["opensrm-aaa"]
    assert e["meta"]["fidelity"] == "recorded"
    first, second = e["recorded"]["rounds"]
    assert [f["severity"] for f in first["findings"]] == ["IMPORTANT", "MINOR"]
    assert first["findings"][0]["fix_commit"] == workspace["fix"]
    assert first["findings"][0]["derived_from"] == "reviewer_transcript"
    assert second["findings"] is None  # a clean re-review: nothing was extracted
    assert e["recorded"]["iterations"] == {"correctness": 2}
    assert e["meta"]["tree_sha"] == run(workspace["repo"], "rev-parse", workspace["head"] + "^{tree}")
    assert e["meta"]["base"] == workspace["base"]  # the archive's short SHA, resolved


def test_an_extraction_whose_counts_differ_from_the_archive_is_not_recorded(workspace, tmp_path):
    ws = workspace["ws"]
    # The archive counts 2 IMPORTANT; the report (and its extraction) has 1.
    rec = record("opensrm-bbb", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 2, "minor": 0}, None)])
    stamps = write_record(ws, "bbb", rec)
    private = private_archive(tmp_path / "p", "r5-state-bbb-completed.json", "correctness", stamps[0])
    assert build(ws, private)["opensrm-bbb"]["meta"]["fidelity"] == "counts_only"


def test_an_extraction_failing_its_checks_is_not_recorded(workspace, tmp_path):
    ws = workspace["ws"]
    rec = record("opensrm-ccc", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 0}, None)])
    stamps = write_record(ws, "ccc", rec)
    stitched = [dict(EXTRACTION[0], claim="drops c and other.py has an unused name")]
    private = private_archive(tmp_path / "p", "r5-state-ccc-completed.json", "correctness", stamps[0],
                              extraction=stitched)
    assert build(ws, private)["opensrm-ccc"]["meta"]["fidelity"] == "counts_only"


def test_a_report_altered_after_indexing_is_refused(workspace, tmp_path):
    ws = workspace["ws"]
    rec = record("opensrm-ddd", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 1}, None)])
    stamps = write_record(ws, "ddd", rec)
    private = private_archive(tmp_path / "p", "r5-state-ddd-completed.json", "correctness", stamps[0])
    report = next((private / "bead").glob("*.md"))
    report.write_text(REPORT + "\nedited\n")
    with pytest.raises(r5_corpus.CorpusError):
        build(ws, private)


def test_a_fix_commit_with_one_bullet_and_one_file_is_derived(workspace):
    ws = workspace["ws"]
    rec = record("opensrm-eee", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 0}, workspace["fix"])])
    write_record(ws, "eee", rec)
    e = build(ws)["opensrm-eee"]
    assert e["meta"]["fidelity"] == "derived"
    (f,) = e["recorded"]["rounds"][0]["findings"]
    # The fix added line 3 of app.py; the bullet wraps onto a second line.
    assert (f["path"], f["start_line"], f["end_line"]) == ("app.py", 3, 3)
    assert f["claim"] == "app.py drops c on the write path"
    assert (f["derived_from"], f["fix_commit"]) == ("fix_commit", workspace["fix"])


def test_a_bullet_naming_no_file_of_a_multi_file_fix_is_not_derived(workspace):
    # The fix touches app.py and other.py; the bullet names neither, so its
    # path would be a guess.
    ws, repo = workspace["ws"], workspace["repo"]
    fix = commit(repo, {"app.py": "a = 9\n", "other.py": "x = 9\n"},
                 "r5(correctness): 1 finding\n\n- IMPORTANT: the write path drops a field\n")
    rec = record("opensrm-eef", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 0}, fix)])
    write_record(ws, "eef", rec)
    assert build(ws)["opensrm-eef"]["meta"]["fidelity"] == "counts_only"


def test_bullets_that_do_not_match_the_counts_are_not_derived(workspace):
    ws = workspace["ws"]
    rec = record("opensrm-fff", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 1, "important": 1, "minor": 0}, workspace["fix"])])
    write_record(ws, "fff", rec)
    assert build(ws)["opensrm-fff"]["meta"]["fidelity"] == "counts_only"


def test_a_record_with_no_blocking_finding_is_clean(workspace):
    ws = workspace["ws"]
    rec = record("opensrm-ggg", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 0, "minor": 3}, None)])
    write_record(ws, "ggg", rec)
    assert build(ws)["opensrm-ggg"]["meta"]["fidelity"] == "clean"


def test_a_multi_repo_record_splits_into_counts_only_entries(workspace):
    ws = workspace["ws"]
    rng = {"base": workspace["base"], "head": workspace["head"]}
    rec = record("opensrm-hhh", {"demo": rng, "missing": rng},
                 [("correctness", {"critical": 0, "important": 1, "minor": 0}, workspace["fix"])])
    write_record(ws, "hhh", rec)
    entries = build(ws)
    assert set(entries) == {"opensrm-hhh--demo", "opensrm-hhh--missing"}
    # Derivable on its own (as opensrm-eee), but not attributable to one repo.
    assert {e["meta"]["fidelity"] for e in entries.values()} == {"counts_only"}
    assert entries["opensrm-hhh--missing"]["meta"]["unavailable"]


# --- escapes, briefs, bundles ----------------------------------------------

def test_a_known_escape_is_flagged_with_its_missed_finding(workspace, monkeypatch):
    ws = workspace["ws"]
    rec = record("opensrm-iii", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)])
    write_record(ws, "iii", rec)
    monkeypatch.setattr(r5_corpus, "KNOWN_ESCAPES", {("opensrm-iii", "demo"): {
        "lens": "provenance", "severity": "CRITICAL", "path": "app.py", "start_line": 1,
        "end_line": 2, "at_commit": workspace["head"][:7], "claim": "the test never runs"}})
    e = build(ws)["opensrm-iii"]
    assert e["meta"]["escape"] is True
    (missed,) = e["recorded"]["escaped"]
    assert (missed["lens"], missed["path"], missed["derived_from"]) == ("provenance", "app.py", "known_escape")


def test_a_known_escape_matching_no_entry_is_refused(workspace, monkeypatch):
    ws = workspace["ws"]
    write_record(ws, "jjj", record("opensrm-jjj", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    monkeypatch.setattr(r5_corpus, "KNOWN_ESCAPES", {("opensrm-typo", "demo"): {}})
    with pytest.raises(r5_corpus.CorpusError):
        build(ws)
    assert r5_corpus.main(["--out", str(ws / "out"), "--archive-dir", str(ws / ".claude"),
                           "--workspace", str(ws), "--no-bd"]) == 2


def test_the_brief_prefers_the_reviewer_s_own(workspace, tmp_path):
    ws = workspace["ws"]
    rec = record("opensrm-kkk", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)])
    write_record(ws, "kkk", rec)
    assert build(ws)["opensrm-kkk"]["meta"]["brief_source"] == "none"
    private = tmp_path / "p"
    (private / "briefs").mkdir(parents=True)
    (private / "index.json").write_text(json.dumps({"pairings": []}))
    (private / "briefs" / "kkk.md").write_text("Review the diff for correctness.\n")
    (private / "briefs" / "index.json").write_text(json.dumps({"kkk": {"sha256": "x"}}))
    e = build(ws, private)["opensrm-kkk"]
    assert (e["meta"]["brief_source"], e["brief"]) == ("reviewer_brief", "Review the diff for correctness.\n")


def test_a_bundle_carries_each_entry_s_exact_trees_and_is_reproducible(workspace, tmp_path):
    ws = workspace["ws"]
    write_record(ws, "lll", record("opensrm-lll", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    entries = list(build(ws).values())
    r5_corpus.write_bundles(entries, ws, tmp_path / "b1")
    meta = entries[0]["meta"]
    bundle = tmp_path / "b1" / "demo.bundle"
    assert meta["bundle"]["sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    clone = tmp_path / "clone"
    run(tmp_path, "init", "-q", str(clone))
    run(clone, "fetch", "-q", str(bundle), "refs/r5/*:refs/r5/*")
    assert run(clone, "rev-parse", "refs/r5/opensrm-lll/head^{tree}") == meta["tree_sha"]
    assert run(clone, "rev-parse", "refs/r5/opensrm-lll/base^{tree}") == meta["base_tree"]
    assert run(clone, "rev-parse", "refs/r5/opensrm-lll/head^") == meta["bundle"]["base_commit"]
    # The diff the replay sees is the diff the gate saw.
    assert run(clone, "diff", "refs/r5/opensrm-lll/base", "refs/r5/opensrm-lll/head") == \
        run(workspace["repo"], "diff", workspace["base"], workspace["head"])
    again = list(build(ws).values())
    r5_corpus.write_bundles(again, ws, tmp_path / "b2")
    assert again[0]["meta"]["bundle"]["head_commit"] == meta["bundle"]["head_commit"]


def test_main_writes_the_light_files_and_a_summary(workspace, capsys):
    ws = workspace["ws"]
    write_record(ws, "mmm", record("opensrm-mmm", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 1}, None)]))
    out = ws / "out"
    assert r5_corpus.main(["--out", str(out), "--archive-dir", str(ws / ".claude"),
                           "--workspace", str(ws), "--no-bd"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert (summary["entries"], summary["fidelity"]["clean"]) == (1, 1)
    assert sorted(p.name for p in (out / "opensrm-mmm").iterdir()) == \
        ["brief.md", "diff.patch", "meta.json", "recorded.json"]
