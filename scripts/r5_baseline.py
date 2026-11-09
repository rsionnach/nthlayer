#!/usr/bin/env python3
"""Baseline of the sequential R5 gate, from its archived records.

Reads every ``r5-state-*-completed.json`` in the workspace's ``.claude/`` and
reports, per bead and per lens: reviews, findings by severity per review, model
steps on the critical path, and the lens order used. This is requirement R5-R0
of the R5 Gate v2 spec (opensrm-6kqs.1; nthlayer/docs/superpowers/specs/
2026-11-03-r5-gate-v2-nthlayer-spec.md section 3). The gate is moving to
cúramóir, the ecosystem's separate review tool, whose batched gate is measured
against these totals: the same or better catch rate in no more than a third of
``sequential_steps``.

Two sources in each record, and why both are read:

- ``audit_trail`` ``findings_received`` events carry severities, one event per
  review. These give the severity columns.
- ``completed_passes[].findings_count_initial`` is the pass's first-review
  total. Many older passes recorded only this total, with the severities in
  free text or nowhere, so it can exceed the first review's severity sum. The
  excess is reported as ``unattributed``, never guessed. Others counted only
  blocking findings in it, so a pass's first-review count is the larger of the
  two, and the columns add up: findings = severities + unattributed.

The gate description's 2026-08-28 table summed the first-review totals in its
findings column (274) but every review's logged severities in its severity
columns (152), re-reviews included. Here the severity columns are the first
review's and re-reviews are reported apart.

Model steps, per pass, are reviews plus fix rounds:

- reviews: one per ``findings_received`` event, or per ``reviewer_dispatched``
  where more were sent than answered (less the known BLOCKED_DISPATCHES);
  failing those, each run's fix iterations plus one, from ``pass_completed``
  events, then from the pass summary.
- fix rounds: the largest of the ``fixes_applied``/``fix_dispatched`` event
  counts, the runs' ``fix_iterations`` summed, and the summary's.

A pass reviewed under a combined name ("clarity+edge-cases") is counted once,
there. The sequential gate runs passes one after another, so the critical path
is the sum over every pass, advisory excellence included. ``steps_source`` says
which derivation each pass used.

A known-data entry that falls within a record here (same bead, inside its
audit trail's time span) but matches none of its events is refused (exit 2),
since a mistyped key would miscount silently.

``--json`` prints one object, ``schema_version`` 1 (JSON_SCHEMA_VERSION), read
by the replay corpus (scripts/r5_corpus.py, opensrm-6kqs.2):

- ``records``: one row per archive, by file name, each with ``counted`` (false
  for a dry run or a gate with no lens reviewed: listed, never totalled),
  ``table_hits`` (the BLOCKED_DISPATCHES and PASSLESS_EVENTS keys it used) and
  ``ts_span`` (its audit trail's first and last timestamps, as ISO 8601 in UTC,
  ``+00:00``; null with no timestamped event).
- ``beads``: per bead, its counted records and ``sequential_steps``. A bead
  gated at several checkpoints, or in several repos one gate at a time, has
  one record each, run one after another, so its steps are their sum.
- ``totals``: per lens over the counted records, as the table.
- ``summary``: the table's data (report()): header counts, schema versions by
  value, table rows and per-gate step statistics.

Like ``eco_doctor.py`` this depends on nothing in the ecosystem: the standard
library only.

Usage:
    python3 scripts/r5_baseline.py [--archive-dir DIR] [--json | --markdown]

Exit codes: 0 report printed · 2 any one of these: a usage error, no countable
record, a record it cannot count without guessing, or a known-data entry that
matches nothing. One fails the whole report: a baseline quietly missing a gate
would look as plausible as a correct one.
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

# The --json contract version; raised when a field changes meaning or goes.
JSON_SCHEMA_VERSION = 1

SEVERITIES = ("critical", "important", "minor")
# Blocking lenses in roster order, then the advisory one. A lens a record names
# that is not here (none today) sorts after these, by name.
LENS_ORDER = ("correctness", "clarity", "edge-cases", "provenance", "excellence")

# Archived reviewer_dispatched events for which no reviewer ran: the hook
# refused the launch and the supervisor re-dispatched the same iteration. A
# blocked dispatch is not a model step, but the archived state format cannot
# tell one from a stalled review that was re-sent (wo62-4-2 logs a real stall
# under the same event names), so the two known cases are listed here, keyed by
# (bead, pass, ts), rather than inferred from free text. The archives are
# frozen; Phase A.4's round record (opensrm-6kqs.4) records dispatches exactly,
# so no entry is added for gates run after it. Found by the opensrm-6kqs.1 R5
# correctness pass, iteration 3.
BLOCKED_DISPATCHES = frozenset({
    # reviewer_dispatch_blocked follows: the supervisor's own bookkeeping
    # tripped the parallel-block hook; iteration 2 re-dispatched at 21:34:23Z.
    ("opensrm-ir5m", "correctness", "2026-10-02T21:32:57Z"),
    # supervisor_blocked follows: the dispatch was logged before launch and the
    # hook refused it; iteration 1 re-dispatched at 17:10:43.
    ("opensrm-wo62.4.1", "correctness", "2026-10-27T17:10:18.968444+00:00"),
})

# Archived counting events logged without a ``pass``, mapped to the pass they
# belong to. Any other counting event with no string ``pass`` is refused, as
# guessing its pass is the silent miscount this script exists to avoid; these
# two are known data, as BLOCKED_DISPATCHES are. Found by the opensrm-6kqs.1 R5
# edge-cases pass, iteration 2.
PASSLESS_EVENTS = {
    # The fix after the scoped(correctness+edge) re-check, dispatched and then
    # applied; the preceding findings_received is that pass's.
    ("opensrm-g32d", "fix_dispatched", "2026-10-20T13:58:06+00:00"): "scoped(correctness+edge)",
    ("opensrm-g32d", "fixes_applied", "2026-10-20T14:04:07+00:00"): "scoped(correctness+edge)",
}

# Events that change a count. One of these without a pass cannot be placed.
COUNTING_EVENTS = frozenset({
    "pass_started", "findings_received", "advisory_pass_completed", "fixes_applied",
    "fix_dispatched", "pass_completed", "reviewer_dispatched",
})

# scripts/ -> the front-door repo -> the workspace root, whose .claude/ holds
# the archives (they are untracked, so they cannot live in this repo).
DEFAULT_ARCHIVE_DIR = Path(__file__).resolve().parents[2] / ".claude"


class RecordError(ValueError):
    """An archive this script cannot count without guessing."""


def _count(value: object, what: str) -> int:
    """A non-negative integer count. Anything else is refused rather than read
    as 0, which would undercount silently. Every archive writes integers."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecordError(f"{what} is {value!r}, not a non-negative count")
    return value


