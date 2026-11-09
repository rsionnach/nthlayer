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
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
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

    stamps, started, seen = [], set(), {}
    for lens, counts, fix in reviews:
        if lens not in started:
            started.add(lens)
            event(event="pass_started", **{"pass": lens})
        event(event="reviewer_dispatched", **{"pass": lens})
        seen[lens] = seen.get(lens, 0) + 1
        # Real v2 archives log the dispatch's iteration on the event.
        stamps.append(event(event="findings_received", counts=counts, iteration=seen[lens], **{"pass": lens}))
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
    entries = r5_corpus.build(ws / ".claude", ws, r5_corpus.PrivateArchive(private), use_bd=False)
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
    # The corpus carries the gate's blocking findings: the MINOR is not kept.
    assert [f["severity"] for f in first["findings"]] == ["IMPORTANT"]
    assert e["meta"]["blocking_findings"] == 1
    assert first["findings"][0]["fix_commit"] == workspace["fix"]
    assert first["findings"][0]["derived_from"] == "reviewer_transcript"
    assert second["findings"] is None  # a clean re-review: nothing was extracted
    assert (first["iteration"], second["iteration"]) == (1, 2)
    assert e["recorded"]["iterations"] == {"correctness": 2}
    assert e["meta"]["tree_sha"] == run(workspace["repo"], "rev-parse", workspace["head"] + "^{tree}")
    assert e["meta"]["base"] == workspace["base"]  # the archive's short SHA, resolved
    assert (e["meta"]["record"], e["meta"]["part"], e["meta"]["record_repos"]) == ("aaa", None, ["demo"])
    assert e["meta"]["sequential_steps"] == e["meta"]["record_sequential_steps"]


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


def test_a_record_with_no_blocking_finding_is_clean_at_counts_only(workspace):
    # blocking_findings 0 marks it clean; with no extraction of its reviews,
    # only the archive says so, so the fidelity is counts_only.
    ws = workspace["ws"]
    rec = record("opensrm-ggg", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 0, "minor": 3}, None)])
    write_record(ws, "ggg", rec)
    meta = build(ws)["opensrm-ggg"]["meta"]
    assert (meta["fidelity"], meta["blocking_findings"]) == ("counts_only", 0)


def test_a_multi_repo_record_assigns_its_findings_by_path(workspace, tmp_path):
    ws = workspace["ws"]
    rng = {"base": workspace["base"], "head": workspace["head"]}
    rec = record("opensrm-hhh", {"demo": rng, "missing": rng},
                 [("correctness", {"critical": 0, "important": 1, "minor": 1}, workspace["fix"])])
    stamps = write_record(ws, "hhh", rec)
    entries = build(ws)
    assert set(entries) == {"opensrm-hhh-demo", "opensrm-hhh-missing"}
    # No extraction: derived from the fix commit, which the archive logs in
    # demo, so its finding is demo's; steps are the record's only.
    for e in entries.values():
        assert (e["meta"]["fidelity"], e["meta"]["sequential_steps"]) == ("derived", None)
        assert e["meta"]["record_sequential_steps"] is not None
        assert e["meta"]["record_repos"] == ["demo", "missing"]
    assert [f["path"] for f in entries["opensrm-hhh-demo"]["recorded"]["rounds"][0]["findings"]] == ["app.py"]
    assert entries["opensrm-hhh-missing"]["recorded"]["rounds"][0]["findings"] == []
    assert entries["opensrm-hhh-missing"]["meta"]["unavailable"]
    # With an accepted extraction: the missing repo has no tree, so a bare
    # app.py cannot be placed by suffix and is listed cross-repo in both...
    private = private_archive(tmp_path / "p", "r5-state-hhh-completed.json", "correctness", stamps[0])
    entries = build(ws, private)
    demo, missing = entries["opensrm-hhh-demo"], entries["opensrm-hhh-missing"]
    assert demo["meta"]["fidelity"] == missing["meta"]["fidelity"] == "recorded"
    assert demo["recorded"]["rounds"][0]["findings"] == missing["recorded"]["rounds"][0]["findings"] == []
    assert [f["path"] for f in demo["recorded"]["cross_repo_findings"]] == ["app.py"]
    # ...while one that names its repo is that repo's.
    named = REPORT.replace("`app.py:2`", "`demo/app.py:2`")
    extraction = [dict(EXTRACTION[0], path="demo/app.py"), EXTRACTION[1]]
    private = private_archive(tmp_path / "p2", "r5-state-hhh-completed.json", "correctness", stamps[0],
                              report=named, extraction=extraction)
    entries = build(ws, private)
    assert [f["path"] for f in entries["opensrm-hhh-demo"]["recorded"]["rounds"][0]["findings"]] == ["app.py"]
    assert entries["opensrm-hhh-missing"]["recorded"]["cross_repo_findings"] == []


