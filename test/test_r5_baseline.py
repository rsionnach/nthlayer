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
    assert len(out["records"]) == 13
    assert "fx-dry-run-with-other-bucket" not in {r["bead"] for r in r5_baseline.baseline_rows(out["records"])}


def test_json_marks_the_records_the_totals_leave_out(capsys):
    # The two excluded fixtures (a dry run; a gate abandoned before any
    # review) are listed but not counted; the other eleven are.
    out = _json_out(capsys)
    uncounted = sorted(r["file"] for r in out["records"] if not r["counted"])
    assert uncounted == [
        "r5-state-fx-abandoned-unreviewed-completed.json",
        "r5-state-fx-dry-run-with-other-bucket-completed.json",
    ]
    assert sum(r["counted"] for r in out["records"]) == 11


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
    assert len(out["beads"]) == 10


def test_json_carries_the_table_summary(capsys):
    out = _json_out(capsys)
    rows = [_row(p.name.removeprefix("r5-state-").removesuffix("-completed.json"))
            for p in sorted(FIXTURES.glob("*.json"))]
    assert out["summary"] == json.loads(json.dumps(r5_baseline.report(rows)))


def test_schema_versions_are_counted_by_value():
    # Counted fixtures: 2 of version 1 (the other two v1 files are the
    # excluded ones), 9 of version 2; read off the files' "version" fields.
    rows = [_row(p.name.removeprefix("r5-state-").removesuffix("-completed.json"))
            for p in sorted(FIXTURES.glob("*.json"))]
    assert r5_baseline.report(rows)["versions"] == {"1": 2, "2": 9}
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
    # fx-abandoned-unreviewed; all 11 have a reviewed correctness pass. With
    # the exclusions skipped, either number would rise.
    assert r["records"] == 11
    # Two of those are checkpoints of one bead (fx-passless-fix-events and
    # fx-re-run-passes share fx-checkpointed-bead), as checkpointed beads are.
    assert r["beads"] == 10
    assert r["table"][0][r5_baseline.TABLE_COLUMNS.index("records")] == 11
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
