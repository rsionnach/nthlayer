"""Tests for scripts/r5_baseline.py (opensrm-6kqs.1, R5-R0).

The fixtures are synthetic records, one per structural pattern the archives
show (test/fixtures/r5-baseline/README.md), and every expected number below is
read off those files by hand: the findings_received counts,
findings_count_initial and fix_iterations each one records. None is copied
from the script's output.

Run: uv run --no-project --with pytest pytest -q test/test_r5_baseline.py
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "r5-baseline"
_spec = importlib.util.spec_from_file_location("r5_baseline", HERE.parent / "scripts" / "r5_baseline.py")
assert _spec and _spec.loader
r5_baseline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r5_baseline)


# The fixtures are synthetic (README.md), so the known-data tables' real keys
# match none of them. Each test runs with the tables keyed to the synthetic
# counterparts of the real entries instead: same pattern, invented identity.
SYNTHETIC_BLOCKED_DISPATCHES = frozenset({
    ("fx-blocked-dispatch-after-launch", "correctness", "2000-01-01T00:00:03Z"),
    ("fx-blocked-dispatch-before-launch", "correctness", "2000-01-01T00:00:01Z"),
})
SYNTHETIC_PASSLESS_EVENTS = {
    ("fx-checkpointed-bead", "fix_dispatched", "2000-01-01T00:00:42Z"): "scoped(correctness+edge)",
    ("fx-checkpointed-bead", "fixes_applied", "2000-01-01T00:00:43Z"): "scoped(correctness+edge)",
}


@pytest.fixture(autouse=True)
def _synthetic_known_data(monkeypatch):
    monkeypatch.setattr(r5_baseline, "BLOCKED_DISPATCHES", SYNTHETIC_BLOCKED_DISPATCHES)
    monkeypatch.setattr(r5_baseline, "PASSLESS_EVENTS", SYNTHETIC_PASSLESS_EVENTS)


def _row(name: str) -> dict:
    record = json.loads((FIXTURES / f"r5-state-{name}-completed.json").read_text())
    return r5_baseline.analyse_record(record)


def test_fixtures_are_present():
    # A missing fixture must fail here, not shrink the suite.
    names = sorted(p.name for p in FIXTURES.glob("r5-state-*-completed.json"))
    assert names == [
        "r5-state-fx-abandoned-unreviewed-completed.json",
        "r5-state-fx-blocked-dispatch-after-launch-completed.json",
        "r5-state-fx-blocked-dispatch-before-launch-completed.json",
        "r5-state-fx-blocking-only-initial-count-completed.json",
        "r5-state-fx-clarity-advisory-completed.json",
        "r5-state-fx-combined-pass-completed.json",
        "r5-state-fx-dry-run-with-other-bucket-completed.json",
        "r5-state-fx-passless-fix-events-completed.json",
        "r5-state-fx-re-run-fixes-only-in-runs-completed.json",
        "r5-state-fx-re-run-passes-completed.json",
        "r5-state-fx-stall-and-resend-completed.json",
        "r5-state-fx-v1-fix-loops-completed.json",
        "r5-state-fx-v1-totals-only-completed.json",
        "r5-state-fx-v2-per-review-severities-completed.json",
    ]


def test_severities_per_review_come_from_findings_received():
    # fx-v2-per-review-severities, correctness: three reviews, 0/1/3, then
    # 0/1/0, then 0/0/1, with fix_iterations 2.
    lens = _row("fx-v2-per-review-severities")["lenses"]["correctness"]
    assert lens["findings_by_review"] == [
        {"critical": 0, "important": 1, "minor": 3, "other": 0},
        {"critical": 0, "important": 1, "minor": 0, "other": 0},
        {"critical": 0, "important": 0, "minor": 1, "other": 0},
    ]
    assert (lens["reviews"], lens["fix_rounds"], lens["steps"]) == (3, 2, 5)
    assert lens["steps_source"] == "events"
    assert lens["unattributed"] == 0  # first review 0+1+3 = findings_count_initial 4


def test_advisory_excellence_is_one_review_from_advisory_pass_completed():
    lens = _row("fx-v2-per-review-severities")["lenses"]["excellence"]
    assert lens["findings_by_review"] == [{"critical": 0, "important": 0, "minor": 4, "other": 0}]
    assert (lens["reviews"], lens["fix_rounds"], lens["steps"]) == (1, 0, 1)


def test_lens_order_and_critical_path_for_a_v2_record():
    row = _row("fx-v2-per-review-severities")
    assert row["lens_order"] == ["correctness", "clarity", "edge-cases", "provenance", "excellence"]
    # reviews + fixes: correctness 3+2, clarity 2+1, edge-cases 2+1, provenance
    # 3+2, excellence 1+0.
    assert row["sequential_steps"] == 17


def test_a_three_pass_record_reads_clarity_as_one_advisory_review():
    # The roster from 2026-11-12 (opensrm-6kqs.11): three passes, clarity and
    # excellence under advisory_passes, each read once on the final tree. By
    # hand from fx-clarity-advisory: correctness 2 reviews + 1 fix, edge-cases
    # 1 + 0, provenance 2 + 1, clarity 1 + 0, excellence 1 + 0.
    row = _row("fx-clarity-advisory")
    assert row["lens_order"] == ["correctness", "edge-cases", "provenance", "clarity", "excellence"]
    assert row["sequential_steps"] == 9
    clarity = row["lenses"]["clarity"]
    assert clarity["findings_by_review"] == [{"critical": 0, "important": 2, "minor": 5, "other": 0}]
    assert (clarity["reviews"], clarity["fix_rounds"], clarity["steps"]) == (1, 0, 1)


def test_a_totals_only_record_reports_every_finding_unattributed():
    # fx-v1-totals-only has no findings_received: totals 2/5/3/0,
    # fix_iterations 1/0/1/0.
    lenses = _row("fx-v1-totals-only")["lenses"]
    assert {k: (v["recorded_initial"], v["unattributed"]) for k, v in lenses.items()} == {
        "correctness": (2, 2), "clarity": (5, 5), "edge-cases": (3, 3), "excellence": (0, 0),
    }
    # pass_completed carries fix_iterations for correctness and edge-cases
    # only.
    assert {k: v["steps_source"] for k, v in lenses.items()} == {
        "correctness": "pass_completed", "clarity": "pass_summary",
        "edge-cases": "pass_completed", "excellence": "pass_summary",
    }
    assert all(v["findings_by_review"] == [] for v in lenses.values())


def test_without_events_reviews_are_fix_iterations_plus_one():
    # fx-v1-fix-loops: fix_iterations 1/3/5/1, so reviews 2/4/6/2 and steps
    # 3+7+11+3.
    row = _row("fx-v1-fix-loops")
    assert [row["lenses"][k]["reviews"] for k in row["lens_order"]] == [2, 4, 6, 2]
    assert row["sequential_steps"] == 24


def test_a_count_key_outside_the_three_severities_goes_to_other():
    # fx-dry-run-with-other-bucket: its first edge-cases review logged
    # missing_tests: 5.
    first = _row("fx-dry-run-with-other-bucket")["lenses"]["edge-cases"]["findings_by_review"][0]
    assert first["other"] == 5


def test_dry_runs_are_excluded_from_the_totals():
    rows = [r5_baseline.analyse_record(json.loads(p.read_text())) for p in sorted(FIXTURES.glob("*.json"))]
    counted = r5_baseline.baseline_rows(rows)
    assert "fx-dry-run-with-other-bucket" not in {r["bead"] for r in counted}
    # Excluded: fx-dry-run-with-other-bucket and fx-abandoned-unreviewed.
    assert len(counted) == len(rows) - 2


def test_an_advisory_event_never_double_counts_a_lens_with_findings_received():
    # Future-shape guard: no archive logs both today (checked 2026-11-07).
    record = {"completed_passes": [], "audit_trail": [
        {"event": "findings_received", "pass": "excellence", "counts": {"minor": 2}},
        {"event": "advisory_pass_completed", "pass": "excellence", "counts": {"minor": 2}},
    ]}
    lens = r5_baseline.analyse_record(record)["lenses"]["excellence"]
    assert lens["reviews"] == 1


def _json_out(capsys) -> dict:
    assert r5_baseline.main(["--archive-dir", str(FIXTURES), "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_json_mode_reports_every_record(capsys):
    out = _json_out(capsys)
    assert out["schema_version"] == 1
    assert len(out["records"]) == 14
    assert "fx-dry-run-with-other-bucket" not in {r["bead"] for r in r5_baseline.baseline_rows(out["records"])}


def test_json_marks_the_records_the_totals_leave_out(capsys):
    # The two excluded fixtures (a dry run; a gate abandoned before any
    # review) are listed but not counted; the other twelve are.
    out = _json_out(capsys)
    uncounted = sorted(r["file"] for r in out["records"] if not r["counted"])
    assert uncounted == [
        "r5-state-fx-abandoned-unreviewed-completed.json",
        "r5-state-fx-dry-run-with-other-bucket-completed.json",
    ]
    assert sum(r["counted"] for r in out["records"]) == 12


def test_a_bead_with_two_records_sums_their_steps(capsys):
    # fx-checkpointed-bead is gated twice. By hand from the fixtures:
    #   fx-passless-fix-events: correctness 3 reviews + 2 fixes = 5; clarity
    #   2 + 1 = 3; edge-cases 3 + 3 (fix_dispatched) = 6; provenance 2 + 1 = 3;
    #   excellence 1; scoped(correctness+edge) 1 + 1 = 2; scoped re-check 1.
    #   Total 21.
    #   fx-re-run-passes: 19 (test_step_stats_use_a_true_median).
    out = _json_out(capsys)
    bead = out["beads"]["fx-checkpointed-bead"]
    assert sorted(bead["records"]) == [
        "r5-state-fx-passless-fix-events-completed.json",
        "r5-state-fx-re-run-passes-completed.json",
    ]
    assert bead["sequential_steps"] == 40
    # Uncounted records give their bead no entry.
    assert "fx-dry-run-with-other-bucket" not in out["beads"]
    assert "fx-abandoned-unreviewed" not in out["beads"]
    assert len(out["beads"]) == 11


def test_json_carries_the_table_summary(capsys):
    out = _json_out(capsys)
    rows = [_row(p.name.removeprefix("r5-state-").removesuffix("-completed.json"))
            for p in sorted(FIXTURES.glob("*.json"))]
    assert out["summary"] == json.loads(json.dumps(r5_baseline.report(rows)))


def test_schema_versions_are_counted_by_value():
    # Counted fixtures: 2 of version 1 (the other two v1 files are the
    # excluded ones), 10 of version 2; read off the files' "version" fields.
    rows = [_row(p.name.removeprefix("r5-state-").removesuffix("-completed.json"))
            for p in sorted(FIXTURES.glob("*.json"))]
    assert r5_baseline.report(rows)["versions"] == {"1": 2, "2": 10}
    # A third version is its own bucket, not folded into v2.
    rows[0] = dict(rows[0], version=3)
    assert r5_baseline.schema_versions(rows)["3"] == 1
    # In numeric order, not text order: "2" before "10".
    assert list(r5_baseline.schema_versions([dict(rows[1], version=10), dict(rows[1], version=2)])) == ["2", "10"]


def test_an_archive_that_cannot_be_opened_is_refused(tmp_path):
    # A directory where a record should be: open() raises IsADirectoryError,
    # an OSError, which is a refusal (exit 2), not a traceback.
    (tmp_path / "r5-state-probe-completed.json").mkdir()
    with pytest.raises(r5_baseline.RecordError):
        r5_baseline.load_records(tmp_path)
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2


@pytest.mark.parametrize("make", ["missing", "empty"])
def test_no_records_is_a_usage_error(tmp_path, make):
    target = tmp_path / "archive"
    if make == "empty":
        target.mkdir()
    assert r5_baseline.main(["--archive-dir", str(target)]) == 2


def test_a_non_archive_file_is_ignored(tmp_path):
    shutil.copy(FIXTURES / "r5-state-fx-v1-totals-only-completed.json", tmp_path)
    (tmp_path / "r5-state.json").write_text("{}")  # the live state file, not an archive
    assert [n for n, _ in r5_baseline.load_records(tmp_path)] == ["r5-state-fx-v1-totals-only-completed.json"]


def test_fixes_with_no_re_review_are_counted():
    # fx-blocking-only-initial-count: clarity, edge-cases and provenance each
    # logged fixes_applied with fix_iterations 0. Reviews 1 each; fixes
    # 0/1/1/1; excellence 1.
    row = _row("fx-blocking-only-initial-count")
    assert [row["lenses"][k]["fix_rounds"] for k in ("correctness", "clarity", "edge-cases", "provenance")] == [0, 1, 1, 1]
    assert row["sequential_steps"] == 8


def test_a_re_run_pass_counts_every_run():
    # fx-re-run-passes re-ran correctness, edge-cases and provenance.
    # edge-cases: three reviews (2 + 1), three fix_dispatched, runs'
    # fix_iterations 2 + 1.
    lenses = _row("fx-re-run-passes")["lenses"]
    assert (lenses["edge-cases"]["reviews"], lenses["edge-cases"]["fix_rounds"]) == (3, 3)
    assert (lenses["provenance"]["reviews"], lenses["provenance"]["fix_rounds"]) == (3, 2)
    # correctness 3+1, clarity 2+1, edge-cases 3+3, provenance 3+2, excellence
    # 1+0.
    assert _row("fx-re-run-passes")["sequential_steps"] == 19


def test_a_re_run_shows_in_the_dispatch_sequence():
    assert _row("fx-re-run-passes")["dispatch_sequence"] == [
        "correctness", "clarity", "edge-cases", "provenance",
        "correctness", "edge-cases", "provenance",
    ]


def test_a_combined_pass_is_counted_once():
    # fx-combined-pass reviewed clarity and edge-cases as one pass,
    # "clarity+edge-cases", yet completed_passes lists both. One review and one
    # fix, counted there.
    row = _row("fx-combined-pass")
    assert row["lens_order"] == ["correctness", "clarity+edge-cases", "provenance", "excellence"]
    assert (row["lenses"]["clarity+edge-cases"]["reviews"], row["lenses"]["clarity+edge-cases"]["fix_rounds"]) == (1, 1)
    # correctness 1+1, combined 1+1, provenance 1+0, excellence 1+0.
    assert row["sequential_steps"] == 6


def test_lens_order_follows_first_appearance_not_the_roster():
    # fx-dry-run-with-other-bucket has no pass_started for correctness, which
    # nonetheless ran first.
    assert _row("fx-dry-run-with-other-bucket")["lens_order"][0] == "correctness"


def test_first_review_findings_are_never_below_the_logged_severities():
    # Some passes counted only blocking findings in findings_count_initial:
    # fx-blocking-only-initial-count records 0 everywhere but logged MINORs
    # (1/5/3/2).
    lenses = _row("fx-blocking-only-initial-count")["lenses"]
    assert [lenses[k]["findings_first_review"] for k in ("correctness", "clarity", "edge-cases", "provenance")] == [1, 5, 3, 2]


def test_a_re_sent_dispatch_counts_as_a_review():
    # fx-stall-and-resend, correctness: three reviewer_dispatched, two
    # findings_received (a stalled dispatch was re-sent).
    assert _row("fx-stall-and-resend")["lenses"]["correctness"]["reviews"] == 3


def test_a_pass_started_but_never_reviewed_is_not_a_lens_run():
    record = {"completed_passes": [], "audit_trail": [{"event": "pass_started", "pass": "clarity"}]}
    row = r5_baseline.analyse_record(record)
    assert row["lenses"] == {} and row["lens_order"] == [] and row["sequential_steps"] == 0


# The two fixtures modelling BLOCKED_DISPATCHES: a dispatch the hook refused,
# so no review came of it (one refused after launch, one before). Hand counts from each one's events, per lens
# reviews + fix rounds:
#   fx-blocked-dispatch-after-launch
#       correctness 2+1 (3 dispatched, 1 blocked), clarity 4+2 (a real stall
#       re-sent), edge-cases 3+3, provenance 3+3, excellence 1.
#   fx-blocked-dispatch-before-launch
#       correctness 2+1 (3 dispatched, 1 blocked), clarity 2+1,
#       edge-cases 2+1, provenance 5+4, excellence 1.
@pytest.mark.parametrize(("name", "steps", "correctness_reviews"), [
    ("fx-blocked-dispatch-after-launch", 22, 2),
    ("fx-blocked-dispatch-before-launch", 19, 2),
])
def test_a_dispatch_the_hook_blocked_is_not_a_model_step(name, steps, correctness_reviews):
    row = _row(name)
    assert row["lenses"]["correctness"]["reviews"] == correctness_reviews
    assert row["sequential_steps"] == steps


def test_a_gate_with_no_lens_reviewed_is_not_counted():
    # fx-abandoned-unreviewed stops after pass_started (status in_progress).
    row = _row("fx-abandoned-unreviewed")
    assert row["lenses"] == {} and row["sequential_steps"] == 0
    assert row not in r5_baseline.baseline_rows([row])


def test_only_excluded_records_is_a_usage_error_not_a_crash(tmp_path):
    shutil.copy(FIXTURES / "r5-state-fx-dry-run-with-other-bucket-completed.json", tmp_path)
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2


# Shapes no archive has today, so these probes are hand-built: each must be
# refused, since counting it would print a plausible wrong total.
@pytest.mark.parametrize("record", [
    # round records (6kqs.4) whose rounds[] is not what audit_trail derives:
    {"rounds": [{"n": 1}], "audit_trail": []},  # stale or hand-edited
    {"rounds": [], "audit_trail": [],  # a pass with no reviewer: build refuses
     "completed_passes": [{"name": "correctness", "fix_iterations": 0}]},
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
    # fx-passless-fix-events logged the scoped(correctness+edge) re-check's
    # fix_dispatched and fixes_applied with no pass (PASSLESS_EVENTS): one
    # review, one fix round.
    lens = _row("fx-passless-fix-events")["lenses"]["scoped(correctness+edge)"]
    assert (lens["reviews"], lens["fix_rounds"]) == (1, 1)


def test_a_non_counting_event_without_a_pass_is_ignored():
    # supervisor_started, commit_made and the like carry no pass in real
    # records.
    record = {"completed_passes": [], "audit_trail": [{"event": "supervisor_started"}]}
    assert r5_baseline.analyse_record(record)["lenses"] == {}


@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe\x00"])
def test_an_unreadable_archive_is_refused(tmp_path, content):
    (tmp_path / "r5-state-bad-completed.json").write_bytes(content)
    with pytest.raises(r5_baseline.RecordError):
        r5_baseline.load_records(tmp_path)
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2


def test_a_re_run_s_fixes_come_from_its_runs_when_events_and_summary_hold_one():
    # fx-re-run-fixes-only-in-runs, provenance: ran twice, each pass_completed
    # fix_iterations 1, but logged one fix_dispatched and its summary holds the
    # last run's 1.
    lens = _row("fx-re-run-fixes-only-in-runs")["lenses"]["provenance"]
    assert (lens["reviews"], lens["fix_rounds"]) == (4, 2)


def test_totals_take_the_first_review_s_severities_and_count_re_reviews_apart():
    # fx-v2-per-review-severities' findings_received, first review then the
    # rest, per lens:
    #   correctness 0/1/3 then 0/1/0, 0/0/1; clarity 0/2/9 then 0/0/1;
    #   edge-cases 0/1/6 then 0/0/1; provenance 3/1/1 then 0/1/0, 0/0/1;
    #   excellence (advisory) 0/0/4.
    t = r5_baseline.totals([_row("fx-v2-per-review-severities")])
    first = {k: (v["critical"], v["important"], v["minor"]) for k, v in t.items()}
    assert first == {
        "correctness": (0, 1, 3), "clarity": (0, 2, 9), "edge-cases": (0, 1, 6),
        "provenance": (3, 1, 1), "excellence": (0, 0, 4),
    }
    assert {k: v["rereview_findings"] for k, v in t.items()} == {
        "correctness": 2, "clarity": 1, "edge-cases": 1, "provenance": 2, "excellence": 0,
    }


def test_passes_outside_the_roster_fold_into_one_row():
    # fx-combined-pass's "clarity+edge-cases" review: first review 0/1/5.
    folded = r5_baseline.fold_other_passes(r5_baseline.totals([_row("fx-combined-pass")]))
    assert "clarity+edge-cases" not in folded
    other = folded["other passes"]
    assert (other["critical"], other["important"], other["minor"], other["records"]) == (0, 1, 5, 1)


def test_step_stats_use_a_true_median():
    # The eight gates whose steps are hand-counted above: 17, 8, 24, 6, 19, 8,
    # 22, 19. An even count, so the median is the mean of the middle two.
    names = ["fx-v2-per-review-severities", "fx-v1-totals-only", "fx-v1-fix-loops", "fx-combined-pass", "fx-re-run-passes", "fx-blocking-only-initial-count", "fx-blocked-dispatch-after-launch", "fx-blocked-dispatch-before-launch"]
    assert r5_baseline.step_stats([_row(n) for n in names]) == {"total": 123, "median": 18, "max": 24}


def test_the_published_table_folds_other_passes_and_follows_the_roster():
    # What docs/r5-gate.md publishes, as data. The fixtures' live, reviewed
    # gates use the five roster passes plus three one-off names
    # (fx-combined-pass "clarity+edge-cases"; fx-passless-fix-events
    # "scoped(correctness+edge)" and "scoped re-check"), which the table must
    # show as one "other passes" row.
    r = r5_baseline.report([_row(p.name.removeprefix("r5-state-").removesuffix("-completed.json"))
                            for p in sorted(FIXTURES.glob("*.json"))])
    assert [row[0] for row in r["table"]] == [
        "correctness", "clarity", "edge-cases", "provenance", "excellence", "other passes",
    ]
    assert (r["excluded_dry_runs"], r["excluded_unreviewed"]) == (1, 1)
    # 13 fixtures less fx-dry-run-with-other-bucket and
    # fx-abandoned-unreviewed; all 12 have a reviewed correctness pass. With
    # the exclusions skipped, either number would rise.
    assert r["records"] == 12
    # Two of those are checkpoints of one bead (fx-passless-fix-events and
    # fx-re-run-passes share fx-checkpointed-bead), as checkpointed beads are.
    assert r["beads"] == 11
    assert r["table"][0][r5_baseline.TABLE_COLUMNS.index("records")] == 12
    # Every row has a cell per column, or every later value shifts left.
    assert all(len(row) == len(r5_baseline.TABLE_COLUMNS) for row in r["table"])
    # The three one-off passes, by hand from the fixtures' events:
    #   fx-combined-pass, clarity+edge-cases:
    #       1 review, 0/1/5, 1 fix (fixes_applied)
    #   fx-passless-fix-events, scoped(correctness+edge):
    #       1 review, 0/3/7, 1 fix (PASSLESS_EVENTS)
    #   fx-passless-fix-events, scoped re-check:
    #       1 review, 0/0/1, no fix
    # No summaries, so findings = severities and nothing is unattributed.
    assert r["table"][-1] == ["other passes", 3, 17, 0, 4, 13, 0, 0, 0, 3, 5]


def test_render_markdown_prints_every_report_row():
    rows = [_row("fx-v2-per-review-severities"), _row("fx-combined-pass")]
    markdown = r5_baseline.render_markdown(rows)
    report = r5_baseline.report(rows)
    body = [line for line in markdown.splitlines() if line.startswith("| ") and "---" not in line][1:]
    assert len(body) == len(report["table"])
    # The step statistics line: each value the report holds is printed.
    stats_line = [line for line in markdown.splitlines() if line.startswith("Sequential model steps")]
    assert len(stats_line) == 1
    assert all(f"{v:g}" in stats_line[0] for v in report["steps"].values())


def test_every_known_data_entry_matches_a_fixture_event():
    rows = [_row(p.name.removeprefix("r5-state-").removesuffix("-completed.json"))
            for p in sorted(FIXTURES.glob("*.json"))]
    assert r5_baseline.unmatched_table_entries(rows) == []


def test_a_directory_without_a_key_s_bead_is_a_subset_not_an_error():
    rows = [_row("fx-v1-totals-only")]
    assert r5_baseline.unmatched_table_entries(rows) == []


def test_a_mistyped_key_for_a_bead_that_is_present_is_refused(tmp_path, monkeypatch):
    # The key's ts is off by a second, inside the record's span: the blocked
    # dispatch would count as a review. main() must refuse, not print a table.
    bead, lens, ts = sorted(SYNTHETIC_BLOCKED_DISPATCHES)[0]
    typo = ts.replace(":03Z", ":04Z")
    assert typo != ts
    monkeypatch.setattr(r5_baseline, "BLOCKED_DISPATCHES", frozenset({(bead, lens, typo)}))
    shutil.copy(FIXTURES / f"r5-state-{bead}-completed.json", tmp_path)
    rows = [r5_baseline.analyse_record(json.loads(p.read_text())) for p in tmp_path.glob("*.json")]
    assert r5_baseline.unmatched_table_entries(rows) == [(bead, lens, typo)]
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2


def test_another_checkpoint_of_the_key_s_bead_is_a_subset_not_an_error(tmp_path):
    # fx-checkpointed-bead has two records; its PASSLESS_EVENTS keys fall in
    # fx-passless-fix-events (2000-01-01), not in fx-re-run-passes (2000-01-02).
    # A directory holding only the latter is a subset: no refusal.
    shutil.copy(FIXTURES / "r5-state-fx-re-run-passes-completed.json", tmp_path)
    rows = [r5_baseline.analyse_record(json.loads(p.read_text())) for p in tmp_path.glob("*.json")]
    assert r5_baseline.unmatched_table_entries(rows) == []
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 0


def test_a_key_with_an_unparseable_ts_for_a_present_bead_is_refused(monkeypatch):
    bead, lens, _ts = sorted(SYNTHETIC_BLOCKED_DISPATCHES)[0]
    bad = (bead, lens, "2000-01-1T00:00:03Z")  # a dropped digit
    monkeypatch.setattr(r5_baseline, "BLOCKED_DISPATCHES", frozenset({bad}))
    assert r5_baseline.unmatched_table_entries([_row(bead)]) == [bad]


def test_a_round_record_reads_as_its_old_record_does():
    """Bead 4: r5_baseline reads old and new archives alike. A record built
    by r5_record (rounds[] added, every old field kept) gives the same row
    as the record it was built from. fx-clarity-advisory is the live
    three-pass shape, the one gates now write."""
    sys.path.insert(0, str(HERE.parent / "scripts"))
    import r5_record

    record = json.loads((FIXTURES / "r5-state-fx-clarity-advisory-completed.json").read_text())
    built = r5_record.build(record)
    assert built["rounds"], "the fixture must derive rounds, or this compares nothing"
    old, new = r5_baseline.analyse_record(record), r5_baseline.analyse_record(built)
    # The same counts; only the source a round record's counts came from
    # differs (opensrm-6kqs.14). This fixture has no blocked dispatch, so
    # rounds[] and audit_trail agree on every count.
    assert {lens: row["steps_source"] for lens, row in new["lenses"].items()} == {
        lens: "rounds" for lens in old["lenses"]
    }
    for row in (*old["lenses"].values(), *new["lenses"].values()):
        del row["steps_source"]
    assert new == old


# Round records (opensrm-6kqs.14). Hand-built, not fixture files: they are
# audit trails r5-supervise writes today (SKILL.md "Audit trail": event names
# reviewer_dispatched, reviewer_dispatch_blocked, reviewer_unavailable,
# findings_received, fixes_applied, commit_made, pass_completed), turned into
# rounds[] by r5_record.build, as the supervisor does at archive time (spec
# section 6, "Round record"). Every expected count is read off the events.
def _round_record(bead: str, trail: list, passes: list) -> dict:
    sys.path.insert(0, str(HERE.parent / "scripts"))
    import r5_record

    events = [{"ts": f"2000-01-01T00:00:{i:02d}Z", **e} for i, e in enumerate(trail)]
    return r5_record.build({
        "supervisor": "r5-supervise", "version": 2, "target_bead": bead,
        "started_at": "2000-01-01T00:00:00Z", "dry_run": False, "status": "completed",
        "completed_passes": passes, "audit_trail": events,
    })


def _review(lens: str, counts: dict | None = None, *, dispatches: int = 1) -> list:
    sent = [{"event": "reviewer_dispatched", "pass": lens}]
    # Step 3: a dispatch the hook refuses logs reviewer_dispatch_blocked (Rob's
    # ruling, 2026-11-13: supervisor_blocked means the run paused, not this).
    blocked = [{"event": "reviewer_dispatch_blocked", "pass": lens}]
    return (sent + blocked) * (dispatches - 1) + sent + [
        {"event": "findings_received", "pass": lens, "counts": counts or {}}]


def _fix(lens: str) -> list:
    return [{"event": "fixes_applied", "pass": lens},
            {"event": "commit_made", "sha": "abc1234"}]


def test_a_round_record_does_not_count_a_dispatch_the_hook_refused():
    # The ir5m / 6kqs.2 shape, before STEP3_CUTOFF (the event rule):
    # reviewer_dispatched logged before launch, the hook refuses the Agent
    # call, reviewer_dispatch_blocked, the same iteration re-sent. No reviewer
    # ran for the first dispatch, and BLOCKED_DISPATCHES holds no key for it.
    # (6kqs.4 logs supervisor_blocked instead: the table test below.)
    # correctness: review (2 dispatches, 1 reviewer), fix, verify = 2 reviews,
    # 1 fix round. edge-cases: one review, clean.
    trail = [
        {"event": "pass_started", "pass": "correctness"},
        *_review("correctness", {"important": 1}, dispatches=2),
        *_fix("correctness"),
        *_review("correctness"),
        {"event": "pass_completed", "pass": "correctness", "fix_iterations": 1},
        {"event": "pass_started", "pass": "edge-cases"},
        *_review("edge-cases"),
        {"event": "pass_completed", "pass": "edge-cases", "fix_iterations": 0},
    ]
    record = _round_record("fx-round-hook-refused", trail, [
        {"name": "correctness", "findings_count_initial": 1, "fix_iterations": 1},
        {"name": "edge-cases", "findings_count_initial": 0, "fix_iterations": 0},
    ])
    row = r5_baseline.analyse_record(record)
    correctness = row["lenses"]["correctness"]
    assert (correctness["reviews"], correctness["fix_rounds"], correctness["steps"]) == (2, 1, 3)
    assert correctness["steps_source"] == "rounds"
    # Severities still come from findings_received, one entry per review.
    assert [r["important"] for r in correctness["findings_by_review"]] == [1, 0]
    # edge-cases, with the schema's edge_cases key in rounds[], keeps its name.
    assert row["lenses"]["edge-cases"]["reviews"] == 1
    assert row["lenses"]["edge-cases"]["steps_source"] == "rounds"
    assert row["sequential_steps"] == 4


def test_a_round_record_does_not_count_a_dispatch_a_table_row_refuses(monkeypatch):
    # The 6kqs.4 archive's shape: reviewer_dispatched logged before launch, the
    # hook refuses the Agent call, the run logs supervisor_blocked (not
    # reviewer_dispatch_blocked), the same iteration is re-sent. Only the
    # history-only KNOWN_REFUSED table marks it refused (Rob's ruling,
    # 2026-11-13). The row here is synthetic, keyed like the real 6kqs.4 row
    # (bead, schema lens, the dispatch ts as logged), as the BLOCKED_DISPATCHES
    # fixture above is.
    trail = [
        {"event": "pass_started", "pass": "correctness"},
        {"event": "reviewer_dispatched", "pass": "correctness"},
        {"event": "supervisor_blocked", "pass": "correctness",
         "reason": "parallel-block hook refused the dispatch"},
        {"event": "reviewer_dispatched", "pass": "correctness"},
        {"event": "findings_received", "pass": "correctness", "counts": {}},
        {"event": "pass_completed", "pass": "correctness", "fix_iterations": 0},
    ]
    passes = [{"name": "correctness", "findings_count_initial": 0, "fix_iterations": 0}]
    # Without the row, supervisor_blocked is a pause, not a refusal: a stall.
    unlisted = _round_record("fx-round-table-refused", trail, passes)
    assert r5_baseline.analyse_record(unlisted)["lenses"]["correctness"]["reviews"] == 2
    monkeypatch.setattr(r5_baseline.r5_record, "KNOWN_REFUSED", {
        ("fx-round-table-refused", "correctness", "2000-01-01T00:00:01Z"): {
            "reason": "hook refused the launch", "evidence": "synthetic"}})
    record = _round_record("fx-round-table-refused", trail, passes)
    assert r5_baseline.r5_record.refused_dispatches(record) == [
        ("correctness", "2000-01-01T00:00:01Z", "table")]
    correctness = r5_baseline.analyse_record(record)["lenses"]["correctness"]
    assert (correctness["reviews"], correctness["fix_rounds"]) == (1, 0)
    assert correctness["steps_source"] == "rounds"


def test_a_round_record_counts_an_unavailable_reviewer_as_a_review():
    # reviewer_unavailable (SKILL.md: the parser refused the report, the same
    # brief is re-sent once). A reviewer ran: a model step, as the audit-trail
    # path counts it through its dispatch. Then the hook refuses the retry's
    # first dispatch. So: dispatched, unavailable, dispatched, blocked,
    # dispatched, findings = 2 reviews, no fix.
    trail = [
        {"event": "pass_started", "pass": "correctness"},
        {"event": "reviewer_dispatched", "pass": "correctness"},
        {"event": "reviewer_unavailable", "pass": "correctness"},
        *_review("correctness", dispatches=2),
        {"event": "pass_completed", "pass": "correctness", "fix_iterations": 0},
    ]
    record = _round_record("fx-round-unavailable", trail, [
        {"name": "correctness", "findings_count_initial": 0, "fix_iterations": 0},
    ])
    assert [r["lenses"]["correctness"]["status"] for r in record["rounds"]] == ["UNAVAILABLE", "ok"]
    correctness = r5_baseline.analyse_record(record)["lenses"]["correctness"]
    assert (correctness["reviews"], correctness["fix_rounds"]) == (2, 0)
    assert correctness["steps_source"] == "rounds"


def test_a_round_record_counts_a_commit_only_fix_round():
    # A MINOR fixed in passing with no re-review (r5_record's docstring: a
    # commit_made after a review with no fixes_applied opens a fix round;
    # section 6: each fix is one). fix_iterations is 0, and the audit trail
    # has no fix event, so only rounds[] shows the fix: 1 review + 1 fix.
    trail = [
        {"event": "pass_started", "pass": "correctness"},
        *_review("correctness", {"minor": 1}),
        {"event": "commit_made", "sha": "abc1234"},
        {"event": "pass_completed", "pass": "correctness", "fix_iterations": 0},
    ]
    record = _round_record("fx-round-commit-only-fix", trail, [
        {"name": "correctness", "findings_count_initial": 1, "fix_iterations": 0},
    ])
    correctness = r5_baseline.analyse_record(record)["lenses"]["correctness"]
    assert (correctness["reviews"], correctness["fix_rounds"], correctness["steps"]) == (1, 1, 2)


def test_a_round_record_reviewing_a_lens_its_audit_trail_does_not_is_refused(tmp_path):
    # A reviewer_unavailable with no dispatch before it is a round of its own
    # in rounds[], but the audit-trail path finds no review of that lens (no
    # findings_received, no dispatch, no summary). The two disagree on which
    # lenses ran, so the record is refused rather than counted either way.
    trail = [
        *_review("correctness"),
        {"event": "reviewer_unavailable", "pass": "provenance"},
    ]
    record = _round_record("fx-round-lens-mismatch", trail, [])
    assert [next(iter(r["lenses"])) for r in record["rounds"]] == ["correctness", "provenance"]
    with pytest.raises(r5_baseline.RecordError, match="rounds"):
        r5_baseline.analyse_record(record)
    (tmp_path / "r5-state-probe-completed.json").write_text(json.dumps(record))
    assert r5_baseline.main(["--archive-dir", str(tmp_path)]) == 2


def test_a_round_record_counts_a_stalled_re_sent_review():
    # A reviewer dispatched, then re-sent with no reviewer_dispatch_blocked
    # between (archives bnal, t4rd: the first
    # reviewer ran and stalled). The audit-trail path counts both dispatches;
    # rounds[] must too: an UNAVAILABLE round plus the answered one.
    trail = [
        {"event": "pass_started", "pass": "correctness"},
        {"event": "reviewer_dispatched", "pass": "correctness"},
        *_review("correctness"),
        {"event": "pass_completed", "pass": "correctness", "fix_iterations": 0},
    ]
    record = _round_record("fx-round-stall", trail, [
        {"name": "correctness", "findings_count_initial": 0, "fix_iterations": 0},
    ])
    assert [r["lenses"]["correctness"]["status"] for r in record["rounds"]] == ["UNAVAILABLE", "ok"]
    correctness = r5_baseline.analyse_record(record)["lenses"]["correctness"]
    assert (correctness["reviews"], correctness["fix_rounds"]) == (2, 0)
    assert correctness["steps_source"] == "rounds"


def test_a_round_record_naming_one_lens_two_ways_is_refused():
    # edge-cases (SKILL.md's pass name) and edge_cases (the schema's, D4) are
    # one lens in rounds[]; two audit-trail rows for it cannot share one count.
    trail = [*_review("edge-cases"), *_review("edge_cases")]
    record = _round_record("fx-round-two-names", trail, [])
    with pytest.raises(r5_baseline.RecordError, match="fewer schema lenses"):
        r5_baseline.analyse_record(record)