def test_a_finding_no_single_repo_holds_is_listed_cross_repo(workspace, tmp_path):
    ws = workspace["ws"]
    rng = {"base": workspace["base"], "head": workspace["head"]}
    rec = record("opensrm-xrp", {"demo": rng, "demo2": rng},
                 [("correctness", {"critical": 0, "important": 1, "minor": 1}, None)])
    stamps = write_record(ws, "xrp", rec)
    # demo2 is a second clone: app.py is in both head trees, so neither is chosen.
    run(ws, "clone", "-q", str(workspace["repo"]), str(ws / "demo2"))
    private = private_archive(tmp_path / "p", "r5-state-xrp-completed.json", "correctness", stamps[0])
    entries = build(ws, private)
    for e in entries.values():
        assert e["recorded"]["rounds"][0]["findings"] == []
        assert [f["claim"] for f in e["recorded"]["cross_repo_findings"]] == [EXTRACTION[0]["claim"]]


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
    none = build(ws)["opensrm-kkk"]
    assert (none["meta"]["brief_source"], none["brief"]) == ("none", None)  # no brief.md is written
    private = tmp_path / "p"
    (private / "briefs").mkdir(parents=True)
    (private / "index.json").write_text(json.dumps({"pairings": []}))
    (private / "briefs" / "kkk.md").write_text("Review the diff for correctness.\n")
    (private / "briefs" / "index.json").write_text(json.dumps({"kkk": {"sha256": "x"}}))
    e = build(ws, private)["opensrm-kkk"]
    assert (e["meta"]["brief_source"], e["brief"]) == ("reviewer_prompt", "Review the diff for correctness.\n")


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
    assert run(clone, "rev-parse", "refs/r5/opensrm-lll/head^") == meta["synthetic_base"]
    assert run(clone, "rev-parse", "refs/r5/opensrm-lll/head") == meta["synthetic_head"]
    assert meta["bundle"]["repo"] == "demo"
    manifest = json.loads((tmp_path / "b1" / "bundles.json").read_text())
    (item,) = manifest["bundles"]
    assert (item["repo"], item["sha256"], item["size"]) == ("demo", meta["bundle"]["sha256"], bundle.stat().st_size)
    assert item["url"].endswith(f"/releases/download/{manifest['release_tag']}/demo.bundle")
    # The diff the replay sees is the diff the gate saw.
    assert run(clone, "diff", "refs/r5/opensrm-lll/base", "refs/r5/opensrm-lll/head") == \
        run(workspace["repo"], "diff", workspace["base"], workspace["head"])
    again = list(build(ws).values())
    r5_corpus.write_bundles(again, ws, tmp_path / "b2")
    assert again[0]["meta"]["synthetic_head"] == meta["synthetic_head"]