def _counts(raw: object) -> Counter:
    """Severity counts from one findings_received ``counts`` value.

    Keys outside SEVERITIES (``missing_tests`` in one edge-cases record) go to
    ``other``. A missing or null ``counts`` is no findings.
    """
    out: Counter = Counter()
    if raw is None:
        return out
    if not isinstance(raw, dict):
        raise RecordError(f"counts is {raw!r}, not a mapping")
    for key, value in raw.items():
        out[key if key in SEVERITIES else "other"] += _count(value, f"counts[{key!r}]")
    return out


def _lens_sort_key(lens: str) -> tuple[int, str]:
    return (LENS_ORDER.index(lens), "") if lens in LENS_ORDER else (len(LENS_ORDER), lens)


def _combined_pass_covers(event_lens: str, lens: str) -> bool:
    """Whether a combined pass name such as "clarity+edge-cases" or
    "scoped(correctness+edge)" covers ``lens``: the record logged one review for
    both, so the lens's own summary must not add a second."""
    parts = event_lens.replace("(", "+").replace(")", "+").split("+")
    return event_lens != lens and any(
        part and (part == lens or lens.startswith(part + "-")) for part in parts
    )


def _scan_events(record: dict) -> dict:
    """Everything the per-lens derivation needs from the audit trail, by lens."""
    scan: dict = {
        "reviews": {},  # lens -> severity Counter per review
        "fix_events": {},  # lens -> Counter of fixes_applied / fix_dispatched
        "runs": {},  # lens -> fix_iterations of each pass_completed
        "dispatched": Counter(),  # lens -> reviewer_dispatched, less BLOCKED_DISPATCHES
        "seen": [],  # first appearance of each pass in any event
        "sequence": [],  # pass_started in order, repeats kept
        "table_hits": [],  # BLOCKED_DISPATCHES / PASSLESS_EVENTS keys used
    }
    advisory: dict[str, list[Counter]] = {}
    for event in record.get("audit_trail") or []:
        if not isinstance(event, dict):
            raise RecordError(f"audit_trail entry {event!r} is not an object")
        kind = event.get("event")
        lens = event.get("pass")
        if not isinstance(lens, str):
            key = (record.get("target_bead"), kind, event.get("ts"))
            lens = PASSLESS_EVENTS.get(key)
            if lens is not None:
                scan["table_hits"].append(key)
        if lens is None:
            if kind in COUNTING_EVENTS:
                raise RecordError(
                    f"{kind} at {event.get('ts')} has no pass: if its pass is known,"
                    " add it to PASSLESS_EVENTS in scripts/r5_baseline.py, keyed"
                    " (bead, event, ts)"
                )
            continue
        if lens not in scan["seen"]:
            scan["seen"].append(lens)
        if kind == "pass_started":
            scan["sequence"].append(lens)
        elif kind == "findings_received":
            scan["reviews"].setdefault(lens, []).append(_counts(event.get("counts")))
        elif kind == "advisory_pass_completed":
            # The advisory read is one review with no fix loop; v2 records log
            # it here rather than as findings_received. Used only for a lens
            # with no findings_received of its own, so it is never counted twice.
            advisory.setdefault(lens, []).append(_counts(event.get("counts")))
        elif kind in ("fixes_applied", "fix_dispatched"):
            scan["fix_events"].setdefault(lens, Counter())[kind] += 1
        elif kind == "pass_completed" and event.get("fix_iterations") is not None:
            scan["runs"].setdefault(lens, []).append(
                _count(event["fix_iterations"], f"{lens} pass_completed fix_iterations")
            )
        elif kind == "reviewer_dispatched":
            key = (record.get("target_bead"), lens, event.get("ts"))
            if key in BLOCKED_DISPATCHES:
                scan["table_hits"].append(key)
            else:
                scan["dispatched"][lens] += 1
    for lens, found in advisory.items():
        scan["reviews"].setdefault(lens, found)
    return scan


