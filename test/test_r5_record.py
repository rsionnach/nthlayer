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

The field rules the script applies (opensrm-6kqs.4; the stall and refusal
rules are opensrm-6kqs.14's) are named where they set an expected value:
measured fields null when unmeasured, duration from timestamps; top-level
repo, base and head only for one repo; the lens key edge_cases; null for
parser lists a record never carried; no single commit, null; the top-level
head is where the gate ended; a fix round dispatches no lens.

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
        (2, "fix", []),  # a fix round dispatches no lens
        (3, "verify", ["correctness"]),
        (4, "review", ["edge_cases"]),  # the schema's lens key
        (5, "review", ["provenance"]),
        (6, "review", ["clarity"]),
        (7, "review", ["excellence"]),
    ]
    assert r5_record.validate(out) == {"valid": True, "errors": [], "notes": []}


def test_heads_move_with_fix_commits():
    """Round head is the HEAD the round ran against: the range head until a
    fix commit, then that commit. The top level ends there too."""
    out = r5_record.build(full_gate())
    assert [r["head"] for r in out["rounds"]] == [HEAD0, FIX1, FIX1, FIX1, FIX1, FIX1, FIX1]
    assert out["rounds"][1]["fix"] == {"commit": FIX1, "statuses": {"a" * 16: "fixed"},
                                       "scope_breaches": []}
    assert (out["bead"], out["repo"], out["base"], out["head"]) == (
        "opensrm-fx.1", "nthlayer", BASE, FIX1)
    assert out["branch"] is None  # r5-state records no branch


def test_lens_entry_measures_and_nulls():
    """duration_s from dispatch and receipt timestamps (00:10 to 02:40 is
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
    assert (entry["model"], entry["tier"], entry["tokens_in"], entry["tokens_out"]) == (
        "claude-opus-5-5", "deep", 40000, 11234)
    # The timestamps (150 s) come before a duration the event states.
    assert entry["duration_s"] == 150.0


def test_a_stated_duration_is_the_fallback_when_no_stamps_measure_one():
    """Timestamps first, then the event's own duration_s, then null."""
    g = full_gate()
    del g["audit_trail"][1]  # no dispatch stamp
    g["audit_trail"][1]["duration_s"] = 149.5
    assert r5_record.build(g)["rounds"][0]["lenses"]["correctness"]["duration_s"] == 149.5


def test_date_only_or_missing_timestamps_give_no_duration():
    """Duration only when both stamps carry a time of day."""
    g = full_gate()
    g["audit_trail"][1]["ts"] = "2026-11-13"
    entry = r5_record.build(g)["rounds"][0]["lenses"]["correctness"]
    assert entry["duration_s"] is None
    g = full_gate()
    del g["audit_trail"][1]  # no dispatch logged before the receipt
    rnd = r5_record.build(g)["rounds"][0]
    assert rnd["started"] is None and rnd["lenses"]["correctness"]["duration_s"] is None


def test_receipt_stamped_before_its_dispatch_gives_no_duration():
    """A duration that cannot be measured is null; a clock that runs
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
    """A lens's first reviewer is a review round, a later one a verify round
    (older Step 8 dispatches name no mode)."""
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
    """A record from before the parser holds counts, not
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
    """repo, base and head only when diff_range names one repo. Section 6
    has one commit per fix round; two have no single one."""
    g = full_gate()
    g["diff_range"]["nthlayer-common"] = {"base": "5555555", "head": "6666666", "worktree": None}
    g["audit_trail"].insert(6, ev("03:07", "commit_made", sha=FIX2, repo="nthlayer-common"))
    out = r5_record.build(g)
    assert (out["repo"], out["base"], out["head"]) == (None, None, None)
    fix = out["rounds"][1]
    # No single commit. And no single tree: rounds over several repos carry
    # no head, as the top level has none.
    assert fix["fix"]["commit"] is None
    assert all(r["head"] is None for r in out["rounds"])
    report = r5_record.validate(out)
    assert report["valid"]
    assert any(n.startswith("multi_repo") for n in report["notes"])
    assert any("no single commit" in n for n in report["notes"])


def test_commit_after_a_review_with_no_fixes_applied_is_a_fix_round():
    """Each fix is a fix round (bead 4). Supervisors before 6kqs.3 logged
    findings_received -> commit_made -> reviewer_dispatched with no
    fixes_applied (opensrm-6kqs.1's record): the commit is that review's fix,
    and the gate's head moves to it."""
    trail = [
        ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        ev("01:10", "findings_received", **{"pass": "correctness", "iteration": 1,
                                            "counts": {"critical": 0, "important": 1, "minor": 0}}),
        ev("01:30", "commit_made", sha=FIX1, repo="nthlayer"),
        ev("01:40", "reviewer_dispatched", **{"pass": "correctness", "iteration": 2}),
        ev("02:40", "findings_received", **{"pass": "correctness", "iteration": 2, "counts": {}}),
        ev("02:40", "pass_completed", **{"pass": "correctness", "fix_iterations": 1}),
    ]
    out = r5_record.build(state(trail, [("correctness", 1)]))
    assert [r["kind"] for r in out["rounds"]] == ["review", "fix", "verify"]
    assert out["rounds"][1]["fix"] == {"commit": FIX1, "statuses": {}, "scope_breaches": []}
    assert [r["head"] for r in out["rounds"]] == [HEAD0, FIX1, FIX1]
    assert out["head"] == FIX1


def test_a_diff_range_head_moved_to_the_end_is_not_the_start():
    """Some supervisors moved diff_range's head to the last fix commit when the
    gate ended (3ntg, ln7w). A round before that commit did not run against
    it: its head is unknown, null, not a commit from the future."""
    g = full_gate()
    g["diff_range"]["nthlayer"]["head"] = FIX1  # the gate's own fix commit
    out = r5_record.build(g)
    assert out["rounds"][0]["head"] is None
    assert [r["head"] for r in out["rounds"][1:]] == [FIX1] * 6
    assert out["head"] == FIX1
    # Abbreviated either way round, as archives record them.
    g["diff_range"]["nthlayer"]["head"] = FIX1[:5]
    assert r5_record.build(g)["rounds"][0]["head"] is None


def test_a_diff_range_head_committed_before_the_first_review_is_the_start():
    """The implementation commit, logged before any review, is the range the
    first reviewer read: the start head, kept."""
    g = full_gate()
    g["diff_range"]["nthlayer"]["head"] = HEAD0
    g["audit_trail"].insert(0, ev("00:00", "commit_made", sha=HEAD0, repo="nthlayer"))
    assert r5_record.build(g)["rounds"][0]["head"] == HEAD0