def test_main_writes_the_light_files_and_a_summary(workspace, capsys):
    ws = workspace["ws"]
    write_record(ws, "mmm", record("opensrm-mmm", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 1}, None)]))
    out = ws / "out"
    assert r5_corpus.main(["--out", str(out), "--archive-dir", str(ws / ".claude"),
                           "--workspace", str(ws), "--no-bd"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert (summary["entries"], summary["clean_entries"]) == (1, 1)
    assert summary["fidelity"]["counts_only"] == {"entries": 1, "beads": 1}
    assert summary["brief_source"]["none"] == 1
    # brief_source none: no brief.md.
    assert sorted(p.name for p in (out / "opensrm-mmm").iterdir()) == ["diff.patch", "meta.json", "recorded.json"]


# --- severities, escapes, tree paths, review pairing, rosters, reruns ---------

def test_a_v1_record_that_logged_only_totals_is_counts_only_not_clean(workspace):
    # No findings_received at all; completed_passes says correctness found 3
    # (as v1 records did), so its severities are unknown.
    ws = workspace["ws"]
    rec = {"version": 1, "target_bead": "opensrm-nnn", "dry_run": False, "passes": ["correctness"],
           "diff_range": {"demo": {"base": workspace["base"], "head": workspace["head"]}},
           "audit_trail": [{"ts": "2000-01-01T00:00:01Z", "event": "pass_started", "pass": "correctness"}],
           "completed_passes": [{"name": "correctness", "findings_count_initial": 3, "fix_iterations": 1}]}
    (ws / ".claude" / "r5-state-nnn-completed.json").write_text(json.dumps(rec))
    e = build(ws)["opensrm-nnn"]
    assert e["meta"]["fidelity"] == "counts_only"
    assert e["meta"]["baseline"]["correctness"]["findings_first_review"] == 3
    assert e["meta"]["baseline"]["correctness"]["unattributed"] == 3


def test_an_escape_in_the_gate_s_last_tree_moves_the_entry_head(workspace, monkeypatch):
    # The escaped line exists only from the fix commit on (app.py line 3).
    ws = workspace["ws"]
    write_record(ws, "ooo", record("opensrm-ooo", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    escape = {"lens": "provenance", "severity": "CRITICAL", "path": "app.py", "start_line": 3,
              "end_line": 3, "at_commit": workspace["fix"][:7], "claim": "c is never read"}
    monkeypatch.setattr(r5_corpus, "KNOWN_ESCAPES", {("opensrm-ooo", "demo"): escape})
    meta = build(ws)["opensrm-ooo"]["meta"]
    assert (meta["head"], meta["record_head"]) == (workspace["fix"], workspace["head"])
    assert meta["tree_sha"] == run(workspace["repo"], "rev-parse", workspace["fix"] + "^{tree}")
    # Lines the carried tree does not have are refused, not published.
    monkeypatch.setattr(r5_corpus, "KNOWN_ESCAPES", {("opensrm-ooo", "demo"): dict(escape, end_line=9)})
    with pytest.raises(r5_corpus.CorpusError):
        build(ws)


def test_a_path_already_in_the_tree_is_kept():
    assert r5_corpus.repo_path("app.py", {"app.py", "src/pkg/app.py"}, "demo") == ("app.py", True)


@pytest.mark.parametrize("reported, expected", [
    ("/Users/someone/ws/demo-worktree/src/pkg/app.py", ("src/pkg/app.py", True)),
    ("demo/src/pkg/app.py", ("src/pkg/app.py", True)),
    ("loader.py", ("src/pkg/loader.py", True)),
    ("util.py", ("util.py", False)),  # two candidates: none is chosen
    ("/Users/someone/ws/demo/nowhere.py", ("nowhere.py", False)),  # no local path leaks
    (None, (None, False)),
])
def test_a_reported_path_becomes_a_tree_path_or_is_flagged(reported, expected):
    files = {"src/pkg/app.py", "src/pkg/loader.py", "a/util.py", "b/util.py"}
    assert r5_corpus.repo_path(reported, files, "demo") == expected


def test_a_commit_after_a_later_review_or_pass_end_is_not_the_earlier_fix(workspace):
    trail = [
        {"ts": "2000-01-01T00:00:01Z", "event": "pass_started", "pass": "correctness"},
        {"ts": "2000-01-01T00:00:02Z", "event": "findings_received", "pass": "correctness",
         "counts": {"critical": 0, "important": 1, "minor": 0}},
        {"ts": "2000-01-01T00:00:03Z", "event": "pass_completed", "pass": "correctness", "fix_iterations": 0},
        {"ts": "2000-01-01T00:00:04Z", "event": "commit_made", "sha": workspace["fix"], "repo": "demo"},
    ]
    (r,) = r5_corpus.reviews({"version": 2, "audit_trail": trail})
    assert r["fix_commit"] is None


def test_a_one_off_pass_naming_a_blocking_lens_blocks_and_v1_excellence_blocks():
    v2 = {"version": 2, "passes": ["correctness"]}
    v1 = {"version": 1, "passes": ["correctness", "clarity", "edge-cases", "excellence"]}
    assert r5_corpus.lens_blocks("clarity+edge-cases", r5_corpus.blocking_lenses(v2))
    assert r5_corpus.lens_blocks("delta-clarity", r5_corpus.blocking_lenses(v2))
    assert not r5_corpus.lens_blocks("excellence", r5_corpus.blocking_lenses(v2))
    assert r5_corpus.lens_blocks("excellence", r5_corpus.blocking_lenses(v1))


def test_a_rerun_removes_entries_the_archive_no_longer_yields(workspace, tmp_path):
    out = tmp_path / "out"
    (out / "opensrm-stale").mkdir(parents=True)
    (out / "opensrm-stale" / "meta.json").write_text(json.dumps({"schema_version": 1, "entry": "opensrm-stale"}))
    (out / "README.md").write_text("kept\n")
    r5_corpus.write_entries([], out)
    assert sorted(p.name for p in out.iterdir()) == ["README.md"]


def test_an_out_holding_a_directory_it_did_not_write_is_refused_untouched(tmp_path):
    # The private archive keeps raw reports in opensrm-<bead>/ directories.
    out = tmp_path / "r5-handbacks"
    (out / "opensrm-0i5h").mkdir(parents=True)
    (out / "opensrm-0i5h" / "report.md").write_text("raw\n")
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.write_entries([], out)
    assert (out / "opensrm-0i5h" / "report.md").read_text() == "raw\n"


# --- no local path is published --------------------------------------------

def test_no_local_path_is_published_in_a_finding_or_a_brief(workspace, tmp_path):
    ws = workspace["ws"]
    local = f"{ws}/demo-wt/app.py"
    report = REPORT.replace("`app.py:2`", f"`{local}:2`")
    extraction = [dict(EXTRACTION[0], path=local), EXTRACTION[1]]
    rec = record("opensrm-ppp", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 1}, None)])
    stamps = write_record(ws, "ppp", rec)
    private = private_archive(tmp_path / "p", "r5-state-ppp-completed.json", "correctness", stamps[0],
                              report=report, extraction=extraction)
    (private / "briefs").mkdir()
    (private / "briefs" / "ppp.md").write_text(f"Review {ws}/demo for correctness.\n")
    (private / "briefs" / "index.json").write_text(json.dumps({"ppp": {}}))
    e = build(ws, private)["opensrm-ppp"]
    assert e["meta"]["fidelity"] == "recorded"
    published = json.dumps(e["recorded"]) + json.dumps(e["meta"]) + e["brief"]
    assert str(ws) not in published and str(ws.resolve()) not in published
    f = e["recorded"]["rounds"][0]["findings"][0]
    assert (f["path"], f["path_in_tree"], f["reported_path"]) == ("app.py", True, "<workspace>/demo-wt/app.py")


def test_a_dot_slash_prefix_is_removed_but_not_a_leading_dot():
    files = {".github/workflows/ci.yml"}
    assert r5_corpus.repo_path("./.github/workflows/ci.yml", files, "demo") == (".github/workflows/ci.yml", True)


def test_a_passless_review_is_placed_as_the_baseline_places_it(monkeypatch):
    trail = [{"ts": "2000-01-01T00:00:02Z", "event": "findings_received",
              "counts": {"critical": 1, "important": 0, "minor": 0}}]
    monkeypatch.setattr(r5_corpus.r5_baseline, "PASSLESS_EVENTS",
                        {("opensrm-qqq", "findings_received", "2000-01-01T00:00:02Z"): "correctness"})
    (r,) = r5_corpus.reviews({"version": 2, "target_bead": "opensrm-qqq", "audit_trail": trail})
    assert (r["lens"], r5_corpus.raised_blocking_finding(r)) == ("correctness", True)


# --- masking the workspace and home ----------------------------------------

def test_masking_a_relative_workspace_touches_only_its_absolute_path(tmp_path, monkeypatch):
    ws = tmp_path / "eco"
    ws.mkdir()
    monkeypatch.chdir(ws / "..")
    text = f"range f42ce8d..28d7add, ../x.py and a.b, file {ws}/demo/app.py"
    masked = r5_corpus.mask_workspace(text, Path("eco"))
    assert masked == "range f42ce8d..28d7add, ../x.py and a.b, file <workspace>/demo/app.py"
    monkeypatch.chdir(ws)
    assert r5_corpus.mask_workspace("a..b a.b", Path(".")) == "a..b a.b"


def test_masking_home_respects_the_path_boundary(monkeypatch):
    monkeypatch.setattr(r5_corpus.Path, "home", classmethod(lambda cls: Path("/Users/rob")))
    assert r5_corpus.mask_workspace("/Users/rob/x and /Users/robert/y", Path("/nowhere")) == \
        "~/x and /Users/robert/y"


def test_masking_stops_at_a_sibling_that_shares_the_workspace_name_prefix(tmp_path):
    ws = tmp_path / "nthlayer"
    ws.mkdir()
    text = f"{ws}/scripts/x.py and {tmp_path}/nthlayer-common/y.py"
    assert r5_corpus.mask_workspace(text, ws) == f"<workspace>/scripts/x.py and {tmp_path}/nthlayer-common/y.py"


# --- malformed inputs, reproducible bundles -----------------------------------

def test_two_builds_give_byte_identical_bundles(workspace, tmp_path):
    ws, repo = workspace["ws"], workspace["repo"]
    # Enough distinct objects for a delta search to have choices to make.
    for i in range(30):
        commit(repo, {f"m{i}.py": "\n".join(f"line {j} {i}" for j in range(200))}, f"more {i}")
    head = run(repo, "rev-parse", "HEAD")
    write_record(ws, "rrr", record("opensrm-rrr", {"demo": {"base": workspace["base"], "head": head}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    digests = []
    for n in (1, 2):
        entries = list(build(ws).values())
        r5_corpus.write_bundles(entries, ws, tmp_path / f"b{n}")
        digests.append(hashlib.sha256((tmp_path / f"b{n}" / "demo.bundle").read_bytes()).hexdigest())
    assert digests[0] == digests[1]


@pytest.mark.parametrize("index", [
    "{not json",
    json.dumps({"pairings": [{"record": "r", "lens": "correctness"}]}),  # keys missing
    json.dumps({"pairings": "nope"}),
])
def test_an_unreadable_private_index_is_refused(tmp_path, index):
    (tmp_path / "index.json").write_text(index)
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.PrivateArchive(tmp_path)


def test_the_report_hash_covers_its_bytes(workspace, tmp_path):
    # A CRLF report whose bytes match the index is accepted, not refused.
    ws = workspace["ws"]
    rec = record("opensrm-sss", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 1}, None)])
    stamps = write_record(ws, "sss", rec)
    crlf = REPORT.replace("\n", "\r\n")
    private = tmp_path / "p"
    sha = hashlib.sha256(crlf.encode()).hexdigest()
    (private / "bead").mkdir(parents=True)
    (private / "extractions").mkdir()
    (private / "bead" / f"{sha[:16]}.md").write_bytes(crlf.encode())
    (private / "extractions" / f"{sha[:16]}.json").write_text(json.dumps(EXTRACTION))
    (private / "index.json").write_text(json.dumps({"pairings": [{
        "record": "r5-state-sss-completed.json", "lens": "correctness",
        "findings_received_ts": stamps[0], "sha256": sha, "file": f"bead/{sha[:16]}.md"}]}))
    assert build(ws, private)["opensrm-sss"]["meta"]["fidelity"] == "recorded"


def test_a_hung_bd_is_refused_not_a_silently_lesser_brief(tmp_path, monkeypatch):
    (tmp_path / "opensrm").mkdir()
    monkeypatch.setattr(r5_corpus.shutil, "which", lambda name: "/usr/bin/bd")

    def hang(*args, **kwargs):
        assert kwargs.get("timeout")  # bounded, never open-ended
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(r5_corpus.subprocess, "run", hang)
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.bead_description("opensrm-x", tmp_path / "opensrm")


def test_a_record_without_a_bead_is_refused(workspace):
    ws = workspace["ws"]
    # A second record, so the baseline's per-bead sort has keys to compare.
    write_record(ws, "tt2", record("opensrm-tt2", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 1}, None)]))
    rec = record("opensrm-ttt", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 0, "minor": 1}, None)])
    rec.pop("_stamps")
    del rec["target_bead"]
    (ws / ".claude" / "r5-state-ttt-completed.json").write_text(json.dumps(rec))
    with pytest.raises(r5_corpus.CorpusError):
        build(ws)
    assert r5_corpus.r5_baseline.main(["--archive-dir", str(ws / ".claude"), "--json"]) == 2