def _lens_row(lens: str, summary: dict, scan: dict) -> dict | None:
    """One lens's row, or None for a lens started but never reviewed."""
    found = scan["reviews"].get(lens, [])
    runs = scan["runs"].get(lens)
    raw_fixes = summary.get("fix_iterations")
    summary_fixes = 0 if raw_fixes is None else _count(raw_fixes, f"{lens} fix_iterations")
    if found:
        # A dispatch that stalled and was re-sent is a review spent with no
        # findings_received of its own.
        reviews, source = max(len(found), scan["dispatched"][lens]), "events"
    elif runs:
        reviews, source = sum(n + 1 for n in runs), "pass_completed"
    elif summary:
        reviews, source = summary_fixes + 1, "pass_summary"
    else:
        reviews, source = scan["dispatched"][lens], "dispatched"
    if reviews == 0:
        return None  # started, never reviewed: no step, and not a lens run
    # A fix that no re-review followed leaves fix_iterations at 0, and a re-run
    # pass's summary holds one run only, so take the largest of the three ways
    # a record shows fix rounds.
    fixes = max(
        max(scan["fix_events"].get(lens, Counter()).values(), default=0),
        sum(runs or []),
        summary_fixes,
    )
    first = sum(found[0].values()) if found else 0
    recorded = summary.get("findings_count_initial")
    recorded = first if recorded is None else _count(recorded, f"{lens} findings_count_initial")
    return {
        "reviews": reviews,
        "fix_rounds": fixes,
        "findings_by_review": [{s: c[s] for s in (*SEVERITIES, "other")} for c in found],
        "recorded_initial": recorded,
        # Some passes counted only blocking findings in findings_count_initial
        # (0 with only MINORs), others every one, so the first review's count
        # is whichever of the two sources is larger.
        "findings_first_review": max(recorded, first),
        "unattributed": max(0, recorded - first),
        "steps": reviews + fixes,
        "steps_source": source,
    }