def test_a_commit_before_any_review_is_not_a_round():
    """The implementation commit lands before the first reviewer; it is the
    range the gate reviews, not a fix."""
    trail = [
        ev("00:05", "commit_made", sha=FIX1, repo="nthlayer"),
        ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        received("01:10", "correctness", 1, []),
        ev("01:10", "pass_completed", **{"pass": "correctness", "fix_iterations": 0}),
    ]
    out = r5_record.build(state(trail, [("correctness", 0)]))
    assert [r["kind"] for r in out["rounds"]] == ["review"]


def test_single_repo_multi_commit_fix_ends_the_gate_at_its_last_commit():
    """The top-level head is where the gate ended, also when the last fix
    round has two commits (and so no single fix.commit)."""
    g = full_gate()
    g["audit_trail"].insert(6, ev("03:07", "commit_made", sha=FIX2, repo="nthlayer"))
    out = r5_record.build(g)
    assert out["rounds"][1]["fix"]["commit"] is None
    assert out["head"] == FIX2


def test_build_keeps_every_existing_field_and_does_not_touch_its_input():
    """Bead 4: existing fields are kept. Erratum E1: re-run safe,
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
    # 6kqs.2 logged sha as a JSON number: unreadable, so the head is unknown.
    "bad_commit_event": lambda: _with_commit(sha=5859972),
    "bad_summary": lambda: dict(full_gate(), completed_passes=5),
    # A reviewer dispatched and never answered: dropping it would record a
    # gate with one review fewer than it ran.
    "dispatch_unanswered": lambda: dict(full_gate(), audit_trail=full_gate()["audit_trail"] + [
        ev("11:00", "reviewer_dispatched", **{"pass": "provenance", "iteration": 2})]),
    # opensrm-6kqs.14: after the cutoff a supervisor_blocked re-send is ambiguous.
    "blocked_resend_ambiguous": lambda: _after_cutoff([PAUSE_AFTER_CUTOFF]),
    # opensrm-6kqs.14, with TABLE_FOR below: history only, and checked.
    "table_row_after_cutoff": lambda: _after_cutoff([]),
    "table_row_unmatched": lambda: full_gate(),
    # opensrm-6kqs.5: round 0's event, as r5_record's docstring defines it.
    "bad_preflight_event": lambda: _gate_after(round0(results={"lint": {"ok": "yes"}})),
    "preflight_not_first": lambda: dict(full_gate(), audit_trail=full_gate()["audit_trail"] + [
        round0("11:00")]),
    "preflight_verdict_mismatch": lambda: _gate_after(round0(verdict="PREFLIGHT_FAILED")),
    "round_after_preflight_failed": lambda: _gate_after(round0(suite_ok=False,
                                                               verdict="PREFLIGHT_FAILED")),
}
# The KNOWN_REFUSED a case is built against, where it needs one.
TABLE_FOR = {
    "table_row_after_cutoff": {("opensrm-fx.1", "correctness", "2026-11-13T22:10:00+00:00"):
                               {"reason": "hook refused the launch", "evidence": "synthetic"}},
    "table_row_unmatched": {("opensrm-fx.1", "correctness", "2026-11-13T10:00:10+00:00"):
                            {"reason": "hook refused the launch", "evidence": "synthetic"}},
}


def _with_commit(**fields) -> dict:
    g = full_gate()
    g["audit_trail"][5] = ev("03:06", "commit_made", repo="nthlayer", **fields)
    return g


@pytest.mark.parametrize("fields", [
    {"sha": None, "shas": "3333333"},  # a string, not a list
    {"shas": [3333333]},  # a list holding a number
    {"shas": {"nthlayer": 3333333}},  # a map to a number
], ids=["shas-string", "shas-list-number", "shas-map-number"])
def test_unreadable_commit_shapes_are_refused(fields):
    assert _refusal(_with_commit(**fields)) == "bad_commit_event"


def test_a_per_repo_map_of_shas_names_its_commits_not_its_repos():
    """7zpz-pinrepos logs shas as {repo: sha}; the commits are the values."""
    out = r5_record.build(_with_commit(shas={"nthlayer": FIX1}))
    assert out["rounds"][1]["fix"]["commit"] == FIX1
    assert out["rounds"][2]["head"] == FIX1


@pytest.mark.parametrize("reason", sorted(REFUSAL_CASES))
def test_each_refusal(reason, monkeypatch):
    if reason in TABLE_FOR:
        monkeypatch.setattr(r5_record, "KNOWN_REFUSED", TABLE_FOR[reason])
    assert _refusal(REFUSAL_CASES[reason]()) == reason


def test_every_refusal_reason_has_a_case():
    # The parametrise list above must not shrink silently below the set.
    assert set(REFUSAL_CASES) == set(r5_record.REFUSALS)
    assert len(REFUSAL_CASES) >= 18


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
    """0 is a measurement, null is none; both are valid."""
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


def test_sweep_reports_a_crash_and_carries_on(tmp_path, monkeypatch):
    """One archive that crashes build is reported invalid; the others are
    still swept, so a bad file cannot hide the rest of the archive."""
    for name in ("a", "b"):
        (tmp_path / f"r5-state-{name}-completed.json").write_text(json.dumps(full_gate()))
    real = r5_record.build

    def flaky(record):
        if record is not None and record.get("target_bead") == "boom":
            raise TypeError("boom")
        return real(record)

    (tmp_path / "r5-state-a-completed.json").write_text(json.dumps(dict(full_gate(), target_bead="boom")))
    monkeypatch.setattr(r5_record, "build", flaky)
    out = r5_record.sweep(tmp_path)
    assert out["built"] == ["r5-state-b-completed.json"]
    assert out["invalid"]["r5-state-a-completed.json"][0].startswith("build crashed: TypeError")
    assert out["ok"] is False


def test_revision_expressions_are_not_commits():
    """jmy.19's diff_range base is "65ba2bc^"; "HEAD" moves with the branch.
    Neither names a commit, so the record holds null, not the expression."""
    g = full_gate()
    g["diff_range"]["nthlayer"].update(base="65ba2bc^", head="HEAD")
    out = r5_record.build(g)
    assert out["base"] is None
    assert out["rounds"][0]["head"] is None  # the start head is not a commit
    assert out["head"] == FIX1  # the gate still ends at its fix commit


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


# ------------------------------------------------ provenance pass additions
# Each case below is a shape a real archive or a supervisor step writes, or a
# section 6 rule, named in its docstring; the provenance pass (6kqs.4 gate)
# found the code paths they cover untested.


def test_a_dispatch_head_is_the_round_head():
    """iiay, f751, wo62-4-22 and wo62-4-6 log the HEAD a reviewer read on
    reviewer_dispatched (iiay: head "baff067" after commit baff067...). That
    HEAD is the round's, not the running head."""
    g = full_gate()
    g["audit_trail"][9]["head"] = "abcdef1"  # the edge-cases dispatch
    rounds = r5_record.build(g)["rounds"]
    assert rounds[3]["head"] == "abcdef1"
    assert rounds[4]["head"] == FIX1  # the next round falls back to the running head


