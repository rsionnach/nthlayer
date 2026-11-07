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
        "r5-state-g32d-checkpointA-completed.json",
        "r5-state-g32d-checkpointB-completed.json",
        "r5-state-g35i-completed.json",
        "r5-state-ir5m-completed.json",
        "r5-state-m7su-dryrun-completed.json",
        "r5-state-oh27-completed.json",
        "r5-state-pnmv-checkpointB-completed.json",
        "r5-state-tu04.1.2.2-completed.json",
        "r5-state-wo62-1-checkpointA-common-completed.json",
        "r5-state-wo62-4-1-completed.json",
    ]


def test_severities_per_review_come_from_findings_received():
    # 3ntg correctness logged three reviews: 0/1/3, then 0/1/0, then 0/0/1,
    # with fix_iterations 2.
    lens = _row("3ntg")["lenses"]["correctness"]
    assert lens["findings_by_review"] == [
        {"critical": 0, "important": 1, "minor": 3, "other": 0},
        {"critical": 0, "important": 1, "minor": 0, "other": 0},
        {"critical": 0, "important": 0, "minor": 1, "other": 0},
    ]
    assert (lens["reviews"], lens["fix_rounds"], lens["steps"]) == (3, 2, 5)
    assert lens["steps_source"] == "events"
    assert lens["unattributed"] == 0  # first review 0+1+3 = findings_count_initial 4


def test_advisory_excellence_is_one_review_from_advisory_pass_completed():
    lens = _row("3ntg")["lenses"]["excellence"]
    assert lens["findings_by_review"] == [{"critical": 0, "important": 0, "minor": 4, "other": 0}]
    assert (lens["reviews"], lens["fix_rounds"], lens["steps"]) == (1, 0, 1)


def test_lens_order_and_critical_path_for_a_v2_record():
    row = _row("3ntg")
    assert row["lens_order"] == ["correctness", "clarity", "edge-cases", "provenance", "excellence"]
    # reviews + fixes: correctness 3+2, clarity 2+1, edge-cases 2+1,
    # provenance 3+2, excellence 1+0.
    assert row["sequential_steps"] == 17


def test_a_totals_only_record_reports_every_finding_unattributed():
    # 1mja (v1) has no findings_received: totals 2/5/3/0, fix_iterations 1/0/1/0.
    lenses = _row("1mja")["lenses"]
    assert {k: (v["recorded_initial"], v["unattributed"]) for k, v in lenses.items()} == {
        "correctness": (2, 2), "clarity": (5, 5), "edge-cases": (3, 3), "excellence": (0, 0),
    }
    # pass_completed carries fix_iterations for correctness and edge-cases only.
    assert {k: v["steps_source"] for k, v in lenses.items()} == {
        "correctness": "pass_completed", "clarity": "pass_summary",
        "edge-cases": "pass_completed", "excellence": "pass_summary",
    }
    assert all(v["findings_by_review"] == [] for v in lenses.values())


def test_without_events_reviews_are_fix_iterations_plus_one():
    # oh27: fix_iterations 1/3/5/1, so reviews 2/4/6/2 and steps 3+7+11+3.
    row = _row("oh27")
    assert [row["lenses"][k]["reviews"] for k in row["lens_order"]] == [2, 4, 6, 2]
    assert row["sequential_steps"] == 24


def test_a_count_key_outside_the_three_severities_goes_to_other():
    # m7su's first edge-cases review logged missing_tests: 5.
    first = _row("m7su-dryrun")["lenses"]["edge-cases"]["findings_by_review"][0]
    assert first["other"] == 5


def test_dry_runs_are_excluded_from_the_totals():
    rows = [r5_baseline.analyse_record(json.loads(p.read_text())) for p in sorted(FIXTURES.glob("*.json"))]
    counted = r5_baseline.baseline_rows(rows)
    assert "opensrm-m7su" not in {r["bead"] for r in counted}
    # Excluded: the m7su dry run and tu04.1.2.2, abandoned with nothing reviewed.
    assert len(counted) == len(rows) - 2


def test_an_advisory_event_never_double_counts_a_lens_with_findings_received():
    # Future-shape guard: no archive logs both today (checked 2026-11-07).
    record = {"completed_passes": [], "audit_trail": [
        {"event": "findings_received", "pass": "excellence", "counts": {"minor": 2}},
        {"event": "advisory_pass_completed", "pass": "excellence", "counts": {"minor": 2}},
    ]}
    lens = r5_baseline.analyse_record(record)["lenses"]["excellence"]
    assert lens["reviews"] == 1