def analyse_record(record: dict) -> dict:
    """The baseline row for one archived gate record.

    Raises RecordError for a shape it does not read: a ``rounds[]`` record (the
    Phase A.4 round record, which this script must learn before it can count
    one) or a record with neither ``audit_trail`` nor ``completed_passes``.
    Counting either as a gate with no reviews would be a plausible wrong total.
    """
    if not isinstance(record, dict):
        raise RecordError("not a JSON object")
    if "rounds" in record:
        raise RecordError(
            "has rounds[] (round record): not yet read by this script; teach"
            " analyse_record the Phase A.4 shape (opensrm-6kqs.4) first"
        )
    if "audit_trail" not in record and "completed_passes" not in record:
        raise RecordError("has neither audit_trail nor completed_passes")
    for key in ("audit_trail", "completed_passes"):
        if record.get(key) is not None and not isinstance(record[key], list):
            raise RecordError(f"{key} is a {type(record[key]).__name__}, not a list")
    passes = record.get("completed_passes") or []
    for p in passes:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str):
            raise RecordError(f"completed_passes entry {p!r} has no name")
    summaries = {p["name"]: p for p in passes}
    scan = _scan_events(record)

    # Lens order: first appearance in the audit trail, which follows dispatch;
    # lenses that appear only in completed_passes follow, in that order.
    order = scan["seen"] + [name for name in summaries if name not in scan["seen"]]
    lenses = {}
    for lens in order:
        if lens not in scan["reviews"] and any(
            _combined_pass_covers(other, lens) for other in scan["reviews"]
        ):
            continue  # reviewed under a combined pass, counted there
        row = _lens_row(lens, summaries.get(lens, {}), scan)
        if row is not None:
            lenses[lens] = row
    sequence = scan["sequence"] or order
    return {
        "bead": record.get("target_bead"),
        "version": record.get("version", 1),
        "started_at": record.get("started_at"),
        "dry_run": bool(record.get("dry_run")),
        "lens_order": [lens for lens in order if lens in lenses],
        "dispatch_sequence": [lens for lens in sequence if lens in lenses],
        "lenses": lenses,
        "sequential_steps": sum(v["steps"] for v in lenses.values()),
        "table_hits": [list(key) for key in scan["table_hits"]],
        "ts_span": _span(record),
    }


def _instant(ts: object) -> datetime.datetime | None:
    """An archive timestamp as an aware datetime, or None if it is not one. The
    archives mix "Z" and "+00:00" and fractional seconds, so strings cannot be
    compared as they stand."""
    if not isinstance(ts, str):
        return None
    try:
        # "Z" by hand: fromisoformat only reads it from Python 3.11, and the
        # workspace shim runs the system python3.
        moment = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    # timezone.utc, not datetime.UTC (3.11+): the shim runs the system python3.
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.timezone.utc)  # noqa: UP017


def _span(record: dict) -> list[str] | None:
    """The first and last event timestamps of a record's audit trail."""
    moments = [m for e in record.get("audit_trail") or [] if (m := _instant(e.get("ts")))]
    return [min(moments).isoformat(), max(moments).isoformat()] if moments else None