def test_fix_dispatched_opens_the_fix_round():
    """7zpz-core logs fix_dispatched (to the implementer) before
    fixes_applied: one fix round, started at the dispatch."""
    g = full_gate()
    g["audit_trail"].insert(3, ev("02:50", "fix_dispatched", **{"pass": "correctness", "to": "implementer"}))
    rounds = r5_record.build(g)["rounds"]
    assert [r["kind"] for r in rounds[:3]] == ["review", "fix", "verify"]
    assert rounds[1]["started"].endswith("10:02:50+00:00")


def test_a_fix_round_spans_its_events():
    """A fix round starts at fixes_applied (03:00) and ends at its last event,
    the commit (03:06)."""
    fix = r5_record.build(full_gate())["rounds"][1]
    assert (fix["started"], fix["ended"]) == ("2026-11-13T10:03:00+00:00", "2026-11-13T10:03:06+00:00")


def test_a_fix_round_with_no_commit_ends_at_its_last_fixes_applied():
    g = full_gate()
    del g["audit_trail"][5]  # no commit_made (a dry run logs none)
    g["audit_trail"].insert(4, ev("03:04", "fixes_applied", **{"pass": "correctness", "statuses": {}}))
    fix = r5_record.build(g)["rounds"][1]
    assert fix["ended"] == "2026-11-13T10:03:04+00:00" and fix["fix"]["commit"] is None


def test_an_unavailable_verify_is_not_a_verify():
    """Step 4: an UNAVAILABLE report is retried with the same brief, so an
    unavailable verify followed by its retry is one re-review against
    fix_iterations 1, not two."""
    g = full_gate()
    g["audit_trail"].insert(7, ev("03:40", "reviewer_unavailable", **{"pass": "correctness", "iteration": 2}))
    g["audit_trail"].insert(8, ev("03:45", "reviewer_dispatched", **{"pass": "correctness", "iteration": 2, "mode": "verify"}))
    out = r5_record.build(g)  # completed_passes says fix_iterations 1
    kinds = [(r["kind"], next(iter(r["lenses"].values()))["status"]) for r in out["rounds"][:4] if r["lenses"]]
    assert kinds == [("review", "ok"), ("verify", "UNAVAILABLE"), ("verify", "ok")]


def test_a_dispatch_mode_is_not_read():
    """Step 8 re-dispatches only in verify mode, and the archives that state a
    mode state "verify" (2 of 96): the kind comes from order, never from a
    field no step writes differently."""
    g = full_gate()
    g["audit_trail"][6]["mode"] = "review"
    assert r5_record.build(g)["rounds"][2]["kind"] == "verify"


@pytest.mark.parametrize("fields, key", [
    ({"duration_s": -5}, "duration_s"),
    ({"tokens_total": -1}, "tokens_total"),
    ({"tokens_in": True}, "tokens_in"),
    ({"tokens_out": 1.5}, "tokens_out"),
    ({"model": 42}, "model"),
], ids=["negative-duration", "negative-tokens", "bool-tokens", "float-tokens", "non-string-model"])
def test_unmeasurable_values_become_null(fields, key):
    """A value that is not a measurement is null, never kept or zeroed.
    (duration_s here has no dispatch stamp to come from first.)"""
    g = full_gate()
    del g["audit_trail"][1]
    g["audit_trail"][1].update(fields)
    assert r5_record.build(g)["rounds"][0]["lenses"]["correctness"][key] is None


def test_the_receipt_wins_over_the_dispatch_for_measurements():
    """The receipt is later than the dispatch, so its value stands."""
    g = full_gate()
    g["audit_trail"][1]["model"] = "dispatch-model"
    g["audit_trail"][2]["model"] = "receipt-model"
    assert r5_record.build(g)["rounds"][0]["lenses"]["correctness"]["model"] == "receipt-model"


def test_nothing_writes_a_status_skip_rule_or_branch():
    """No supervisor step writes status or skip_rule on an event, or a branch
    into r5-state (0 of 96 archives): the record carries the defaults."""
    g = full_gate()
    g["audit_trail"][2].update(status="skipped", skip_rule="docs-only")
    g["branch_name"] = "round-record"
    out = r5_record.build(g)
    entry = out["rounds"][0]["lenses"]["correctness"]
    assert (entry["status"], entry["skip_rule"], out["branch"]) == ("ok", None, None)


@pytest.mark.parametrize("value, kept", [
    ("abc", False), ("abcd", True), ("a" * 40, True), ("a" * 41, False),
], ids=["3-hex", "4-hex", "40-hex", "41-hex"])
def test_sha_length_bounds(value, kept):
    """git abbreviates to at least 4 hex digits; a full SHA-1 is 40."""
    g = full_gate()
    g["diff_range"]["nthlayer"]["base"] = value
    assert r5_record.build(g)["base"] == (value if kept else None)


@pytest.mark.parametrize("name, mutate, needle", [
    ("bead not a string", lambda o: o.update(bead=7), "bead: not a string"),
    ("round head not a string", lambda o: o["rounds"][0].update(head=7), "head: not a string"),
    ("round started not a string", lambda o: o["rounds"][0].update(started=7), "started: not a string"),
    ("fix commit not a string", lambda o: o["rounds"][1]["fix"].update(commit=7), "fix.commit"),
    ("scope_breaches not a list", lambda o: o["rounds"][1]["fix"].update(scope_breaches={}), "scope_breaches"),
    ("fix round without fix", lambda o: o["rounds"][1].pop("fix"), "fix: missing"),
    ("round not an object", lambda o: o["rounds"].__setitem__(0, "r"), "not an object"),
    ("lens entry not an object",
     lambda o: o["rounds"][0]["lenses"].update(correctness="x"), "correctness: not an object"),
    ("model not a string",
     lambda o: o["rounds"][0]["lenses"]["correctness"].update(model=1), "model: not a string"),
    ("negative duration",
     lambda o: o["rounds"][0]["lenses"]["correctness"].update(duration_s=-1), "duration_s"),
    ("parser list not a list",
     lambda o: o["rounds"][0]["lenses"]["correctness"].update(closures="x"), "closures: not a list"),
    ("measured field missing",
     lambda o: o["rounds"][0]["lenses"]["correctness"].pop("tokens_total"), "tokens_total: missing"),
])
def test_validate_rejects_each_shape_break(name, mutate, needle):
    """Section 6's round-record shape, one break per check."""
    errors = _errors(mutate)
    assert any(needle in e for e in errors), (name, errors)


