"""Tests for scripts/r5_baseline.py (opensrm-6kqs.1, R5-R0).

The fixtures are trimmed real archives (test/fixtures/r5-baseline/README.md),
and every expected number below is read off those files by hand: the
findings_received counts, findings_count_initial and fix_iterations each one
records. None is copied from the script's output.

Run: uv run --no-project --with pytest pytest -q test/test_r5_baseline.py
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "r5-baseline"
_spec = importlib.util.spec_from_file_location("r5_baseline", HERE.parent / "scripts" / "r5_baseline.py")
assert _spec and _spec.loader
r5_baseline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r5_baseline)


def _row(name: str) -> dict:
    record = json.loads((FIXTURES / f"r5-state-{name}-completed.json").read_text())
    return r5_baseline.analyse_record(record)


def test_fixtures_are_present():
    # A missing fixture must fail here, not shrink the suite.
    names = sorted(p.name for p in FIXTURES.glob("r5-state-*-completed.json"))
    assert names == [
        "r5-state-1mja-completed.json",
        "r5-state-3ntg-completed.json",
        "r5-state-bnal-completed.json",
        "r5-state-g32d-checkpointB-completed.json",
        "r5-state-g35i-completed.json",
        "r5-state-ir5m-completed.json",
        "r5-state-m7su-dryrun-completed.json",
        "r5-state-oh27-completed.json",
        "r5-state-wo62-1-checkpointA-common-completed.json",
        "r5-state-wo62-4-1-completed.json",
    ]


def test_severities_per_iteration_come_from_findings_received():
    # 3ntg correctness logged three reviews: 0/1/3, then 0/1/0, then 0/0/1,
    # with fix_iterations 2.
    lens = _row("3ntg")["lenses"]["correctness"]
    assert lens["findings_by_iteration"] == [
        {"critical": 0, "important": 1, "minor": 3, "other": 0},
        {"critical": 0, "important": 1, "minor": 0, "other": 0},
        {"critical": 0, "important": 0, "minor": 1, "other": 0},
    ]
    assert (lens["iterations"], lens["fix_rounds"], lens["steps"]) == (3, 2, 5)
    assert lens["steps_source"] == "events"
    assert lens["unattributed"] == 0  # first review 0+1+3 = findings_count_initial 4


def test_advisory_excellence_is_one_review_from_advisory_pass_completed():
    lens = _row("3ntg")["lenses"]["excellence"]
    assert lens["findings_by_iteration"] == [{"critical": 0, "important": 0, "minor": 4, "other": 0}]
    assert (lens["iterations"], lens["fix_rounds"], lens["steps"]) == (1, 0, 1)


def test_lens_order_and_critical_path_for_a_v2_record():
    row = _row("3ntg")
    assert row["lens_order"] == ["correctness", "clarity", "edge-cases", "provenance", "excellence"]
    # reviews + fixes: correctness 3+2, clarity 2+1, edge-cases 2+1,
    # provenance 3+2, excellence 1+0.
    assert row["sequential_steps"] == 17


def test_a_totals_only_record_reports_every_finding_unattributed():
    # 1mja (v1) has no findings_received: totals 2/5/3/0, fix_iterations 1/0/1/0.
    lenses = _row("1mja")["lenses"]
    assert {k: (v["findings_initial"], v["unattributed"]) for k, v in lenses.items()} == {
        "correctness": (2, 2), "clarity": (5, 5), "edge-cases": (3, 3), "excellence": (0, 0),
    }
    # pass_completed carries fix_iterations for correctness and edge-cases only.
    assert {k: v["steps_source"] for k, v in lenses.items()} == {
        "correctness": "pass_completed", "clarity": "pass_summary",
        "edge-cases": "pass_completed", "excellence": "pass_summary",
    }
    assert all(v["findings_by_iteration"] == [] for v in lenses.values())


def test_without_events_reviews_are_fix_iterations_plus_one():
    # oh27: fix_iterations 1/3/5/1, so reviews 2/4/6/2 and steps 3+7+11+3.
    row = _row("oh27")
    assert [row["lenses"][k]["iterations"] for k in row["lens_order"]] == [2, 4, 6, 2]
    assert row["sequential_steps"] == 24


def test_a_count_key_outside_the_three_severities_goes_to_other():
    # m7su's first edge-cases review logged missing_tests: 5.
    first = _row("m7su-dryrun")["lenses"]["edge-cases"]["findings_by_iteration"][0]
    assert first["other"] == 5


def test_dry_runs_are_excluded_from_the_totals():
    rows = [r5_baseline.analyse_record(json.loads(p.read_text())) for p in sorted(FIXTURES.glob("*.json"))]
    counted = r5_baseline.baseline_rows(rows)
    assert "opensrm-m7su" not in {r["bead"] for r in counted}
    assert len(counted) == len(rows) - 1


def test_an_advisory_event_never_double_counts_a_lens_with_findings_received():
    # Future-shape guard: no archive logs both today (checked 2026-11-07).
    record = {"completed_passes": [], "audit_trail": [
        {"event": "findings_received", "pass": "excellence", "counts": {"minor": 2}},
        {"event": "advisory_pass_completed", "pass": "excellence", "counts": {"minor": 2}},
    ]}
    lens = r5_baseline.analyse_record(record)["lenses"]["excellence"]
    assert lens["iterations"] == 1


def test_json_mode_reports_every_record(tmp_path, capsys):
    assert r5_baseline.main(["--archive-dir", str(FIXTURES), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["records"]) == 10
    assert "opensrm-m7su" not in {r["bead"] for r in r5_baseline.baseline_rows(out["records"])}


@pytest.mark.parametrize("make", ["missing", "empty"])
def test_no_records_is_a_usage_error(tmp_path, make):
    target = tmp_path / "archive"
    if make == "empty":
        target.mkdir()
    assert r5_baseline.main(["--archive-dir", str(target)]) == 2


def test_a_non_archive_file_is_ignored(tmp_path):
    shutil.copy(FIXTURES / "r5-state-1mja-completed.json", tmp_path)
    (tmp_path / "r5-state.json").write_text("{}")  # the live state file, not an archive
    assert [n for n, _ in r5_baseline.load_records(tmp_path)] == ["r5-state-1mja-completed.json"]


def test_fixes_with_no_re_review_are_counted():
    # wo62-1-A: clarity, edge-cases and provenance each logged fixes_applied
    # with fix_iterations 0. Reviews 1 each; fixes 0/1/1/1; excellence 1.
    row = _row("wo62-1-checkpointA-common")
    assert [row["lenses"][k]["fix_rounds"] for k in ("correctness", "clarity", "edge-cases", "provenance")] == [0, 1, 1, 1]
    assert row["sequential_steps"] == 8


def test_a_re_run_pass_counts_every_run():
    # g32d-B re-ran correctness, edge-cases and provenance. edge-cases: three
    # reviews (2 + 1), three fix_dispatched, runs' fix_iterations 2 + 1.
    lenses = _row("g32d-checkpointB")["lenses"]
    assert (lenses["edge-cases"]["iterations"], lenses["edge-cases"]["fix_rounds"]) == (3, 3)
    assert (lenses["provenance"]["iterations"], lenses["provenance"]["fix_rounds"]) == (3, 2)
    # correctness 3+1, clarity 2+1, edge-cases 3+3, provenance 3+2, excellence 1+0.
    assert _row("g32d-checkpointB")["sequential_steps"] == 19


def test_a_re_run_shows_in_the_dispatch_sequence():
    assert _row("g32d-checkpointB")["dispatch_sequence"] == [
        "correctness", "clarity", "edge-cases", "provenance",
        "correctness", "edge-cases", "provenance",
    ]


def test_a_combined_pass_is_counted_once():
    # g35i reviewed clarity and edge-cases as one pass, "clarity+edge-cases",
    # yet completed_passes lists both. One review and one fix, counted there.
    row = _row("g35i")
    assert row["lens_order"] == ["correctness", "clarity+edge-cases", "provenance", "excellence"]
    assert (row["lenses"]["clarity+edge-cases"]["iterations"], row["lenses"]["clarity+edge-cases"]["fix_rounds"]) == (1, 1)
    # correctness 1+1, combined 1+1, provenance 1+0, excellence 1+0.
    assert row["sequential_steps"] == 6


def test_lens_order_follows_first_appearance_not_the_roster():
    # m7su has no pass_started for correctness, which nonetheless ran first.
    assert _row("m7su-dryrun")["lens_order"][0] == "correctness"


def test_first_review_findings_are_never_below_the_logged_severities():
    # Some passes counted only blocking findings in findings_count_initial:
    # wo62-1-A records 0 everywhere but logged MINORs (1/5/3/2).
    lenses = _row("wo62-1-checkpointA-common")["lenses"]
    assert [lenses[k]["findings_first_review"] for k in ("correctness", "clarity", "edge-cases", "provenance")] == [1, 5, 3, 2]


def test_a_re_sent_dispatch_counts_as_a_review():
    # bnal correctness: three reviewer_dispatched, two findings_received (a
    # stalled dispatch was re-sent).
    assert _row("bnal")["lenses"]["correctness"]["iterations"] == 3


def test_a_pass_started_but_never_reviewed_is_not_a_lens_run():
    record = {"completed_passes": [], "audit_trail": [{"event": "pass_started", "pass": "clarity"}]}
    row = r5_baseline.analyse_record(record)
    assert row["lenses"] == {} and row["lens_order"] == [] and row["sequential_steps"] == 0


# The two archived dispatches the hook blocked before any reviewer ran
# (BLOCKED_DISPATCHES). Hand counts from each record's events, per lens
# reviews + fix rounds:
#   ir5m      correctness 2+1 (3 dispatched, 1 blocked), clarity 4+2 (a real
#             stall re-sent), edge-cases 3+3, provenance 3+3, excellence 1.
#   wo62-4-1  correctness 2+1 (3 dispatched, 1 blocked), clarity 2+1,
#             edge-cases 2+1, provenance 5+4, excellence 1.
@pytest.mark.parametrize(("name", "steps", "correctness_reviews"), [
    ("ir5m", 22, 2),
    ("wo62-4-1", 19, 2),
])
def test_a_dispatch_the_hook_blocked_is_not_a_model_step(name, steps, correctness_reviews):
    row = _row(name)
    assert row["lenses"]["correctness"]["iterations"] == correctness_reviews
    assert row["sequential_steps"] == steps


def test_the_blocked_dispatch_table_names_events_that_exist():
    # An entry that matches no archived event would silently exclude nothing.
    fixtures = {
        (rec["target_bead"], e.get("pass"), e.get("ts"))
        for p in FIXTURES.glob("*.json")
        for rec in [json.loads(p.read_text())]
        for e in rec["audit_trail"] if e.get("event") == "reviewer_dispatched"
    }
    assert fixtures >= r5_baseline.BLOCKED_DISPATCHES