def unmatched_table_entries(rows: list[dict]) -> list[tuple]:
    """BLOCKED_DISPATCHES and PASSLESS_EVENTS keys that a record here should
    have matched but did not.

    A key belongs to the record of its bead whose audit trail spans the key's
    timestamp; a bead gated at several checkpoints has one record each. A key
    with no such record here is skipped, since the directory is a subset of the
    archive. A key with one, unmatched, is mistyped, and would silently count a
    blocked dispatch as a review, so main() refuses the report (exit 2). The
    tests cannot check the real keys, since their fixtures are synthetic; this
    check does, every time the script runs."""
    hits = {tuple(key) for row in rows for key in row["table_hits"]}

    def held_here(key: tuple) -> bool:
        moment = _instant(key[2])
        if moment is None:
            # An unparseable ts is itself a typo: refuse it if its bead is here.
            return any(row["bead"] == key[0] for row in rows)
        return any(
            row["bead"] == key[0] and row["ts_span"]
            and _instant(row["ts_span"][0]) <= moment <= _instant(row["ts_span"][1])
            for row in rows
        )

    keys = set(BLOCKED_DISPATCHES) | set(PASSLESS_EVENTS)
    return sorted((k for k in keys - hits if held_here(k)), key=str)


def load_records(archive_dir: Path) -> list[tuple[str, dict]]:
    """Every archived record, by file name, sorted by name for a stable report."""
    out = []
    for path in sorted(archive_dir.glob("r5-state-*-completed.json")):
        try:
            with path.open(encoding="utf-8") as handle:
                out.append((path.name, json.load(handle)))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RecordError(f"{path.name}: unreadable ({exc})") from exc
    return out