def test_validate_rejects_a_record_that_is_not_an_object():
    assert r5_record.validate([]) == {"valid": False, "errors": ["not a JSON object"], "notes": []}


def test_sweep_does_not_count_an_invalid_record_as_built(tmp_path, monkeypatch):
    """A record that builds but fails validate is invalid, and the sweep is
    not ok: that is the archive-wide check a shape change relies on."""
    (tmp_path / "r5-state-x-completed.json").write_text(json.dumps(full_gate()))
    real = r5_record.build
    monkeypatch.setattr(r5_record, "build", lambda rec: dict(real(rec), rounds="broken"))
    out = r5_record.sweep(tmp_path)
    assert out["built"] == [] and "r5-state-x-completed.json" in out["invalid"]
    assert out["ok"] is False


# ------------------------------------------------------- re-sent dispatches
# A reviewer_dispatched for a lens whose last dispatch has no receipt is a
# re-send (opensrm-6kqs.14). The shapes: SKILL.md Step 3
# appends reviewer_dispatched right after the launch and, if the hook refuses
# it anyway, reviewer_dispatch_blocked {ts, event, pass, iteration, reason}
# (opensrm-ir5m and 6kqs.2 log it so); Step 4 appends the receipt. Archives
# 6kqs.2 (reviewer_stalled), bnal (reviewer_dispatch_failed) and t4rd
# (provenance_checks_skipped) re-send after a reviewer that ran and stalled.
# supervisor_blocked means the run paused for the user, not a refusal
# (opensrm-6kqs.14): wo62-4-2 logs one after a real stall that was then
# re-sent; 6kqs.4 and wo62-4-1 log one after a hook refusal, and those two
# are rows of the history-only KNOWN_REFUSED table instead.


def _resent(between: list, iteration: int = 1, fixed: bool = False) -> dict:
    trail = [ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1})]
    if fixed:
        trail += [received("01:00", "correctness", 1, [finding("correctness")]),
                  ev("01:30", "fixes_applied", **{"pass": "correctness"}),
                  ev("01:40", "commit_made", sha=FIX1, repo="nthlayer"),
                  ev("02:00", "reviewer_dispatched", **{"pass": "correctness", "iteration": 2})]
    trail += [*between,
              ev("12:00", "reviewer_dispatched", **{"pass": "correctness", "iteration": iteration}),
              received("14:00", "correctness", iteration, []),
              ev("14:00", "pass_completed", **{"pass": "correctness", "fix_iterations": int(fixed)})]
    return r5_record.build(state(trail, [("correctness", int(fixed))]))


def test_a_stalled_dispatch_re_sent_is_an_unavailable_round():
    """No block event between: the first reviewer ran and gave no answer. It
    is its own round, UNAVAILABLE with null lists, from the stalled dispatch
    to the re-send; duration_s is null (the wait is not the reviewer's
    measured time). It is not the first review, so the re-send is still a
    review, and fix_iterations 0 still matches."""
    out = _resent([ev("10:10", "reviewer_stalled", **{"pass": "correctness", "iteration": 1})])
    stall, answer = out["rounds"]
    assert (stall["kind"], answer["kind"]) == ("review", "review")
    entry = stall["lenses"]["correctness"]
    assert entry["status"] == "UNAVAILABLE"
    assert all(entry[k] is None for k in r5_record.PARSER_LISTS)
    assert entry["duration_s"] is None
    assert (stall["started"], stall["ended"]) == ("2026-11-13T10:00:10+00:00",
                                                  "2026-11-13T10:12:00+00:00")
    assert answer["lenses"]["correctness"]["status"] == "ok"
    assert answer["started"] == "2026-11-13T10:12:00+00:00"
    assert r5_record.lens_tally(out["rounds"])["correctness"] == {"review": 1, "verify": 0, "fix": 0}
    assert r5_record.validate(out)["valid"]


def test_a_stalled_verify_re_sent_is_an_unavailable_verify():
    out = _resent([], iteration=2, fixed=True)
    kinds = [(r["kind"], next(iter(r["lenses"].values()))["status"]) for r in out["rounds"] if r["lenses"]]
    assert kinds == [("review", "ok"), ("verify", "UNAVAILABLE"), ("verify", "ok")]


@pytest.mark.parametrize("block", [
    {"event": "reviewer_dispatch_blocked", "pass": "correctness", "iteration": 1,
     "reason": "parallel-block hook refused the launch"},
    {"event": "reviewer_dispatch_blocked", "reason": "lock held by another session"},
], ids=["for-the-pass", "no-pass"])
def test_a_hook_refused_dispatch_re_sent_is_replaced(block):
    """The event rule (opensrm-6kqs.14): a reviewer_dispatch_blocked for the
    pass (or naming none) between: no reviewer ran, so the re-send replaces
    the dispatch and the gate has one round."""
    out = _resent([ev("00:40", **block)])
    assert [(r["kind"], r["started"]) for r in out["rounds"]] == [
        ("review", "2026-11-13T10:12:00+00:00")]
    assert r5_record.refused_dispatches(out) == [
        ("correctness", "2026-11-13T10:00:10+00:00", "event")]


@pytest.mark.parametrize("paused", [
    {"pass": "correctness", "reason": "two consecutive reviewer stalls; escalated to the user"},
    {"reason": "two consecutive reviewer stalls; escalated to the user"},
], ids=["for-the-pass", "no-pass"])
def test_a_supervisor_blocked_re_send_before_the_cutoff_is_a_stall(paused):
    """opensrm-6kqs.14: before STEP3_CUTOFF, a supervisor_blocked between a
    dispatch and its re-send, with no reviewer_dispatch_blocked and no table
    row, leaves a stall (wo62-4-2: dispatched 01:41:08, supervisor_blocked
    03:53:55 for two consecutive reviewer stalls, escalated to the user, re-sent
    15:09:30)."""
    out = _resent([ev("05:00", "supervisor_blocked", **paused)])
    assert [r["lenses"]["correctness"]["status"] for r in out["rounds"]] == ["UNAVAILABLE", "ok"]
    assert out["rounds"][0]["started"] == "2026-11-13T10:00:10+00:00"
    assert r5_record.refused_dispatches(out) == []


