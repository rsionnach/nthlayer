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

Like ``eco_doctor.py`` this depends on nothing in the ecosystem: the standard
library only.

Usage:
    python3 scripts/r5_baseline.py [--archive-dir DIR] [--json | --markdown]

Exit codes: 0 report printed · 2 usage error or no records found.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

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

# scripts/ -> the front-door repo -> the workspace root, whose .claude/ holds
# the archives (they are untracked, so they cannot live in this repo).
DEFAULT_ARCHIVE_DIR = Path(__file__).resolve().parents[2] / ".claude"


def _counts(raw: object) -> Counter:
    """Severity counts from one findings_received ``counts`` value.

    Keys outside SEVERITIES (``missing_tests`` in one edge-cases record) go to
    ``other``; non-integer values are ignored, as no record uses one for a count.
    """
    out: Counter = Counter()
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        out[key if key in SEVERITIES else "other"] += value
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
        "dispatched": Counter(),
        "seen": [],  # first appearance of each pass in any event
        "sequence": [],  # pass_started in order, repeats kept
    }
    advisory: dict[str, list[Counter]] = {}
    for event in record.get("audit_trail", []):
        if not isinstance(event, dict) or not isinstance(event.get("pass"), str):
            continue
        lens, kind = event["pass"], event.get("event")
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
        elif kind == "pass_completed" and isinstance(event.get("fix_iterations"), int):
            scan["runs"].setdefault(lens, []).append(event["fix_iterations"])
        elif (
            kind == "reviewer_dispatched"
            and (record.get("target_bead"), lens, event.get("ts")) not in BLOCKED_DISPATCHES
        ):
            scan["dispatched"][lens] += 1
    for lens, found in advisory.items():
        scan["reviews"].setdefault(lens, found)
    return scan


def _lens_row(lens: str, summary: dict, scan: dict) -> dict | None:
    """One lens's row, or None for a lens started but never reviewed."""
    found = scan["reviews"].get(lens, [])
    runs = scan["runs"].get(lens)
    summary_fixes = summary.get("fix_iterations") or 0
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
    if recorded is None:
        recorded = first
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
    """The baseline row for one archived gate record."""
    passes = [p for p in record.get("completed_passes", []) if isinstance(p, dict)]
    summaries = {p["name"]: p for p in passes if isinstance(p.get("name"), str)}
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
    }


def load_records(archive_dir: Path) -> list[tuple[str, dict]]:
    """Every archived record, by file name, sorted by name for a stable report."""
    out = []
    for path in sorted(archive_dir.glob("r5-state-*-completed.json")):
        with path.open(encoding="utf-8") as handle:
            out.append((path.name, json.load(handle)))
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
            its = data["findings_by_review"]
            for sev, n in (its[0] if its else {}).items():
                acc[sev] += n  # first review only, comparable to the pass totals
            acc["rereview_findings"] += sum(sum(it.values()) for it in its[1:])
    return {lens: dict(out[lens]) for lens in sorted(out, key=_lens_sort_key)}


def baseline_rows(rows: list[dict]) -> list[dict]:
    """The rows the baseline counts: live gates only. A dry run replays a bead
    already gated, so counting it would count that bead twice."""
    return [r for r in rows if not r["dry_run"]]


def render_markdown(all_rows: list[dict]) -> str:
    rows = baseline_rows(all_rows)
    agg = totals(rows)
    # Passes outside the roster (one-off re-checks such as "delta-clarity" or
    # "scoped re-check") are folded into one row here; --json
    # keeps them by name.
    other: Counter = Counter()
    for lens in [lens for lens in agg if lens not in LENS_ORDER]:
        other.update(agg.pop(lens))
    if other:
        agg["other passes"] = dict(other)
    beads = {r["bead"] for r in rows}
    lines = [
        f"{len(rows)} archived gate records, {len(beads)} beads"
        f" ({sum(r['version'] == 1 for r in rows)} schema v1,"
        f" {sum(r['version'] != 1 for r in rows)} v2;"
        f" {len(all_rows) - len(rows)} dry run(s) excluded).",
        "",
        "| pass | records | findings (first review) | CRITICAL | IMPORTANT | MINOR"
        " | other | unattributed | re-review findings | reviews | model steps |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lens, t in agg.items():
        lines.append(
            f"| {lens} | {t['records']} | {t['findings_first_review']} | {t.get('critical', 0)}"
            f" | {t.get('important', 0)} | {t.get('minor', 0)} | {t.get('other', 0)}"
            f" | {t['unattributed']} | {t.get('rereview_findings', 0)}"
            f" | {t['reviews']} | {t['steps']} |"
        )
    steps = [r["sequential_steps"] for r in rows]
    lines += [
        "",
        f"Sequential model steps per gate: total {sum(steps)},"
        f" median {sorted(steps)[len(steps) // 2]}, max {max(steps)}.",
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
    records = load_records(args.archive_dir)
    if not records:
        print(f"r5-baseline: no r5-state-*-completed.json in {args.archive_dir}", file=sys.stderr)
        return 2
    rows = [dict(analyse_record(data), file=name) for name, data in records]
    if args.json:
        json.dump({"records": rows, "totals": totals(baseline_rows(rows))}, sys.stdout, indent=1)
        print()
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
