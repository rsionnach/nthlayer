"""Tests for scripts/r5_record.py (opensrm-6kqs.4, R5-R48).

Two sources fix every input and expected value here, never the script:

- the round-record shape, from "Round record" in section 6 of
  docs/superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md, and bead 4
  in section 3 ("each sequential lens iteration is one review or verify round
  with one lens in lenses, and each fix is a fix round");
- the audit events, as r5-supervise's SKILL.md tells the supervisor to append
  them (Step 1 state shape; Step 3 reviewer_dispatched; Step 4
  findings_received and reviewer_unavailable; Step 5 fixes_applied; Step 7
  commit_made; Step 8 pass_completed; advisory passes).

The rulings the script applies (Rob, 2026-11-13) are quoted where they set an
expected value: D2 null when unmeasured, duration from timestamps; D3
top-level fields only for one repo; D4 the lens key edge_cases; (a) null for
parser lists a record never carried; (b) no single commit, null; (c) the
top-level head is where the gate ended; (d) a fix round dispatches no lens.

Run: uv run --no-project --with pytest pytest -q test/test_r5_record.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "r5_record.py"
sys.path.insert(0, str(SCRIPT.parent))
_spec = importlib.util.spec_from_file_location("r5_record", SCRIPT)
assert _spec and _spec.loader
r5_record = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r5_record)

BASE, HEAD0, FIX1, FIX2 = "1111111", "2222222", "3333333", "4444444"


def ev(ts: str, event: str, **fields) -> dict:
    return {"ts": f"2026-11-13T10:{ts}+00:00", "event": event, **fields}


def finding(lens: str, severity: str = "IMPORTANT", claim: str = "the branch never fires") -> dict:
    """A parser finding in the section 6 Finding shape."""
    return {"lens": lens, "severity": severity, "path": "scripts/x.py", "start_line": 3,
            "end_line": 4, "claim": claim, "evidence": "line 3", "fingerprint": "a" * 16}


def received(ts: str, pass_: str, iteration: int, findings: list, **more) -> dict:
    """Step 4: findings_received carries the parser's output lists."""
    return ev(ts, "findings_received", **{
        "pass": pass_, "iteration": iteration, "counts": {}, "findings": findings,
        "open_set": findings, "unproven": [], "closures": [], "closure_rejected": [],
        "unaccounted": [], "downgrades_refused": [], "prose_unfiled": [], **more})


def state(trail: list, completed: list, diff_range: dict | None = None) -> dict:
    """Step 1's r5-state.json, with completed_passes as Step 8 writes them."""
    return {
        "supervisor": "r5-supervise", "version": 2, "target_bead": "opensrm-fx.1",
        "started_at": "2026-11-13T10:00:00+00:00",
        "passes": ["correctness", "edge-cases", "provenance"],
        "advisory_passes": ["clarity", "excellence"], "current_pass": None,
        "completed_passes": [{"name": n, "fix_iterations": k} for n, k in completed],
        "advisory_results": [], "audit_trail": trail, "status": "completed",
        "dry_run": False, "verification_floor": "script",
        "diff_range": diff_range if diff_range is not None else
        {"nthlayer": {"base": BASE, "head": HEAD0, "worktree": None}},
    }