def _after_cutoff(between: list) -> dict:
    """A gate started at STEP3_CUTOFF (the rule is 'at or after') whose
    correctness dispatch is re-sent with ``between`` in the gap."""
    trail = [{"ts": "2026-11-13T22:10:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             *between,
             {"ts": "2026-11-13T22:20:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             dict(received("00:00", "correctness", 1, []), ts="2026-11-13T22:25:00+00:00")]
    return dict(state(trail, [("correctness", 0)]), started_at=r5_record.STEP3_CUTOFF)


PAUSE_AFTER_CUTOFF = {"ts": "2026-11-13T22:15:00+00:00", "event": "supervisor_blocked",
                      "pass": "correctness", "reason": "reviewer stalled; escalated to the user"}


def test_a_supervisor_blocked_re_send_after_the_cutoff_is_refused():
    """opensrm-6kqs.14: from the cutoff on, Step 3 logs reviewer_dispatched
    after the launch, so a refusal leaves no dispatch; a supervisor_blocked
    between a dispatch and its re-send with no reviewer_dispatch_blocked is
    ambiguous, and build refuses rather than guess."""
    assert _refusal(_after_cutoff([PAUSE_AFTER_CUTOFF])) == "blocked_resend_ambiguous"


# opensrm-6kqs.14 and r5-supervise Step 3: from STEP3_CUTOFF on, Step 3
# logs reviewer_dispatched only after the launch returns, so a logged dispatch
# ran, and a reviewer_dispatch_blocked records a launch that never happened.
BLOCK_AFTER_CUTOFF = {"ts": "2026-11-13T22:15:01+00:00", "event": "reviewer_dispatch_blocked",
                      "pass": "correctness", "iteration": 1,
                      "reason": "parallel-block hook refused the launch"}


def _stall_then_ok(out: dict) -> None:
    assert [(r["kind"], r["lenses"]["correctness"]["status"]) for r in out["rounds"]] == [
        ("review", "UNAVAILABLE"), ("review", "ok")]
    assert out["rounds"][0]["started"] == "2026-11-13T22:10:00+00:00"
    assert r5_record.refused_dispatches(out) == []
    assert r5_record.validate(out)["valid"]


def test_after_the_cutoff_reviewer_dispatch_blocked_settles_it():
    """opensrm-6kqs.14: a reviewer_dispatch_blocked beside a supervisor_blocked
    settles the ambiguity (the refusal was logged as one, the pause is a real
    pause), and the logged dispatch ran either way: a stall, not a refusal."""
    _stall_then_ok(r5_record.build(_after_cutoff([PAUSE_AFTER_CUTOFF, BLOCK_AFTER_CUTOFF])))


def test_after_the_cutoff_a_blocked_re_send_of_a_stalled_reviewer_is_a_stall():
    """opensrm-6kqs.14 and SKILL.md Step 3: dispatch (logged after its launch,
    so it ran) -> reviewer_dispatch_blocked (the hook refused the re-send,
    since reviewer_dispatched was still the latest event) -> re-send ->
    findings. The block never refuses the logged dispatch: it is an
    UNAVAILABLE stall round, and no dispatch is refused."""
    _stall_then_ok(r5_record.build(_after_cutoff([BLOCK_AFTER_CUTOFF])))


def test_after_the_cutoff_reviewer_unavailable_stall_then_re_send():
    """SKILL.md Step 3, the protocol's normal shape: before re-sending a
    stalled reviewer the supervisor logs reviewer_unavailable (reason stall),
    closing the round as UNAVAILABLE; the re-send is then an ordinary review."""
    trail = [{"ts": "2026-11-13T22:10:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             {"ts": "2026-11-13T22:15:00+00:00", "event": "reviewer_unavailable",
              "pass": "correctness", "iteration": 1, "reason": "stall"},
             {"ts": "2026-11-13T22:20:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             dict(received("00:00", "correctness", 1, []), ts="2026-11-13T22:25:00+00:00")]
    out = r5_record.build(dict(state(trail, [("correctness", 0)]), started_at=r5_record.STEP3_CUTOFF))
    _stall_then_ok(out)
    assert out["rounds"][0]["ended"] == "2026-11-13T22:15:00+00:00"
    assert out["rounds"][1]["started"] == "2026-11-13T22:20:00+00:00"


def test_before_the_cutoff_reviewer_dispatch_blocked_still_refuses():
    """opensrm-6kqs.14: before STEP3_CUTOFF the event rule is unchanged (ir5m
    stays refused by event): the re-send replaces the blocked dispatch."""
    out = _resent([ev("00:40", "reviewer_dispatch_blocked", **{
        "pass": "correctness", "iteration": 1, "reason": "parallel-block hook refused the launch"})])
    assert len(out["rounds"]) == 1
    assert r5_record.refused_dispatches(out) == [
        ("correctness", "2026-11-13T10:00:10+00:00", "event")]


def test_a_not_converged_supervisor_blocked_after_a_returned_review_gives_no_stall():
    """opensrm-6kqs.14: the 'not converged after 3 fix iterations' escalation
    (6kqs.1, 6kqs.2-store, t4rd, wo62-4-19...) follows a findings_received:
    the reviewer returned, so the next dispatch is no re-send and no stall is
    inferred from the supervisor_blocked alone, before or after the cutoff."""
    for started_at in ("2026-11-13T10:00:00+00:00", r5_record.STEP3_CUTOFF):
        f = finding("correctness")
        trail = [ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
                 received("01:00", "correctness", 1, [f]),
                 ev("01:10", "supervisor_blocked", **{
                     "pass": "correctness", "reason": "not converged after 3 fix iterations"}),
                 ev("01:30", "fixes_applied", **{"pass": "correctness"}),
                 ev("01:40", "commit_made", sha=FIX1, repo="nthlayer"),
                 ev("02:00", "reviewer_dispatched", **{"pass": "correctness", "iteration": 2}),
                 received("03:00", "correctness", 2, [], closures=[f["fingerprint"]])]
        out = r5_record.build(dict(state(trail, [("correctness", 1)]), started_at=started_at))
        assert [r["kind"] for r in out["rounds"]] == ["review", "fix", "verify"]
        assert all(e["status"] == "ok" for r in out["rounds"] for e in r["lenses"].values())


# A synthetic KNOWN_REFUSED row, in the table's key shape (bead, pass, the
# dispatch ts exact string) with a reason and an evidence pointer.
ROW = ("opensrm-fx.1", "correctness", "2026-11-13T10:00:10+00:00")
ROW_TABLE = {ROW: {"reason": "hook refused the launch", "evidence": "synthetic"}}


def test_a_table_row_refuses_its_dispatch(monkeypatch):
    """The table rule (opensrm-6kqs.14): a dispatch listed in KNOWN_REFUSED is
    replaced by its re-send with no event between."""
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", ROW_TABLE)
    out = _resent([])
    assert [r["started"] for r in out["rounds"]] == ["2026-11-13T10:12:00+00:00"]
    assert r5_record.refused_dispatches(out) == [("correctness", ROW[2], "table")]


def test_a_table_row_matches_its_ts_exactly(monkeypatch):
    """The key is the dispatch ts as logged: the same instant spelt with Z
    is not the row, so it matches nothing and the record is refused."""
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", {
        (ROW[0], ROW[1], "2026-11-13T10:00:10Z"): ROW_TABLE[ROW]})
    with pytest.raises(r5_record.BuildRefused) as caught:
        _resent([])
    assert caught.value.reason == "table_row_unmatched"


def test_a_table_row_in_a_record_after_the_cutoff_is_refused(monkeypatch):
    """opensrm-6kqs.14: the table is history only; a row in a record started
    at or after STEP3_CUTOFF is an error."""
    key = ("opensrm-fx.1", "correctness", "2026-11-13T22:10:00+00:00")
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", {key: ROW_TABLE[ROW]})
    assert _refusal(_after_cutoff([])) == "table_row_after_cutoff"


def test_a_table_row_after_the_cutoff_is_refused_in_an_earlier_record(monkeypatch):
    """opensrm-6kqs.14: the table covers records up to the Step 3 change and
    takes no new rows after it, so a row whose own ts is at or after
    STEP3_CUTOFF is an error even when its record started before it."""
    key = ("opensrm-fx.1", "correctness", "2026-11-13T22:10:00+00:00")
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", {key: ROW_TABLE[ROW]})
    record = dict(_after_cutoff([]), started_at="2026-11-13T22:00:00+00:00")
    assert r5_record._record_start(record, record["audit_trail"]) < r5_record._instant(
        r5_record.STEP3_CUTOFF) <= r5_record._instant(key[2])
    assert _refusal(record) == "table_row_after_cutoff"


def test_an_unmatched_table_row_is_refused(monkeypatch):
    """opensrm-6kqs.14: a row of this bead, inside this record's span, that
    matches no re-sent dispatch is detected: build refuses (sweep then lists
    the record under refused). Here the listed dispatch was answered."""
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", ROW_TABLE)
    assert full_gate()["audit_trail"][1]["ts"] == ROW[2]
    assert _refusal(full_gate()) == "table_row_unmatched"


def test_the_real_table_is_history_with_reasons():
    """opensrm-6kqs.14: each row carries a reason and an evidence pointer and
    predates STEP3_CUTOFF."""
    assert len(r5_record.KNOWN_REFUSED) == 2
    for (bead, lens, ts), row in r5_record.KNOWN_REFUSED.items():
        assert bead.startswith("opensrm-") and lens in r5_record.LENSES
        assert r5_record._instant(ts) < r5_record._instant(r5_record.STEP3_CUTOFF)
        assert row["reason"] and row["evidence"] and set(row) == {"reason", "evidence"}


def test_a_table_row_of_another_bead_or_outside_the_span_is_not_this_records(monkeypatch):
    """A bead gated at several checkpoints has one record each; a row is the
    record's whose audit trail spans its ts (r5_baseline's rule)."""
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", {
        ("opensrm-other", *ROW[1:]): ROW_TABLE[ROW],
        (ROW[0], ROW[1], "2026-11-12T10:00:10+00:00"): ROW_TABLE[ROW]})
    assert r5_record.build(full_gate())["rounds"]


def test_validate_notes_name_the_rule(monkeypatch):
    """opensrm-6kqs.14: validate says which rule refused each replaced
    dispatch, re-derived from the kept audit_trail; no new record field."""
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", ROW_TABLE)
    by_table = _resent([])
    assert "refused dispatch correctness 2026-11-13T10:00:10+00:00: table" in \
        r5_record.validate(by_table)["notes"]
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", {})
    by_event = _resent([ev("00:40", "reviewer_dispatch_blocked", **{"pass": "correctness"})])
    assert "refused dispatch correctness 2026-11-13T10:00:10+00:00: event" in \
        r5_record.validate(by_event)["notes"]
    assert set(by_event) == set(full_gate()) | set(r5_record.DERIVED_KEYS)


def test_a_block_for_another_pass_does_not_replace_a_stall():
    out = _resent([ev("00:40", "reviewer_dispatch_blocked", **{"pass": "provenance"})])
    assert [r["lenses"]["correctness"]["status"] for r in out["rounds"]] == ["UNAVAILABLE", "ok"]


def test_a_block_before_the_pending_dispatch_does_not_replace_a_stall():
    """The block refused the dispatch before it; the pending one ran."""
    trail = [
        ev("00:05", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        ev("00:06", "reviewer_dispatch_blocked", **{"pass": "correctness"}),
        ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        ev("12:00", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        received("14:00", "correctness", 1, []),
    ]
    out = r5_record.build(state(trail, [("correctness", 0)]))
    assert [(r["started"], r["lenses"]["correctness"]["status"]) for r in out["rounds"]] == [
        ("2026-11-13T10:00:10+00:00", "UNAVAILABLE"), ("2026-11-13T10:12:00+00:00", "ok")]


def test_a_stall_keeps_its_dispatch_measurements_but_never_a_duration():
    """Measured fields logged on the reviewer events pass through (as in
    test_measured_fields_on_the_event_are_kept), but a stall has no receipt:
    a duration_s on its dispatch would stand for a run nobody timed."""
    trail = [
        ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1,
                                              "model": "claude-opus-5-5", "duration_s": 30}),
        ev("12:00", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
        received("14:00", "correctness", 1, []),
    ]
    entry = r5_record.build(state(trail, [("correctness", 0)]))["rounds"][0]["lenses"]["correctness"]
    assert (entry["status"], entry["model"], entry["duration_s"]) == ("UNAVAILABLE", "claude-opus-5-5", None)


# ---------------------------------- provenance pass additions (6kqs.14 gate)
# Each case covers a branch the 6kqs.14 provenance pass mutated and found
# green; its source is named in the docstring.


@pytest.mark.parametrize("dispatch_head, expected", [
    ("ccccccc", "ccccccc"),
    (None, HEAD0),
], ids=["dispatch-head", "running-head"])
def test_a_stall_round_s_head_is_its_dispatch_s_else_the_running_head(dispatch_head, expected):
    """opensrm-6kqs.14 (stall = a dispatch with no result before its re-send) makes
    the stalled dispatch a round of its own, so its head follows the receipt
    round's rule (test_a_dispatch_head_is_the_round_head: iiay, f751 log the
    HEAD a reviewer read on reviewer_dispatched): the dispatch's head, else the
    running head (diff_range's head, HEAD0, before any fix commit)."""
    first = ev("00:10", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1})
    if dispatch_head is not None:
        first["head"] = dispatch_head
    trail = [first,
             ev("12:00", "reviewer_dispatched", **{"pass": "correctness", "iteration": 1}),
             received("14:00", "correctness", 1, [])]
    stall, answer = r5_record.build(state(trail, [("correctness", 0)]))["rounds"]
    assert stall["lenses"]["correctness"]["status"] == "UNAVAILABLE"
    assert stall["head"] == expected
    assert answer["head"] == HEAD0


def test_after_the_cutoff_a_second_re_send_after_a_settled_pause_is_a_stall():
    """opensrm-6kqs.14: post-cutoff a logged dispatch always ran, and only a
    supervisor_blocked between a dispatch and ITS re-send is ambiguous. Here
    the pause (settled by reviewer_dispatch_blocked, SKILL.md Step 3's shape)
    lies before the first re-send only; the second re-send follows a dispatch
    with no pause after it, so both earlier dispatches are stalls."""
    trail = [{"ts": "2026-11-13T22:10:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             PAUSE_AFTER_CUTOFF, BLOCK_AFTER_CUTOFF,
             {"ts": "2026-11-13T22:20:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             {"ts": "2026-11-13T22:22:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             dict(received("00:00", "correctness", 1, []), ts="2026-11-13T22:25:00+00:00")]
    out = r5_record.build(dict(state(trail, [("correctness", 0)]), started_at=r5_record.STEP3_CUTOFF))
    assert [r["lenses"]["correctness"]["status"] for r in out["rounds"]] == [
        "UNAVAILABLE", "UNAVAILABLE", "ok"]
    assert [r["started"] for r in out["rounds"]] == [
        "2026-11-13T22:10:00+00:00", "2026-11-13T22:20:00+00:00", "2026-11-13T22:22:00+00:00"]
    assert r5_record.refused_dispatches(out) == []


def test_a_table_row_exactly_at_the_cutoff_is_refused(monkeypatch):
    """opensrm-6kqs.14: the table takes no rows at/after STEP3_CUTOFF, so a row
    whose ts IS the cutoff is late, even in a record started before it. The
    row otherwise matches a re-sent dispatch, so only the cutoff refuses it."""
    key = ("opensrm-fx.1", "correctness", r5_record.STEP3_CUTOFF)
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", {key: ROW_TABLE[ROW]})
    trail = [{"ts": r5_record.STEP3_CUTOFF, "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             {"ts": "2026-11-13T22:20:00+00:00", "event": "reviewer_dispatched",
              "pass": "correctness", "iteration": 1},
             dict(received("00:00", "correctness", 1, []), ts="2026-11-13T22:25:00+00:00")]
    record = dict(state(trail, [("correctness", 0)]), started_at="2026-11-13T22:00:00+00:00")
    assert _refusal(record) == "table_row_after_cutoff"


def test_a_table_row_with_an_unparseable_ts_is_refused(monkeypatch):
    """KNOWN_REFUSED's docstring: a mistyped key must not pass silently. A ts
    that does not parse can match no logged dispatch, so the row is the
    record's (its bead) and unmatched: build refuses it."""
    monkeypatch.setattr(r5_record, "KNOWN_REFUSED", {
        (ROW[0], ROW[1], "2026-13-99Tbad"): ROW_TABLE[ROW]})
    assert _refusal(full_gate()) == "table_row_unmatched"


def test_a_record_with_no_started_at_is_dated_by_its_first_event():
    """SKILL.md's r5-state.json carries started_at, but an archive missing it is
    dated by its first audit event. A trail that starts after STEP3_CUTOFF is
    then post-cutoff, and opensrm-6kqs.14 refuses its ambiguous supervisor_blocked
    re-send (before the cutoff the same trail would be a stall)."""
    record = _after_cutoff([PAUSE_AFTER_CUTOFF])
    del record["started_at"]
    assert _refusal(record) == "blocked_resend_ambiguous"


def test_validate_checks_the_shape_of_a_record_whose_trail_no_longer_builds():
    """validate checks the section 6 shape; refused-dispatch notes
    (opensrm-6kqs.14) are informational, re-derived from audit_trail when it
    derives. A built record whose trail then gains an unanswered dispatch
    (dispatch_unanswered) is still shape-valid: validate returns it valid with
    no refused-dispatch notes rather than raising. Whether rounds[] matches its
    trail is r5_baseline._check_rounds's question, not the shape's."""
    record = r5_record.build(full_gate())
    record["audit_trail"].append(
        ev("11:00", "reviewer_dispatched", **{"pass": "provenance", "iteration": 2}))
    assert _refusal(record) == "dispatch_unanswered"
    report = r5_record.validate(record)
    assert report["valid"] and report["errors"] == []
    assert not any(n.startswith("refused dispatch") for n in report["notes"])


# ------------------------------------------------ round 0 (opensrm-6kqs.5)
#
# Bead 5 in section 3 of the spec, and R5-R1: before the first reviewer the
# supervisor runs lint, the type check, the full suite and the provenance
# mechanical checks; any failure ends the gate PREFLIGHT_FAILED with the tool
# output in the record, and a check hit is a blocking provenance finding
# that stops the gate before any model. The event is the one r5_record's
# docstring defines (round0_completed); section 6 gives the round its kind,
# "preflight", and the record its verdict state, "PREFLIGHT_FAILED".


def round0(ts: str = "00:05", verdict: str = "ok", findings: list | None = None,
           suite_ok: bool = True, **more) -> dict:
    results = {
        "lint": {"ok": True, "command": "uvx ruff check src/ tests/", "output_tail": "All checks passed!"},
        "typecheck": {"ok": True, "command": None, "output_tail": None},
        "suite": {"ok": suite_ok, "command": "uv run pytest -q",
                  "output_tail": "3 passed" if suite_ok else "1 failed, 2 passed"},
        "provenance_checks": {"ok": not findings, "command": "r5_provenance_checks.py check",
                              "output_tail": "exit 2" if findings else "exit 0"},
    }
    fields = {"head": HEAD0, "results": results, "findings": findings or [], "verdict": verdict}
    fields.update(more)
    return ev(ts, "round0_completed", **fields)


def _gate_after(event: dict) -> dict:
    """The full gate with round 0 logged before its first dispatch."""
    g = full_gate()
    g["audit_trail"].insert(0, event)
    return g


def _stopped(event: dict) -> dict:
    """A gate that stopped at round 0: no dispatch, no pass completed."""
    rec = state([ev("00:00", "supervisor_started"), event], [])
    rec["verdict"] = {"state": "PREFLIGHT_FAILED", "tree_sha": None, "head_sha": HEAD0,
                      "at": event["ts"]}
    return rec


def test_a_clean_round_0_is_round_1_and_the_gate_follows():
    out = r5_record.build(_gate_after(round0()))
    first = out["rounds"][0]
    assert (first["n"], first["kind"], first["head"], first["lenses"]) == (1, "preflight", HEAD0, {})
    assert first["preflight"]["verdict"] == "ok"
    assert set(first["preflight"]["results"]) == {"lint", "typecheck", "suite", "provenance_checks"}
    assert "fix" not in first
    # The review rounds keep their order, one later.
    assert [r["kind"] for r in out["rounds"][1:]] == [
        r["kind"] for r in r5_record.build(full_gate())["rounds"]]
    assert [r["n"] for r in out["rounds"]] == list(range(1, len(out["rounds"]) + 1))
    assert r5_record.validate(out)["valid"] is True


def test_round_0_s_started_defaults_to_its_event_and_takes_a_stated_start():
    out = r5_record.build(_gate_after(round0()))["rounds"][0]
    assert out["started"] == out["ended"] == "2026-11-13T10:00:05+00:00"
    out = r5_record.build(_gate_after(round0(started="2026-11-13T10:00:01+00:00")))["rounds"][0]
    assert out["started"] == "2026-11-13T10:00:01+00:00"


def test_a_tool_failure_stops_the_gate_and_still_builds():
    """R5-R1: the record of a gate that stopped is the tool output."""
    out = r5_record.build(_stopped(round0(suite_ok=False, verdict="PREFLIGHT_FAILED")))
    assert [r["kind"] for r in out["rounds"]] == ["preflight"]
    assert out["rounds"][0]["preflight"]["results"]["suite"]["output_tail"] == "1 failed, 2 passed"
    assert out["head"] == HEAD0
    assert r5_record.validate(out) == {"valid": True, "errors": [], "notes": []}


def test_a_check_hit_is_a_blocking_provenance_finding_and_stops_the_gate():
    hit = dict(finding("provenance", "CRITICAL", "pytestmark applies skipif to the whole module"),
               verification_level="script")
    out = r5_record.build(_stopped(round0(findings=[hit], verdict="PREFLIGHT_FAILED")))
    assert out["rounds"][0]["preflight"]["findings"] == [hit]
    assert r5_record.validate(out)["valid"] is True


@pytest.mark.parametrize("kwargs", [
    {"verdict": "PREFLIGHT_FAILED"},  # everything ok, yet failed
    {"suite_ok": False},  # a tool failed, yet ok
    {"findings": [dict(finding("provenance", "CRITICAL"), verification_level="script")]},
], ids=["failed-when-ok", "ok-when-a-tool-failed", "ok-with-a-hit"])
def test_a_verdict_that_contradicts_its_results_is_refused(kwargs):
    assert _refusal(_gate_after(round0(**kwargs))) == "preflight_verdict_mismatch"


@pytest.mark.parametrize("more", [
    {"results": {}},
    {"results": {"suite": {"ok": True, "command": 3, "output_tail": None}}},
    {"findings": "none"},
    {"findings": [finding("correctness", "CRITICAL")]},  # not a provenance finding
    {"verdict": "CLEAN"},
], ids=["no-results", "command-not-a-string", "findings-not-a-list", "wrong-lens", "bad-verdict"])
def test_a_malformed_round_0_is_refused(more):
    assert _refusal(_gate_after(round0(**more))) == "bad_preflight_event"


def test_round_0_after_a_dispatch_is_refused():
    g = full_gate()
    g["audit_trail"].insert(2, round0("00:15"))  # after the first dispatch
    assert _refusal(g) == "preflight_not_first"


def test_a_second_round_0_is_refused():
    g = _gate_after(round0())
    g["audit_trail"].insert(1, round0("00:06"))
    assert _refusal(g) == "preflight_not_first"


def test_validate_holds_round_0_to_its_place_and_shape():
    out = r5_record.build(_gate_after(round0()))
    moved = copy.deepcopy(out)
    moved["rounds"][0], moved["rounds"][1] = moved["rounds"][1], moved["rounds"][0]
    moved["rounds"][0]["n"], moved["rounds"][1]["n"] = 1, 2
    assert any("round 1 or absent" in e for e in r5_record.validate(moved)["errors"])
    with_lens = copy.deepcopy(out)
    with_lens["rounds"][0]["lenses"] = copy.deepcopy(out["rounds"][1]["lenses"])
    assert any("dispatches no lens" in e for e in r5_record.validate(with_lens)["errors"])
    bad = copy.deepcopy(out)
    bad["rounds"][0]["preflight"]["verdict"] = "PREFLIGHT_FAILED"
    assert any("preflight: verdict: PREFLIGHT_FAILED but" in e for e in r5_record.validate(bad)["errors"])
    stray = copy.deepcopy(out)
    stray["rounds"][1]["preflight"] = out["rounds"][0]["preflight"]
    assert any("preflight object on a" in e for e in r5_record.validate(stray)["errors"])


def test_validate_refuses_rounds_after_a_failed_round_0_and_a_contrary_verdict():
    out = r5_record.build(_stopped(round0(suite_ok=False, verdict="PREFLIGHT_FAILED")))
    extra = copy.deepcopy(out)
    extra["rounds"].append(dict(r5_record.build(full_gate())["rounds"][0], n=2))
    assert any("follow a PREFLIGHT_FAILED" in e for e in r5_record.validate(extra)["errors"])
    contrary = copy.deepcopy(out)
    contrary["verdict"]["state"] = "CLEAN"
    assert any("verdict.state" in e for e in r5_record.validate(contrary)["errors"])


def test_a_gate_with_no_round_0_is_unchanged():
    """Archives before bead 5 log no round0_completed: no preflight round."""
    assert all(r["kind"] != "preflight" for r in r5_record.build(full_gate())["rounds"])