def test_the_bundle_is_packed_single_threaded(workspace, tmp_path, monkeypatch):
    # A threaded delta search reorders objects run to run on a real repo (the
    # synthetic one above is too small to show it), so the published sha256
    # rests on this setting: assert it is passed.
    ws = workspace["ws"]
    write_record(ws, "uuu", record("opensrm-uuu", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    entries = list(build(ws).values())
    calls, real = [], r5_corpus.git
    monkeypatch.setattr(r5_corpus, "git", lambda repo, *a, **k: (calls.append(a), real(repo, *a, **k))[1])
    r5_corpus.write_bundles(entries, ws, tmp_path / "b")
    (bundle,) = [a for a in calls if "bundle" in a]
    assert bundle[:2] == ("-c", "pack.threads=1")
    assert set(r5_corpus.PACK_CONFIG) <= set(bundle)


def test_the_caller_s_git_config_does_not_change_the_bundle(workspace, tmp_path, monkeypatch):
    ws, repo = workspace["ws"], workspace["repo"]
    # A large file that changes slightly, so the pack has a delta for an
    # inherited setting to change.
    big = "\n".join(f"line {i} of a long module" for i in range(5000))
    base = commit(repo, {"big.py": big}, "big")
    head = commit(repo, {"big.py": big.replace("line 2500 ", "line 2500 changed ")}, "big change")
    write_record(ws, "vvv", record("opensrm-vvv", {"demo": {"base": base, "head": head}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    entries = list(build(ws).values())
    r5_corpus.write_bundles(entries, ws, tmp_path / "plain")
    # A key PACK_CONFIG does not pin, so only the isolation keeps it out.
    for key, value in {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bigFileThreshold",
                       "GIT_CONFIG_VALUE_0": "1"}.items():
        monkeypatch.setenv(key, value)
    again = list(build(ws).values())
    r5_corpus.write_bundles(again, ws, tmp_path / "configured")
    assert (tmp_path / "plain" / "demo.bundle").read_bytes() == (tmp_path / "configured" / "demo.bundle").read_bytes()
    manifest = json.loads((tmp_path / "configured" / "bundles.json").read_text())
    assert manifest["bundles"][0]["git_version"].startswith("git version")


def test_a_foreign_out_is_refused_before_any_bundle_is_written(workspace, tmp_path):
    ws = workspace["ws"]
    write_record(ws, "www", record("opensrm-www", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    out, bundles = tmp_path / "out", tmp_path / "bundles"
    out.mkdir()
    (out / "opensrm-www").write_text("a file, not an entry\n")
    assert r5_corpus.main(["--out", str(out), "--bundles", str(bundles), "--archive-dir",
                           str(ws / ".claude"), "--workspace", str(ws), "--no-bd"]) == 2
    assert not bundles.exists()
    assert (out / "opensrm-www").read_text() == "a file, not an entry\n"


def test_a_symlink_named_like_an_entry_is_refused(tmp_path):
    real = tmp_path / "elsewhere" / "opensrm-xxx"
    real.mkdir(parents=True)
    (real / "meta.json").write_text(json.dumps({"schema_version": 1, "entry": "opensrm-xxx"}))
    out = tmp_path / "out"
    out.mkdir()
    (out / "opensrm-xxx").symlink_to(real)
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.write_entries([], out)
    assert (real / "meta.json").exists()



def _fake_bd(monkeypatch, returncode: int, stdout: str = "", stderr: str = ""):
    monkeypatch.setattr(r5_corpus.shutil, "which", lambda name: "/usr/bin/bd")
    monkeypatch.setattr(r5_corpus.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], returncode, stdout=stdout, stderr=stderr))


def test_a_failing_bd_is_refused_but_a_missing_bead_is_not(tmp_path, monkeypatch):
    (tmp_path / "opensrm").mkdir()
    _fake_bd(monkeypatch, 1, stderr="Error: database is locked")
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.bead_description("opensrm-x", tmp_path / "opensrm")
    _fake_bd(monkeypatch, 0, stdout="not json")
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.bead_description("opensrm-x", tmp_path / "opensrm")
    _fake_bd(monkeypatch, 1, stderr="Error: no issue found matching \"opensrm-x\"")
    assert r5_corpus.bead_description("opensrm-x", tmp_path / "opensrm") is None


def test_bd_absent_without_no_bd_is_refused(tmp_path, monkeypatch):
    (tmp_path / "opensrm").mkdir()
    monkeypatch.setattr(r5_corpus.shutil, "which", lambda name: None)
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.bead_description("opensrm-x", tmp_path / "opensrm")


def test_a_config_reaching_commit_tree_does_not_change_the_bundle(workspace, tmp_path, monkeypatch):
    ws = workspace["ws"]
    write_record(ws, "yyy", record("opensrm-yyy", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    entries = list(build(ws).values())
    r5_corpus.write_bundles(entries, ws, tmp_path / "plain")
    for key, value in {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "i18n.commitEncoding",
                       "GIT_CONFIG_VALUE_0": "ISO-8859-1", "GIT_DIR": str(workspace["repo"] / ".git")}.items():
        monkeypatch.setenv(key, value)
    again = list(build(ws).values())
    r5_corpus.write_bundles(again, ws, tmp_path / "configured")
    assert again[0]["meta"]["synthetic_head"] == entries[0]["meta"]["synthetic_head"]
    assert (tmp_path / "plain" / "demo.bundle").read_bytes() == (tmp_path / "configured" / "demo.bundle").read_bytes()
    assert not run(workspace["repo"], "for-each-ref", "refs/r5")  # nothing written to the caller's repo


def test_an_out_that_is_a_file_is_refused_before_bundles(workspace, tmp_path):
    ws = workspace["ws"]
    write_record(ws, "zzz", record("opensrm-zzz", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    out, bundles = tmp_path / "out", tmp_path / "bundles"
    out.write_text("a file\n")
    assert r5_corpus.main(["--out", str(out), "--bundles", str(bundles), "--archive-dir",
                           str(ws / ".claude"), "--workspace", str(ws), "--no-bd"]) == 2
    assert not bundles.exists()



@pytest.mark.parametrize("stdout", ["[]", json.dumps({"error": "x"}), json.dumps([{"id": "opensrm-x"}])])
def test_bd_answering_with_no_bead_is_refused(tmp_path, monkeypatch, stdout):
    (tmp_path / "opensrm").mkdir()
    _fake_bd(monkeypatch, 0, stdout=stdout)
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.bead_description("opensrm-x", tmp_path / "opensrm")


def test_an_inherited_git_dir_does_not_redirect_source_repo_calls(workspace, monkeypatch, tmp_path):
    other = tmp_path / "other"
    run(tmp_path, "init", "-q", str(other))
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert r5_corpus.resolve(workspace["repo"], workspace["head"]) == workspace["head"]


def test_bundles_that_is_a_file_is_refused(workspace, tmp_path):
    ws = workspace["ws"]
    write_record(ws, "abc", record("opensrm-abc", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    (tmp_path / "bundles").write_text("a file\n")
    assert r5_corpus.main(["--out", str(tmp_path / "out"), "--bundles", str(tmp_path / "bundles"),
                           "--archive-dir", str(ws / ".claude"), "--workspace", str(ws), "--no-bd"]) == 2
    assert not (tmp_path / "out").exists()



# --- review numbering, pairing, counted records, refusals ---------------------

def test_rounds_are_numbered_per_lens_and_keep_the_archive_s_iteration():
    trail = [
        {"ts": "t1", "event": "findings_received", "pass": "correctness", "iteration": 1,
         "counts": {"critical": 0, "important": 1, "minor": 0}},
        {"ts": "t2", "event": "findings_received", "pass": "clarity", "iteration": 1,
         "counts": {"critical": 0, "important": 0, "minor": 0}},
        {"ts": "t3", "event": "findings_received", "pass": "correctness", "iteration": 1,  # a re-run restarts
         "counts": {"critical": 0, "important": 0, "minor": 0}},
    ]
    revs = r5_corpus.reviews({"version": 2, "target_bead": "b", "audit_trail": trail})
    assert [(r["lens"], r["iteration"], r["recorded_iteration"]) for r in revs] == [
        ("correctness", 1, 1), ("clarity", 1, 1), ("correctness", 2, 1)]


def test_the_first_commit_after_a_review_is_its_fix_not_a_later_one(workspace):
    trail = [
        {"ts": "t1", "event": "findings_received", "pass": "correctness",
         "counts": {"critical": 0, "important": 1, "minor": 0}},
        {"ts": "t2", "event": "commit_made", "sha": workspace["fix"], "repo": "demo"},
        {"ts": "t3", "event": "commit_made", "sha": workspace["head"], "repo": "demo"},
    ]
    (r,) = r5_corpus.reviews({"version": 2, "target_bead": "b", "audit_trail": trail})
    assert r["fix_commit"] == workspace["fix"]


def test_a_dry_run_record_yields_no_entry(workspace):
    ws = workspace["ws"]
    rec = record("opensrm-dry", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 1, "minor": 0}, None)])
    rec["dry_run"] = True
    write_record(ws, "dry", rec)
    write_record(ws, "live", record("opensrm-live", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                    [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    assert set(build(ws)) == {"opensrm-live"}


def test_a_record_with_no_diff_range_is_refused(workspace):
    ws = workspace["ws"]
    rec = record("opensrm-nod", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)])
    rec["diff_range"] = {}
    write_record(ws, "nod", rec)
    with pytest.raises(r5_corpus.CorpusError):
        build(ws)


def test_a_v2_excellence_finding_never_makes_an_entry_blocking(workspace):
    # Excellence is advisory from the 2026-08-28 roster on, so a v2 record
    # whose only IMPORTANT is excellence's is clean.
    ws = workspace["ws"]
    write_record(ws, "exc", record("opensrm-exc", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 1}, None),
                                    ("excellence", {"critical": 0, "important": 1, "minor": 0}, None)]))
    assert build(ws)["opensrm-exc"]["meta"]["blocking_findings"] == 0



def test_a_built_round_keeps_the_archive_s_iteration_where_it_differs(workspace):
    # A re-run pass restarts the archive's count: the second correctness
    # review logs iteration 1 again, as 41 real reviews do.
    ws = workspace["ws"]
    rec = record("opensrm-rit", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                 [("correctness", {"critical": 0, "important": 0, "minor": 1}, None),
                  ("correctness", {"critical": 0, "important": 0, "minor": 0}, None)])
    reviews = [e for e in rec["audit_trail"] if e["event"] == "findings_received"]
    reviews[1]["iteration"] = 1
    write_record(ws, "rit", rec)
    rounds = build(ws)["opensrm-rit"]["recorded"]["rounds"]
    assert [(r["iteration"], r["recorded_iteration"]) for r in rounds] == [(1, 1), (2, 1)]


def test_a_commit_with_no_sha_names_no_fix_and_ends_the_window(workspace):
    trail = [
        {"ts": "t1", "event": "findings_received", "pass": "correctness",
         "counts": {"critical": 0, "important": 1, "minor": 0}},
        {"ts": "t2", "event": "commit_made"},  # as one real archive logs it
        {"ts": "t3", "event": "commit_made", "sha": workspace["fix"], "repo": "demo"},
    ]
    (r,) = r5_corpus.reviews({"version": 2, "target_bead": "b", "audit_trail": trail})
    assert r["fix_commit"] is None


def test_the_caller_s_global_git_config_does_not_change_the_bundle(workspace, tmp_path, monkeypatch):
    ws, repo = workspace["ws"], workspace["repo"]
    big = "\n".join(f"line {i} of a long module" for i in range(5000))
    base = commit(repo, {"big.py": big}, "big")
    head = commit(repo, {"big.py": big.replace("line 2500 ", "line 2500 changed ")}, "big change")
    write_record(ws, "gcf", record("opensrm-gcf", {"demo": {"base": base, "head": head}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    r5_corpus.write_bundles(list(build(ws).values()), ws, tmp_path / "plain")
    home = tmp_path / "home"
    (home / ".config" / "git").mkdir(parents=True)
    hostile = "[core]\n\tbigFileThreshold = 1\n"
    (home / ".gitconfig").write_text(hostile)
    (home / ".config" / "git" / "config").write_text(hostile)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    r5_corpus.write_bundles(list(build(ws).values()), ws, tmp_path / "configured")
    assert (tmp_path / "plain" / "demo.bundle").read_bytes() == (tmp_path / "configured" / "demo.bundle").read_bytes()


def test_a_bullet_naming_two_changed_files_is_not_derived(workspace):
    # The one-to-one rule: a bullet naming both files of a two-file fix
    # gives no single path, so nothing is chosen.
    ws, repo = workspace["ws"], workspace["repo"]
    fix = commit(repo, {"app.py": "a = 7\n", "other.py": "x = 7\n"},
                 "r5(correctness): 1 finding\n\n- IMPORTANT: app.py and other.py disagree on x\n")
    write_record(ws, "two", record("opensrm-two", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 1, "minor": 0}, fix)]))
    assert build(ws)["opensrm-two"]["meta"]["fidelity"] == "counts_only"


def test_a_deletion_only_hunk_gives_no_changed_line(workspace):
    repo = workspace["repo"]
    sha = commit(repo, {"app.py": "a = 1\n"}, "drop b")  # app.py loses its other lines
    assert r5_corpus.changed_span(repo, sha, "app.py") is None


def test_a_blank_line_ends_a_severity_bullet():
    assert r5_corpus.severity_bullets("- IMPORTANT: one\n\nnot part of it\n") == [("IMPORTANT", "one")]


def test_a_one_off_pass_naming_a_lens_by_its_first_word_blocks():
    assert r5_corpus.lens_blocks("scoped(correctness+edge)", {"edge-cases"})


def test_an_absolute_path_is_cut_after_the_last_part_naming_the_repo():
    # A worktree "demo-wt" inside a workspace that also holds "demo".
    assert r5_corpus.repo_path("/ws/demo/../demo-wt/src/x.py", set(), "demo") == ("src/x.py", False)



def test_the_part_is_the_stem_s_suffix_after_the_bead():
    assert r5_corpus.record_part("zo0o-workers", "opensrm-zo0o") == "workers"
    assert r5_corpus.record_part("wo62-1-checkpointA-floors", "opensrm-wo62.1") == "checkpointA-floors"
    assert r5_corpus.record_part("jmy.7", "opensrm-jmy.7") is None
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.record_part("other-x", "opensrm-zo0o")


def test_a_record_whose_severities_are_unknown_has_no_blocking_count(workspace):
    ws = workspace["ws"]
    rec = {"version": 1, "target_bead": "opensrm-unk", "dry_run": False, "passes": ["correctness"],
           "diff_range": {"demo": {"base": workspace["base"], "head": workspace["head"]}},
           "audit_trail": [{"ts": "2000-01-01T00:00:01Z", "event": "pass_started", "pass": "correctness"}],
           "completed_passes": [{"name": "correctness", "findings_count_initial": 2, "fix_iterations": 0}]}
    (ws / ".claude" / "r5-state-unk-completed.json").write_text(json.dumps(rec))
    meta = build(ws)["opensrm-unk"]["meta"]
    assert (meta["fidelity"], meta["blocking_findings"]) == ("counts_only", None)



@pytest.mark.parametrize("path, expected", [
    ("demo2/app.py", ("demo2", "app.py", True)),  # names its repo: not ambiguous
    ("./demo2/app.py", ("demo2", "app.py", True)),
    # Absolute, with no workspace to say where its root is: not placed
    # (with the workspace given, it is; see the member tests below).
    ("/Users/x/eco/demo2/app.py", (None, "app.py", False)),  # a local absolute path is cut
    ("../demo2/app.py", ("demo2", "app.py", True)),
    # A worktree of demo2 is known only from the workspace (tested with a
    # real one below); without it, "demo2-wt" names no record repo.
    ("demo2-wt/app.py", (None, "demo2-wt/app.py", False)),
    ("docs/only-demo.md", ("demo", "docs/only-demo.md", True)),  # exactly in one tree first
    ("examples/demo2/only-demo.md", ("demo", "examples/demo2/only-demo.md", True)),  # a dir named like a sibling
    ("demo2-other/x.py", (None, "demo2-other/x.py", False)),  # starts with a name, not in its tree
    ("", (None, None, False)),
    ("./", (None, None, False)),
    ("demo2", ("demo2", None, False)),  # the bare repo name: that repo, no file
    ("app.py", (None, "app.py", False)),  # in both trees: no single repo
])
def test_a_path_naming_one_of_the_record_s_repos_is_that_repo_s(path, expected):
    repos = {"demo": {"head": "h1"}, "demo2": {"head": "h2"}}
    files = {"demo": {"app.py", "docs/only-demo.md", "examples/demo2/only-demo.md", "notes.md"},
             "demo2": {"app.py"}}
    assert r5_corpus.assign(path, repos, files) == expected


def test_the_summary_does_not_count_a_pathless_finding_as_outside_the_tree():
    # repo_path(None) says path_in_tree=False: the summary must not read that
    # as a path outside the tree.
    f = r5_corpus.finding("correctness", "IMPORTANT", None, None, None, "a claim", path_in_tree=False)
    g = r5_corpus.finding("correctness", "IMPORTANT", "x.py", 1, 1, "b claim", path_in_tree=False)
    entry = {"meta": {"bead": "b", "fidelity": "recorded", "blocking_findings": 2, "brief_source": "none",
                      "unavailable": None, "entry": "e", "archive": "a"},
             "recorded": {"rounds": [{"findings": [f, g]}], "cross_repo_findings": []}}
    counts = r5_corpus.summary([entry])["located_findings"]
    assert (counts["no_path"], counts["path_not_in_tree"]) == (1, 1)



def test_two_records_yielding_one_entry_name_are_refused(workspace):
    ws = workspace["ws"]
    rng = {"base": workspace["base"], "head": workspace["head"]}
    # A multi-repo record "kk" spanning demo makes opensrm-kk-demo, as does a
    # single-repo record whose stem is kk-demo.
    write_record(ws, "kk", record("opensrm-kk", {"demo": rng, "other": rng},
                                  [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    write_record(ws, "kk-demo", record("opensrm-kk", {"demo": rng},
                                       [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    with pytest.raises(r5_corpus.CorpusError):
        build(ws)


def test_a_fix_repo_outside_the_record_is_found_by_its_commit(workspace):
    repos = {"demo": {"path": workspace["repo"], "head": workspace["head"]}}
    review = {"fix_repo": "elsewhere", "fix_commit": workspace["fix"]}
    assert r5_corpus._fix_repo(review, repos) == "demo"
    assert r5_corpus._fix_repo(dict(review, fix_commit="0" * 40), repos) is None


def test_no_suffix_match_when_a_record_repo_has_no_tree():
    repos = {"demo": {"head": "h"}, "gone": {"head": None}}
    files = {"demo": {"app.py"}, "gone": set()}
    assert r5_corpus.assign("app.py", repos, files) == (None, "app.py", False)


def test_an_empty_part_is_no_part():
    assert r5_corpus.record_part("a-", "opensrm-a") is None


def test_a_stale_bundle_is_removed_with_its_repo(workspace, tmp_path):
    ws = workspace["ws"]
    write_record(ws, "stb", record("opensrm-stb", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    out = tmp_path / "b"
    out.mkdir()
    (out / "old-repo.bundle").write_bytes(b"stale")
    (out / "bundles.json").write_text(json.dumps({"bundles": [{"asset": "old-repo.bundle"}]}))
    r5_corpus.write_bundles(list(build(ws).values()), ws, out)
    assert sorted(p.name for p in out.iterdir()) == ["bundles.json", "demo.bundle"]


def test_a_bundle_this_script_did_not_list_is_refused_untouched(workspace, tmp_path):
    ws = workspace["ws"]
    write_record(ws, "stc", record("opensrm-stc", {"demo": {"base": workspace["base"], "head": workspace["head"]}},
                                   [("correctness", {"critical": 0, "important": 0, "minor": 0}, None)]))
    out = tmp_path / "b"
    out.mkdir()
    (out / "my-backup.bundle").write_bytes(b"mine")
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.write_bundles(list(build(ws).values()), ws, out)
    assert (out / "my-backup.bundle").read_bytes() == b"mine"
    assert r5_corpus.main(["--out", str(tmp_path / "out"), "--bundles", str(out), "--archive-dir",
                           str(ws / ".claude"), "--workspace", str(ws), "--no-bd"]) == 2
    assert not (tmp_path / "out").exists()



def _member(ws: Path, name: str, files: dict[str, str]) -> Path:
    repo = ws / name
    repo.mkdir(parents=True)
    run(repo, "init", "-q")
    commit(repo, files, "init")
    return repo


def test_a_path_naming_a_member_outside_the_record_is_cross_repo(tmp_path):
    # Record repos nthlayer and nthlayer-workers; nthlayer-common is another
    # member. Its CLAUDE.md must not land in nthlayer, whose tree also has one.
    ws = tmp_path / "eco"
    for name in ("nthlayer", "nthlayer-workers", "nthlayer-common"):
        _member(ws, name, {"CLAUDE.md": f"{name}\n", "pyproject.toml": "x\n"})
    repos = {n: {"path": ws / n, "head": run(ws / n, "rev-parse", "HEAD")} for n in ("nthlayer", "nthlayer-workers")}
    files = {n: r5_corpus.tree_paths(st["path"], st["head"]) for n, st in repos.items()}
    w = r5_corpus.Workspace(ws)
    assert r5_corpus.assign("nthlayer-common/CLAUDE.md", repos, files, w)[0] is None
    assert r5_corpus.assign("nthlayer-common/pyproject.toml", repos, files, w)[0] is None
    # An absolute path into a record repo, file not (yet) in its tree, is that repo's.
    assert r5_corpus.assign(f"{ws}/nthlayer-workers/src/new.py", repos, files, w) == \
        ("nthlayer-workers", "src/new.py", False)
    # The bare repo after the workspace path: that repo, no file.
    assert r5_corpus.assign(f"{ws}/nthlayer-workers", repos, files, w) == ("nthlayer-workers", None, False)
    # The workspace's own top-level file names no record repo: cross-repo.
    assert r5_corpus.assign(f"{ws}/CLAUDE.md", repos, files, w)[0] is None


def test_a_worktree_of_a_record_repo_is_that_repo(tmp_path):
    ws = tmp_path / "eco"
    a = _member(ws, "alpha", {"a.py": "1\n", "shared.md": "a\n"})
    _member(ws, "beta", {"b.py": "1\n", "shared.md": "b\n"})
    run(a, "worktree", "add", "-q", str(ws / "alpha-fix"))
    repos = {n: {"path": ws / n, "head": run(ws / n, "rev-parse", "HEAD")} for n in ("alpha", "beta")}
    files = {n: r5_corpus.tree_paths(st["path"], st["head"]) for n, st in repos.items()}
    assert r5_corpus.assign("alpha-fix/shared.md", repos, files, r5_corpus.Workspace(ws)) == \
        ("alpha", "shared.md", True)


@pytest.mark.parametrize("assets", [["../outside.bundle"], ["/abs/x.bundle"], [3]])
def test_a_manifest_listing_a_non_plain_asset_is_refused(tmp_path, assets):
    (tmp_path / "bundles.json").write_text(json.dumps({"bundles": [{"asset": a} for a in assets]}))
    with pytest.raises(r5_corpus.CorpusError):
        r5_corpus.previous_assets(tmp_path)



def test_the_first_workspace_directory_in_a_path_decides_not_an_inner_one(tmp_path):
    # generate holds examples/opensrm/ and .claude/, both named like
    # workspace directories; a path through them stays generate's.
    ws = tmp_path / "eco"
    _member(ws, "opensrm", {"spec.md": "s\n"})
    _member(ws, "nthlayer-common", {"lib.py": "l\n"})
    _member(ws, "nthlayer-generate", {"examples/opensrm/batch.yaml": "b\n", ".claude/settings.json": "{}\n",
                                      "x.py": "x\n"})
    (ws / ".claude").mkdir()
    w = r5_corpus.Workspace(ws)
    for names in (("nthlayer-generate", "opensrm"), ("nthlayer-generate", "nthlayer-common")):
        repos = {n: {"path": ws / n, "head": run(ws / n, "rev-parse", "HEAD")} for n in names}
        files = {n: r5_corpus.tree_paths(st["path"], st["head"]) for n, st in repos.items()}
        assert r5_corpus.assign("nthlayer-generate/examples/opensrm/batch.yaml", repos, files, w) == \
            ("nthlayer-generate", "examples/opensrm/batch.yaml", True)
        assert r5_corpus.assign(f"{ws}/nthlayer-generate/.claude/settings.json", repos, files, w) == \
            ("nthlayer-generate", ".claude/settings.json", True)