def full_gate() -> dict:
    """A clean gate: correctness finds one IMPORTANT, a fix, a verify that
    closes it; edge-cases and provenance clean; two advisory reads."""
    f = finding("correctness")
    trail = [
        ev("00:00", "pass_started", **{"pass": "correctness"}),
        ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        received("02:40", "correctness", 1, [f], tokens_total=51234),
        ev("03:00", "fixes_applied", **{"pass": "correctness", "statuses": {f["fingerprint"]: "fixed"}}),
        ev("03:05", "tests_passed"),
        ev("03:06", "commit_made", sha=FIX1, repo="nthlayer"),
        ev("03:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 2, "mode": "verify"}),
        received("04:00", "correctness", 2, [], closures=[f["fingerprint"]]),
        ev("04:00", "pass_completed", **{"pass": "correctness", "fix_iterations": 1}),
        ev("04:05", "reviewer_dispatched", **{"pass": "edge-cases", "iteration": 1}),
        received("06:05", "edge-cases", 1, []),
        ev("06:10", "reviewer_dispatched", **{"pass": "provenance", "iteration": 1}),
        received("08:10", "provenance", 1, []),
        ev("08:20", "reviewer_dispatched", **{"pass": "clarity", "iteration": 1, "advisory": True}),
        ev("09:20", "advisory_pass_completed", **{"pass": "clarity", "counts": {},
                                                  "findings": [finding("clarity", "MINOR")],
                                                  "verdict": "PASS WITH FIXES"}),
        ev("09:30", "reviewer_dispatched", **{"pass": "excellence", "iteration": 1, "advisory": True}),
        ev("10:00", "advisory_pass_completed", **{"pass": "excellence", "counts": {},
                                                  "findings": [], "verdict": "SHIP IT"}),
    ]
    return state(trail, [("correctness", 1), ("edge-cases", 0), ("provenance", 0)])


# ------------------------------------------------------------------ build


def test_rounds_follow_the_sequential_gate():
    """Bead 4: each lens iteration is one review or verify round with one
    lens; each fix is a fix round. n counts from 1 in audit order."""
    out = r5_record.build(full_gate())
    kinds = [(r["n"], r["kind"], list(r["lenses"])) for r in out["rounds"]]
    assert kinds == [
        (1, "review", ["correctness"]),
        (2, "fix", []),  # ruling (d)
        (3, "verify", ["correctness"]),
        (4, "review", ["edge_cases"]),  # D4
        (5, "review", ["provenance"]),
        (6, "review", ["clarity"]),
        (7, "review", ["excellence"]),
    ]
    assert r5_record.validate(out) == {"valid": True, "errors": [], "notes": []}


def test_heads_move_with_fix_commits():
    """Round head is the HEAD the round ran against: the range head until a
    fix commit, then that commit. Ruling (c): the top level ends there too."""
    out = r5_record.build(full_gate())
    assert [r["head"] for r in out["rounds"]] == [HEAD0, FIX1, FIX1, FIX1, FIX1, FIX1, FIX1]
    assert out["rounds"][1]["fix"] == {"commit": FIX1, "statuses": {"a" * 16: "fixed"},
                                       "scope_breaches": []}
    assert (out["bead"], out["repo"], out["base"], out["head"]) == (
        "opensrm-fx.1", "nthlayer", BASE, FIX1)
    assert out["branch"] is None  # r5-state records no branch


def test_lens_entry_measures_and_nulls():
    """D2: duration_s from dispatch and receipt timestamps (00:10 to 02:40 is
    150 s); tokens_total recorded when the event carries it; model, tier,
    tokens_in and tokens_out null when unmeasured, never 0."""
    entry = r5_record.build(full_gate())["rounds"][0]["lenses"]["correctness"]
    assert entry["duration_s"] == 150.0
    assert entry["tokens_total"] == 51234
    assert [entry[k] for k in ("model", "tier", "tokens_in", "tokens_out", "skip_rule")] == [None] * 5
    assert entry["mode"] == "review" and entry["status"] == "ok"
    assert entry["findings"] == [finding("correctness")]
    assert entry["closures"] == []


def test_verify_round_carries_closures():
    entry = r5_record.build(full_gate())["rounds"][2]["lenses"]["correctness"]
    assert entry["mode"] == "verify"
    assert entry["closures"] == ["a" * 16]
    assert entry["findings"] == []


def test_measured_fields_on_the_event_are_kept():
    """A supervisor that can measure model, tier and the token split logs
    them on the reviewer events; they pass through unchanged."""
    g = full_gate()
    g["audit_trail"][1].update(model="claude-opus-5-5", tier="deep")
    g["audit_trail"][2].update(tokens_in=40000, tokens_out=11234, duration_s=149.5)
    entry = r5_record.build(g)["rounds"][0]["lenses"]["correctness"]
    assert (entry["model"], entry["tier"], entry["tokens_in"], entry["tokens_out"],
            entry["duration_s"]) == ("claude-opus-5-5", "deep", 40000, 11234, 149.5)


def test_date_only_or_missing_timestamps_give_no_duration():
    """D2: duration only when both stamps carry a time of day."""
    g = full_gate()
    g["audit_trail"][1]["ts"] = "2026-11-13"
    entry = r5_record.build(g)["rounds"][0]["lenses"]["correctness"]
    assert entry["duration_s"] is None
    g = full_gate()
    del g["audit_trail"][1]  # no dispatch logged before the receipt
    rnd = r5_record.build(g)["rounds"][0]
    assert rnd["started"] is None and rnd["lenses"]["correctness"]["duration_s"] is None


def test_receipt_stamped_before_its_dispatch_gives_no_duration():
    """D2: a duration that cannot be measured is null; a clock that runs
    backwards measures nothing, and validate rejects a negative duration."""
    g = full_gate()
    g["audit_trail"][1]["ts"] = "2026-11-13T10:05:00+00:00"  # after the 02:40 receipt
    assert r5_record.build(g)["rounds"][0]["lenses"]["correctness"]["duration_s"] is None


def test_z_suffix_timestamps_are_read():
    g = full_gate()
    g["audit_trail"][1]["ts"] = "2026-11-13T10:00:10Z"
    g["audit_trail"][2]["ts"] = "2026-11-13T10:02:40Z"
    assert r5_record.build(g)["rounds"][0]["lenses"]["correctness"]["duration_s"] == 150.0


def test_mode_without_a_stated_mode():
    """A lens's first reviewer is a review round, a later one a verify round,
    when the dispatch names no mode (older Step 8 dispatches did not)."""
    g = full_gate()
    del g["audit_trail"][6]["mode"]
    assert r5_record.build(g)["rounds"][2]["kind"] == "verify"


def test_fix_in_passing_is_a_fix_round_with_no_verify():
    """Each fix is a fix round (bead 4). fix_iterations counts fix-then-
    re-review loops, so a MINOR fixed in passing leaves it at 0."""
    f = finding("edge_cases", "MINOR")
    trail = [
        ev("00:10", "reviewer_dispatched", **{"pass": "edge-cases", "iteration": 1}),
        received("01:10", "edge-cases", 1, [f]),
        ev("01:20", "fixes_applied", **{"pass": "edge-cases",
                                        "statuses": {f["fingerprint"]: "fixed_in_passing"}}),
        ev("01:30", "commit_made", sha=FIX1, repo="nthlayer"),
        ev("01:30", "pass_completed", **{"pass": "edge-cases", "fix_iterations": 0}),
    ]
    out = r5_record.build(state(trail, [("edge-cases", 0)]))
    assert [r["kind"] for r in out["rounds"]] == ["review", "fix"]
    assert r5_record.validate(out)["valid"]


def test_unavailable_report_is_its_own_round_and_the_retry_keeps_the_mode():
    """Step 4: exit 2 logs reviewer_unavailable and re-dispatches the same
    brief once. Section 6 lens status UNAVAILABLE; no parser output, so the
    lists are null. The retry is still the lens's first review."""
    trail = [
        ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        ev("01:10", "reviewer_unavailable", **{"pass": "correctness", "iteration": 1,
                                               "reason": "last line is not R5-FINDINGS"}),
        ev("01:20", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        received("02:20", "correctness", 1, []),
        ev("02:20", "pass_completed", **{"pass": "correctness", "fix_iterations": 0}),
    ]
    out = r5_record.build(state(trail, [("correctness", 0)]))
    first, retry = out["rounds"]
    assert first["kind"] == retry["kind"] == "review"
    assert first["lenses"]["correctness"]["status"] == "UNAVAILABLE"
    assert all(first["lenses"]["correctness"][k] is None for k in r5_record.PARSER_LISTS)
    assert first["lenses"]["correctness"]["duration_s"] == 60.0
    assert retry["lenses"]["correctness"]["status"] == "ok"
    assert r5_record.validate(out)["valid"]


def test_pre_parser_records_carry_null_lists():
    """Ruling (a): a record from before the parser holds counts, not
    findings: null (not recorded), never [] (none found)."""
    trail = [
        ev("00:10", "reviewer_dispatched", **{"pass": "correctness"}),
        ev("01:10", "findings_received", **{"pass": "correctness",
                                            "counts": {"critical": 1, "important": 0, "minor": 0}}),
        ev("01:10", "pass_completed", **{"pass": "correctness", "fix_iterations": 0}),
    ]
    entry = r5_record.build(state(trail, [("correctness", 0)]))["rounds"][0]["lenses"]["correctness"]
    assert all(entry[k] is None for k in r5_record.PARSER_LISTS)


def test_multi_repo_gate_leaves_top_level_and_multi_commit_fix_null():
    """D3: repo, base and head only when diff_range names one repo. Ruling
    (b): section 6 has one commit per fix round; two have no single one."""
    g = full_gate()
    g["diff_range"]["nthlayer-common"] = {"base": "5555555", "head": "6666666", "worktree": None}
    g["audit_trail"].insert(6, ev("03:07", "commit_made", sha=FIX2, repo="nthlayer-common"))
    out = r5_record.build(g)
    assert (out["repo"], out["base"], out["head"]) == (None, None, None)
    fix = out["rounds"][1]
    assert fix["fix"]["commit"] is None and fix["head"] is None
    report = r5_record.validate(out)
    assert report["valid"]
    assert any(n.startswith("multi_repo") for n in report["notes"])
    assert any("no single commit" in n for n in report["notes"])


def test_build_keeps_every_existing_field_and_does_not_touch_its_input():
    """Bead 4: existing fields are kept. Rob's condition on E1: re-run safe,
    so the input is never edited."""
    g = full_gate()
    before = copy.deepcopy(g)
    out = r5_record.build(g)
    assert g == before
    for key, value in before.items():
        assert out[key] == value


def test_build_is_a_re_derivation():
    """Re-running over a built record, or one carrying stale derived keys,
    gives the same record: a rename in the shape is a re-derivation."""
    once = r5_record.build(full_gate())
    assert r5_record.build(once) == once
    stale = dict(full_gate(), rounds=[{"n": 9}], head="dead000", bead="other")
    assert r5_record.build(stale) == once


# --------------------------------------------------------------- refusals


def _refusal(record) -> str:
    with pytest.raises(r5_record.BuildRefused) as caught:
        r5_record.build(record)
    return caught.value.reason


REFUSAL_CASES = {
    "not_an_object": lambda: [],
    "no_audit_trail": lambda: {k: v for k, v in full_gate().items() if k != "audit_trail"},
    "bad_event": lambda: dict(full_gate(), audit_trail=[{"ts": "x"}]),
    "unknown_lens": lambda: state([ev("00:10", "reviewer_dispatched", **{"pass": "clarity+edge-cases"})], []),
    "receipt_without_pass": lambda: state([ev("00:10", "findings_received", counts={})], []),
    "bad_parser_field": lambda: state([received("00:10", "correctness", 1, [], closures="none")], []),
    "pass_without_review": lambda: state(
        [ev("00:10", "pass_completed", **{"pass": "correctness", "fix_iterations": 1})],
        [("correctness", 1)]),
    "verify_count_mismatch": lambda: dict(
        full_gate(), completed_passes=[{"name": "correctness", "fix_iterations": 2}]),
}


@pytest.mark.parametrize("reason", sorted(REFUSAL_CASES))
def test_each_refusal(reason):
    assert _refusal(REFUSAL_CASES[reason]()) == reason


def test_every_refusal_reason_has_a_case():
    # The parametrise list above must not shrink silently below the set.
    assert set(REFUSAL_CASES) == set(r5_record.REFUSALS)
    assert len(REFUSAL_CASES) >= 8


# --------------------------------------------------------------- validate


def _errors(mutate) -> list:
    out = r5_record.build(full_gate())
    mutate(out)
    return r5_record.validate(out)["errors"]


@pytest.mark.parametrize("name, mutate, needle", [
    ("two lenses in a review round",
     lambda o: o["rounds"][0]["lenses"].update(clarity=o["rounds"][0]["lenses"]["correctness"]),
     "has 2 lenses"),
    ("a fix round with a lens",
     lambda o: o["rounds"][1]["lenses"].update(correctness={}), "dispatches no lens"),
    ("unknown kind", lambda o: o["rounds"][0].update(kind="merge"), "kind"),
    ("n out of order", lambda o: o["rounds"][1].update(n=5), "expected 2"),
    ("mode differs from kind",
     lambda o: o["rounds"][0]["lenses"]["correctness"].update(mode="verify"), "does not match"),
    ("negative tokens",
     lambda o: o["rounds"][0]["lenses"]["correctness"].update(tokens_in=-1), "tokens_in"),
    ("bool is not a count",
     lambda o: o["rounds"][0]["lenses"]["correctness"].update(tokens_total=True), "tokens_total"),
    ("unknown lens status",
     lambda o: o["rounds"][0]["lenses"]["correctness"].update(status="FAILED"), "status"),
    ("missing parser list",
     lambda o: o["rounds"][0]["lenses"]["correctness"].pop("unaccounted"), "unaccounted: missing"),
    ("unknown fixer status",
     lambda o: o["rounds"][1]["fix"]["statuses"].update(x="maybe"), "statuses"),
    ("fix object on a review round",
     lambda o: o["rounds"][0].update(fix={"commit": None}), "fix object"),
    ("ended before started",
     lambda o: o["rounds"][0].update(ended="2026-11-13T09:00:00+00:00"), "ended before"),
    ("schema lens spelling",
     lambda o: o["rounds"][3].update(lenses={"edge-cases": o["rounds"][3]["lenses"]["edge_cases"]}),
     "lens 'edge-cases'"),
    ("verdict state", lambda o: o.update(verdict={"state": "PASSED"}), "verdict.state"),
    ("rounds missing", lambda o: o.pop("rounds"), "rounds: missing"),
    ("repo set on a multi-repo gate",
     lambda o: o["diff_range"].update(other={"base": "a", "head": "b"}), "multi-repo"),
])
def test_validate_rejects(name, mutate, needle):
    errors = _errors(mutate)
    assert any(needle in e for e in errors), (name, errors)


def test_validate_accepts_zero_and_null_measurements():
    """D2: 0 is a measurement, null is none; both are valid."""
    def zero(o):
        o["rounds"][0]["lenses"]["correctness"].update(tokens_in=0, tokens_out=0, duration_s=0)
    assert _errors(zero) == []


def test_validate_accepts_a_section_6_verdict():
    """Section 6 verdict block (bead 6 writes it); its state is checked."""
    assert _errors(lambda o: o.update(verdict={"state": "CLEAN", "tree_sha": "t"})) == []


# ------------------------------------------------------------------ sweep


def test_sweep_over_the_baseline_fixtures(tmp_path):
    """Each of r5_baseline's fixtures (one per archive pattern) builds into
    a valid record or refuses with a named reason; none is invalid."""
    out = r5_record.sweep(HERE / "fixtures" / "r5-baseline")
    assert out["ok"] and not out["invalid"] and not out["unreadable"]
    assert len(out["built"]) + len(out["refused"]) == 14
    assert set(out["refused"].values()) <= set(r5_record.REFUSALS)
    # v1 records logged pass summaries only, no reviewer events.
    assert out["refused"]["r5-state-fx-v1-totals-only-completed.json"] == "pass_without_review"
    # a combined pass is not one section 6 lens.
    assert out["refused"]["r5-state-fx-combined-pass-completed.json"] == "unknown_lens"
    assert "r5-state-fx-clarity-advisory-completed.json" in out["built"]


def test_sweep_reports_invalid_and_unreadable(tmp_path):
    (tmp_path / "r5-state-good-completed.json").write_text(json.dumps(full_gate()))
    (tmp_path / "r5-state-bad-completed.json").write_text("{not json")
    out = r5_record.sweep(tmp_path)
    assert out["built"] == ["r5-state-good-completed.json"]
    assert "r5-state-bad-completed.json" in out["unreadable"] and not out["ok"]


def test_sweep_of_an_empty_directory_is_not_ok(tmp_path):
    # No archive found must not read as a clean sweep.
    assert r5_record.sweep(tmp_path)["ok"] is False


# -------------------------------------------------------------------- CLI


def _cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_cli_exit_codes(tmp_path):
    good = tmp_path / "s.json"
    good.write_text(json.dumps(full_gate()))
    built = _cli("build", str(good))
    assert built.returncode == 0
    record = tmp_path / "r.json"
    record.write_text(built.stdout)
    assert _cli("validate", str(record)).returncode == 0
    assert json.loads(_cli("validate", str(record)).stdout)["valid"] is True

    refused = tmp_path / "x.json"
    refused.write_text(json.dumps([]))
    assert _cli("build", str(refused)).returncode == 2
    assert _cli("validate", str(good)).returncode == 2  # no rounds yet
    assert _cli("build").returncode == 1
    assert _cli("build", str(tmp_path / "missing.json")).returncode == 1
    assert _cli("sweep", str(good)).returncode == 1  # not a directory
    assert _cli("sweep", str(tmp_path / "empty-dir-missing")).returncode == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _cli("sweep", str(empty)).returncode == 2
