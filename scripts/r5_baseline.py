#!/usr/bin/env python3
"""Baseline of the sequential R5 gate, from its archived records (R5-R0).

Reads every ``r5-state-*-completed.json`` in the workspace's ``.claude/`` and
reports, per bead and per lens: review iterations, findings by severity per
iteration, model steps on the critical path, and the lens order used. The
totals are the baseline cúramóir's batched gate is measured against: the same
or better catch rate in no more than a third of ``sequential_steps``
(R5 Gate v2 spec, opensrm-6kqs.1; nthlayer/docs/superpowers/specs/
2026-11-03-r5-gate-v2-nthlayer-spec.md section 3).

Two sources in each record, and why both are read:

- ``audit_trail`` ``findings_received`` events carry severities, one event per
  review iteration. These give the severity columns.
- ``completed_passes[].findings_count_initial`` is the pass's first-review
  total. Many older passes recorded only this total, with the severities in
  free text or nowhere, so it can exceed the first iteration's severity sum.
  The excess is reported as ``unattributed``, never guessed.

That difference is the 152-versus-274 discrepancy in the gate description's
2026-08-28 table: its findings column summed the totals, its severity columns
summed the events.

Model steps, per pass: reviews (one per ``findings_received`` event, or
``fix_iterations + 1`` when the record has none) plus fix rounds
(``fix_iterations``). The sequential gate runs passes one after another, so the
critical path is the sum over every pass, advisory excellence included.
``steps_source`` says which derivation each pass used.

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


def analyse_record(record: dict) -> dict:
    """The baseline row for one archived gate record."""
    passes = [p for p in record.get("completed_passes", []) if isinstance(p, dict)]
    summaries = {p["name"]: p for p in passes if isinstance(p.get("name"), str)}

    iterations: dict[str, list[Counter]] = {}
    advisory: dict[str, list[Counter]] = {}
    started: list[str] = []
    for event in record.get("audit_trail", []):
        if not isinstance(event, dict):
            continue
        lens = event.get("pass")
        if event.get("event") == "pass_started" and isinstance(lens, str) and lens not in started:
            started.append(lens)
        if event.get("event") == "findings_received" and isinstance(lens, str):
            iterations.setdefault(lens, []).append(_counts(event.get("counts")))
        if event.get("event") == "advisory_pass_completed" and isinstance(lens, str):
            # The advisory read is one review with no fix loop; v2 records log
            # it here rather than as findings_received. Used only for a lens
            # with no findings_received of its own, so it is never counted twice.
            advisory.setdefault(lens, []).append(_counts(event.get("counts")))
    for lens, found in advisory.items():
        iterations.setdefault(lens, found)

    # Lens order as dispatched: pass_started order where the record has it,
    # else completed_passes order; advisory lenses with no pass_started last.
    order = list(started) or [p["name"] for p in passes]
    for lens in sorted(set(summaries) | set(iterations), key=_lens_sort_key):
        if lens not in order:
            order.append(lens)

    lenses = {}
    for lens in order:
        summary = summaries.get(lens, {})
        fixes = summary.get("fix_iterations") or 0
        found = iterations.get(lens, [])
        if found:
            reviews, source = len(found), "events"
        else:
            reviews, source = fixes + 1, "pass_summary"
        initial = summary.get("findings_count_initial")
        first = sum((found[0][s] for s in (*SEVERITIES, "other")), 0) if found else 0
        if initial is None:
            initial = first
        lenses[lens] = {
            "iterations": reviews,
            "fix_rounds": fixes,
            "findings_by_iteration": [
                {s: c[s] for s in (*SEVERITIES, "other")} for c in found
            ],
            "findings_initial": initial,
            "unattributed": max(0, initial - first),
            "steps": reviews + fixes,
            "steps_source": source,
        }
    return {
        "bead": record.get("target_bead"),
        "version": record.get("version", 1),
        "started_at": record.get("started_at"),
        "dry_run": bool(record.get("dry_run")),
        "lens_order": order,
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
    """Per-lens totals over all rows: severities summed over every iteration."""
    out: dict[str, Counter] = {}
    for row in rows:
        for lens, data in row["lenses"].items():
            acc = out.setdefault(lens, Counter())
            acc["records"] += 1
            acc["findings_initial"] += data["findings_initial"]
            acc["unattributed"] += data["unattributed"]
            acc["iterations"] += data["iterations"]
            acc["steps"] += data["steps"]
            for it in data["findings_by_iteration"]:
                for sev, n in it.items():
                    acc[sev] += n
    return {lens: dict(out[lens]) for lens in sorted(out, key=_lens_sort_key)}


def baseline_rows(rows: list[dict]) -> list[dict]:
    """The rows the baseline counts: live gates only. A dry run replays a bead
    already gated, so counting it would count that bead twice."""
    return [r for r in rows if not r["dry_run"]]


def render_markdown(all_rows: list[dict]) -> str:
    rows = baseline_rows(all_rows)
    agg = totals(rows)
    # Passes outside the roster (one-off re-checks such as "delta-clarity" or
    # "scoped re-check", seven records) are folded into one row here; --json
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
        "| pass | records | findings (pass totals) | CRITICAL | IMPORTANT | MINOR"
        " | other | unattributed | reviews | model steps |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lens, t in agg.items():
        lines.append(
            f"| {lens} | {t['records']} | {t['findings_initial']} | {t.get('critical', 0)}"
            f" | {t.get('important', 0)} | {t.get('minor', 0)} | {t.get('other', 0)}"
            f" | {t['unattributed']} | {t['iterations']} | {t['steps']} |"
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