def test_json_mode_reports_every_record(tmp_path, capsys):
    assert r5_baseline.main(["--archive-dir", str(FIXTURES), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["records"]) == 13
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
    assert (lenses["edge-cases"]["reviews"], lenses["edge-cases"]["fix_rounds"]) == (3, 3)
    assert (lenses["provenance"]["reviews"], lenses["provenance"]["fix_rounds"]) == (3, 2)
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
    assert (row["lenses"]["clarity+edge-cases"]["reviews"], row["lenses"]["clarity+edge-cases"]["fix_rounds"]) == (1, 1)
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
    assert _row("bnal")["lenses"]["correctness"]["reviews"] == 3


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
    assert row["lenses"]["correctness"]["reviews"] == correctness_reviews
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


def test_a_gate_with_no_lens_reviewed_is_not_counted():
    # tu04.1.2.2 was abandoned after pass_started (status in_progress).
    row = _row("tu04.1.2.2")
    assert row["lenses"] == {} and row["sequential_steps"] == 0
    assert row not in r5_baseline.baseline_rows([row])


def test_only_excluded_records_is_a_usage_error_not_a_crash(tmp_path):
    shutil.copy(FIXTURES / "r5-state-m7su-dryrun-completed.json", tmp_path)
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2


# Shapes no archive has today, so these probes are hand-built: each must be
# refused, since counting it would print a plausible wrong total.
@pytest.mark.parametrize("record", [
    {"rounds": [], "audit_trail": []},  # a Phase A.4 round record
    {"target_bead": "x"},  # neither audit_trail nor completed_passes
    {"audit_trail": [{"event": "findings_received", "pass": "c", "counts": {"critical": "1"}}]},
    {"audit_trail": [{"event": "findings_received", "pass": "c", "counts": {"minor": -1}}]},
    {"audit_trail": [{"event": "findings_received", "pass": "c", "counts": [1]}]},
    {"completed_passes": [{"name": "c", "fix_iterations": -1}], "audit_trail": []},
    {"completed_passes": [{"name": "c", "findings_count_initial": "3"}], "audit_trail": []},
    {"completed_passes": [{"name": "c", "fix_iterations": False}], "audit_trail": []},
    {"audit_trail": [{"event": "findings_received", "counts": {"critical": 1}}]},  # no pass
    {"audit_trail": [{"event": "findings_received", "pass": 3, "counts": {}}]},
    {"audit_trail": {"event": "findings_received"}},  # a dict, not a list
    {"audit_trail": ["findings_received"]},
    {"completed_passes": [{"fix_iterations": 1}], "audit_trail": []},  # no name
])
def test_a_record_it_cannot_count_is_refused(tmp_path, record):
    with pytest.raises(r5_baseline.RecordError):
        r5_baseline.analyse_record(record)
    (tmp_path / "r5-state-probe-completed.json").write_text(json.dumps(record))
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2



def test_a_known_passless_fix_is_given_to_its_pass():
    # g32d-A logged the scoped(correctness+edge) re-check's fix_dispatched and
    # fixes_applied with no pass (PASSLESS_EVENTS): one review, one fix round.
    lens = _row("g32d-checkpointA")["lenses"]["scoped(correctness+edge)"]
    assert (lens["reviews"], lens["fix_rounds"]) == (1, 1)


def test_the_passless_table_names_events_that_exist():
    events = {
        (rec["target_bead"], e.get("event"), e.get("ts"))
        for p in FIXTURES.glob("*.json")
        for rec in [json.loads(p.read_text())]
        for e in rec["audit_trail"] if "pass" not in e
    }
    assert set(r5_baseline.PASSLESS_EVENTS) <= events


def test_a_non_counting_event_without_a_pass_is_ignored():
    # supervisor_started, commit_made and the like carry no pass in real records.
    record = {"completed_passes": [], "audit_trail": [{"event": "supervisor_started"}]}
    assert r5_baseline.analyse_record(record)["lenses"] == {}


@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe\x00"])
def test_an_unreadable_archive_is_refused(tmp_path, content):
    (tmp_path / "r5-state-bad-completed.json").write_bytes(content)
    with pytest.raises(r5_baseline.RecordError):
        r5_baseline.load_records(tmp_path)
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2


def test_a_re_run_s_fixes_come_from_its_runs_when_events_and_summary_hold_one():
    # pnmv-B provenance ran twice, each pass_completed fix_iterations 1, but
    # logged one fix_dispatched and its summary holds the last run's 1.
    lens = _row("pnmv-checkpointB")["lenses"]["provenance"]
    assert (lens["reviews"], lens["fix_rounds"]) == (4, 2)


def test_totals_take_the_first_review_s_severities_and_count_re_reviews_apart():
    # 3ntg's findings_received, first review then the rest, per lens:
    #   correctness 0/1/3 then 0/1/0, 0/0/1; clarity 0/2/9 then 0/0/1;
    #   edge-cases 0/1/6 then 0/0/1; provenance 3/1/1 then 0/1/0, 0/0/1;
    #   excellence (advisory) 0/0/4.
    t = r5_baseline.totals([_row("3ntg")])
    first = {k: (v["critical"], v["important"], v["minor"]) for k, v in t.items()}
    assert first == {
        "correctness": (0, 1, 3), "clarity": (0, 2, 9), "edge-cases": (0, 1, 6),
        "provenance": (3, 1, 1), "excellence": (0, 0, 4),
    }
    assert {k: v["rereview_findings"] for k, v in t.items()} == {
        "correctness": 2, "clarity": 1, "edge-cases": 1, "provenance": 2, "excellence": 0,
    }


def test_passes_outside_the_roster_fold_into_one_row():
    # g35i's combined "clarity+edge-cases" review: first review 0/1/5.
    folded = r5_baseline.fold_other_passes(r5_baseline.totals([_row("g35i")]))
    assert "clarity+edge-cases" not in folded
    other = folded["other passes"]
    assert (other["critical"], other["important"], other["minor"], other["records"]) == (0, 1, 5, 1)


def test_step_stats_use_a_true_median():
    # The eight gates whose steps are hand-counted above: 17, 8, 24, 6, 19, 8,
    # 22, 19. An even count, so the median is the mean of the middle two.
    names = ["3ntg", "1mja", "oh27", "g35i", "g32d-checkpointB", "wo62-1-checkpointA-common", "ir5m", "wo62-4-1"]
    assert r5_baseline.step_stats([_row(n) for n in names]) == {"total": 123, "median": 18, "max": 24}


def test_the_published_table_folds_other_passes_and_follows_the_roster():
    # What docs/r5-gate.md publishes, as data. The fixtures' live, reviewed
    # gates use the five roster passes plus three one-off names (g35i
    # "clarity+edge-cases", g32d-A "scoped(correctness+edge)" and
    # "scoped re-check"), which the table must show as one "other passes" row.
    r = r5_baseline.report([_row(p.name.removeprefix("r5-state-").removesuffix("-completed.json"))
                            for p in sorted(FIXTURES.glob("*.json"))])
    assert [row[0] for row in r["table"]] == [
        "correctness", "clarity", "edge-cases", "provenance", "excellence", "other passes",
    ]
    assert (r["excluded_dry_runs"], r["excluded_unreviewed"]) == (1, 1)
    # 13 fixtures less the m7su dry run and tu04.1.2.2 (nothing reviewed); all
    # 11 have a reviewed correctness pass. With the exclusions skipped, either
    # number would rise.
    assert r["records"] == 11
    assert r["table"][0][r5_baseline.TABLE_COLUMNS.index("records")] == 11
    # Every row has a cell per column, or every later value shifts left.
    assert all(len(row) == len(r5_baseline.TABLE_COLUMNS) for row in r["table"])
    # The three one-off passes, by hand from the fixtures' events:
    #   g35i clarity+edge-cases     1 review, 0/1/5, 1 fix (fixes_applied)
    #   g32d-A scoped(correctness+edge)  1 review, 0/3/7, 1 fix (PASSLESS_EVENTS)
    #   g32d-A scoped re-check      1 review, 0/0/1, no fix
    # No summaries, so findings = severities and nothing is unattributed.
    assert r["table"][-1] == ["other passes", 3, 17, 0, 4, 13, 0, 0, 0, 3, 5]


def test_render_markdown_prints_every_report_row():
    rows = [_row("3ntg"), _row("g35i")]
    markdown = r5_baseline.render_markdown(rows)
    report = r5_baseline.report(rows)
    body = [line for line in markdown.splitlines() if line.startswith("| ") and "---" not in line][1:]
    assert len(body) == len(report["table"])
    # The step statistics line: each value the report holds is printed.
    stats_line = [line for line in markdown.splitlines() if line.startswith("Sequential model steps")]
    assert len(stats_line) == 1
    assert all(f"{v:g}" in stats_line[0] for v in report["steps"].values())