def totals(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Per-lens totals over all rows. Severities are the first review's, so they
    sit beside the pass totals they make up; later reviews' findings are
    ``rereview_findings``, so a residual finding re-raised is not counted twice."""
    out: dict[str, Counter] = {}
    for row in rows:
        for lens, data in row["lenses"].items():
            acc = out.setdefault(lens, Counter())
            acc["records"] += 1
            acc["recorded_initial"] += data["recorded_initial"]
            acc["findings_first_review"] += data["findings_first_review"]
            acc["unattributed"] += data["unattributed"]
            acc["reviews"] += data["reviews"]
            acc["steps"] += data["steps"]
            by_review = data["findings_by_review"]
            for sev, n in (by_review[0] if by_review else {}).items():
                acc[sev] += n  # first review only, comparable to the pass totals
            acc["rereview_findings"] += sum(sum(r.values()) for r in by_review[1:])
    return {lens: dict(out[lens]) for lens in sorted(out, key=_lens_sort_key)}


def baseline_rows(rows: list[dict]) -> list[dict]:
    """The rows the baseline counts: live gates that reviewed something. A dry
    run replays a bead already gated, so counting it would count that bead
    twice; a record with no lens reviewed (a gate abandoned after pass_started)
    would add a gate of zero steps."""
    return [r for r in rows if not r["dry_run"] and r["lenses"]]


def fold_other_passes(agg: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """The totals with every pass outside the roster (one-off re-checks such as
    "delta-clarity" or "scoped re-check") summed into one "other passes" row, as
    the table shows them; --json keeps them by name."""
    out = {lens: t for lens, t in agg.items() if lens in LENS_ORDER}
    other: Counter = Counter()
    for lens, t in agg.items():
        if lens not in LENS_ORDER:
            other.update(t)
    if other:
        out["other passes"] = dict(other)
    return out


def step_stats(rows: list[dict]) -> dict[str, float]:
    """Total, median and maximum sequential steps per gate."""
    steps = [r["sequential_steps"] for r in rows]
    return {"total": sum(steps), "median": statistics.median(steps), "max": max(steps)}


TABLE_COLUMNS = (
    "pass", "records", "findings (first review)", "CRITICAL", "IMPORTANT", "MINOR",
    "other", "unattributed", "re-review findings", "reviews", "model steps",
)


def report(all_rows: list[dict]) -> dict:
    """Everything the published table shows, as data: the header counts, one
    row per pass (TABLE_COLUMNS order, roster passes then "other passes"), and
    the per-gate step statistics. render_markdown only formats this."""
    rows = baseline_rows(all_rows)
    table = [
        [
            lens, t["records"], t["findings_first_review"], t.get("critical", 0),
            t.get("important", 0), t.get("minor", 0), t.get("other", 0),
            t["unattributed"], t.get("rereview_findings", 0), t["reviews"], t["steps"],
        ]
        for lens, t in fold_other_passes(totals(rows)).items()
    ]
    return {
        "records": len(rows),
        "beads": len({r["bead"] for r in rows}),
        "versions": schema_versions(rows),
        "excluded_dry_runs": sum(r["dry_run"] for r in all_rows),
        "excluded_unreviewed": sum(not r["dry_run"] and not r["lenses"] for r in all_rows),
        "table": table,
        "steps": step_stats(rows),
    }


def schema_versions(rows: list[dict]) -> dict[str, int]:
    """Records per schema version, by value, in version order. Keys are strings
    so the mapping survives JSON unchanged."""
    counts = Counter(str(r["version"]) for r in rows)
    return {v: counts[v] for v in sorted(counts, key=lambda v: (len(v), v))}


def bead_steps(rows: list[dict]) -> dict[str, dict]:
    """Each bead's counted records and their summed sequential steps: a bead
    gated at several checkpoints, or repo by repo, ran those gates in turn."""
    out: dict[str, dict] = {}
    for row in baseline_rows(rows):
        bead = out.setdefault(row["bead"], {"records": [], "sequential_steps": 0})
        bead["records"].append(row.get("file"))
        bead["sequential_steps"] += row["sequential_steps"]
    return dict(sorted(out.items()))


def json_report(all_rows: list[dict]) -> dict:
    """The --json object (JSON_SCHEMA_VERSION; see the module docstring)."""
    counted = {id(r) for r in baseline_rows(all_rows)}
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "records": [dict(r, counted=id(r) in counted) for r in all_rows],
        "beads": bead_steps(all_rows),
        "totals": totals(baseline_rows(all_rows)),
        "summary": report(all_rows),
    }


def render_markdown(all_rows: list[dict]) -> str:
    r = report(all_rows)
    # "20 schema v1, 66 v2", as the gate description publishes it.
    versions = ", ".join(
        f"{n} {'schema ' if i == 0 else ''}v{v}" for i, (v, n) in enumerate(r["versions"].items())
    )
    lines = [
        f"{r['records']} archived gate records, {r['beads']} beads"
        f" ({versions});"
        f" excluded: {r['excluded_dry_runs']} dry run(s),"
        f" {r['excluded_unreviewed']} with no lens reviewed.",
        "",
        "| " + " | ".join(TABLE_COLUMNS) + " |",
        "|" + "---|" * len(TABLE_COLUMNS),
    ]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in r["table"]]
    stats = r["steps"]
    lines += [
        "",
        f"Sequential model steps per gate: total {stats['total']},"
        f" median {stats['median']:g}, max {stats['max']}.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="per-record rows and totals as JSON")
    fmt.add_argument("--markdown", action="store_true", help="the totals table (default)")
    args = parser.parse_args(argv)

    if not args.archive_dir.is_dir():
        print(f"r5-baseline: no such directory {args.archive_dir}", file=sys.stderr)
        return 2
    try:
        records = load_records(args.archive_dir)
    except RecordError as exc:
        print(f"r5-baseline: {exc}", file=sys.stderr)
        return 2
    if not records:
        print(f"r5-baseline: no r5-state-*-completed.json in {args.archive_dir}", file=sys.stderr)
        return 2
    rows = []
    for name, data in records:
        try:
            rows.append(dict(analyse_record(data), file=name))
        except RecordError as exc:
            print(f"r5-baseline: {name}: {exc}", file=sys.stderr)
            return 2
    unmatched = unmatched_table_entries(rows)
    for key in unmatched:
        table = "BLOCKED_DISPATCHES" if key in BLOCKED_DISPATCHES else "PASSLESS_EVENTS"
        print(f"r5-baseline: known-data entry {key} matches no event in its bead's"
              f" record: correct it in {table} in scripts/r5_baseline.py (a mistyped"
              " key would miscount silently)", file=sys.stderr)
    if unmatched:
        return 2
    if not baseline_rows(rows):
        print(f"r5-baseline: no live, reviewed gate in {args.archive_dir}", file=sys.stderr)
        return 2
    if args.json:
        json.dump(json_report(rows), sys.stdout, indent=1)
        print()
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
