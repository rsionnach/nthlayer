#!/usr/bin/env python3
"""Derive and validate the R5 round record [opensrm-6kqs.4, R5-R48].

The shape is "Round record" in section 6 of
docs/superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md, which cúramóir
owns. ``r5-state.json`` keeps every existing top-level field; this adds
``bead``, ``repo``, ``branch``, ``base``, ``head`` and ``rounds[]``.

``rounds[]`` is DERIVED from ``audit_trail`` (Rob, 2026-11-13, D1), never
written by hand: the supervisor appends events, this script turns them into
rounds, so the two cannot drift apart. ``build`` never edits its input, is
deterministic and replaces only the keys it derives, so a later rename in the
shape is a re-derivation over the whole archive, not a migration.

    r5_record.py build <state.json>       derived record on stdout
    r5_record.py validate <record.json>   report on stdout

Exit codes: 0 ok; 2 the record cannot be derived (``build``, with a named
reason) or does not match the shape (``validate``); 1 usage or unreadable file.

Rulings applied (Rob, 2026-11-13):

- D2: ``model``, ``tier``, ``tokens_in``, ``tokens_out`` and ``duration_s`` are
  null when unmeasured, never 0. ``duration_s`` comes from the dispatch and
  receipt timestamps when both carry a time of day. ``tokens_total`` (erratum
  E1, an addition to section 6) holds the Agent result's total.
- D3: the top-level ``repo``, ``base`` and ``head`` are filled from
  ``diff_range`` only when it names one repo; otherwise they are null and
  ``diff_range`` stays the source.
- D4: ``lenses`` keys use the schema's spelling (``edge_cases``).

Records written before the parser (6kqs.3) hold severity counts, not
findings. Their lens entries carry ``null`` for ``findings`` and the other
parser lists: not recorded, as opposed to ``[]``, none found.

Round kinds. A lens's first reviewer in the gate is a ``review`` round and
each later one a ``verify`` round, unless the dispatch event names its
``mode``. ``fixes_applied`` or ``fix_dispatched`` opens a ``fix`` round; the
``commit_made`` events before the next dispatch are its commits. ``preflight``
rounds are bead 5's, ``merge`` and ``mutations`` Phase B's and bead 10's, and
``verdict`` bead 6's: this script writes none of them.

Standard library only, Python 3.9 compatible, like the other gate scripts.
"""

from __future__ import annotations

import copy
import datetime
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r5_findings import LENSES, _schema_lens  # noqa: E402  (sibling script)

KINDS = ("preflight", "review", "fix", "verify")
MODES = ("review", "verify")
LENS_STATUSES = ("ok", "UNAVAILABLE", "skipped")
# r5-supervise Step 5's fixer statuses, plus Phase B bead 3's superseded.
FIX_STATUSES = ("fixed", "fixed_in_passing", "superseded", "could_not_fix", "disputed")
VERDICT_STATES = ("CLEAN", "ESCALATED", "PREFLIGHT_FAILED", "BUDGET")
# The parser's lists on a lens entry (section 6), in the shape's order.
PARSER_LISTS = ("findings", "closures", "closure_rejected", "unaccounted",
                "downgrades_refused", "prose_unfiled")
MEASURED = ("model", "tier", "tokens_in", "tokens_out", "tokens_total", "duration_s")
DERIVED_KEYS = ("bead", "repo", "branch", "base", "head", "rounds")

# The audit events that make rounds. Every other event (preflight drift,
# tests, rulings, notes...) is informational and ignored here.
DISPATCH = "reviewer_dispatched"
RECEIPTS = ("findings_received", "advisory_pass_completed")
FIX_OPENERS = ("fixes_applied", "fix_dispatched")
COMMIT = "commit_made"

# Why ``build`` refuses a record. A fixed set, so a test can hold the whole
# archive to it: each record builds, or refuses for one of these.
REFUSALS = {
    "not_an_object": "the record is not a JSON object",
    "no_audit_trail": "audit_trail is missing or not a list",
    "bad_event": "an audit_trail entry is not an object with a string event",
    "unknown_lens": "a pass name is not one of the section 6 lenses",
    "receipt_without_pass": "a findings event names no pass",
    "bad_parser_field": "a findings event carries a parser field that is not a list",
    "pass_without_review": "a completed pass has no reviewer receipt in audit_trail",
    "verify_count_mismatch": "a lens's derived verify rounds differ from its fix_iterations",
}


class BuildRefused(ValueError):
    """The record cannot be turned into rounds without guessing."""

    def __init__(self, reason: str, detail: str):
        assert reason in REFUSALS, reason
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


def _instant(ts: Any) -> datetime.datetime | None:
    """A timestamp with a time of day, or None (date-only stamps carry none)."""
    if not isinstance(ts, str) or "T" not in ts:
        return None
    try:
        moment = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def _duration(started: Any, ended: Any) -> float | None:
    a, b = _instant(started), _instant(ended)
    if a is None or b is None or b < a:
        return None
    return (b - a).total_seconds()


def _lens_of(event: dict) -> str:
    name = event.get("pass")
    if not isinstance(name, str):
        raise BuildRefused("receipt_without_pass", repr(event)[:120])
    lens = _schema_lens(name)
    if lens not in LENSES:
        raise BuildRefused("unknown_lens", repr(name))
    return lens


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _lens_entry(dispatch: dict | None, receipt: dict, mode: str) -> dict:
    """One lens's entry in a review or verify round."""
    started = dispatch.get("ts") if dispatch else None
    measured = dict(dispatch or {})
    measured.update(receipt)  # the receipt is later, so it wins
    duration = measured.get("duration_s")
    if not (isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0):
        duration = _duration(started, receipt.get("ts"))
    entry = {
        "model": measured.get("model") if isinstance(measured.get("model"), str) else None,
        "tier": measured.get("tier") if isinstance(measured.get("tier"), str) else None,
        "mode": mode,
        "tokens_in": _int_or_none(measured.get("tokens_in")),
        "tokens_out": _int_or_none(measured.get("tokens_out")),
        "tokens_total": _int_or_none(measured.get("tokens_total")),
        "duration_s": duration,
        "status": measured.get("status") if measured.get("status") in LENS_STATUSES else "ok",
        "skip_rule": measured.get("skip_rule") if isinstance(measured.get("skip_rule"), str) else None,
    }
    for key in PARSER_LISTS:
        value = receipt.get(key)
        if value is not None and not isinstance(value, list):
            raise BuildRefused("bad_parser_field", f"{key} is {type(value).__name__}")
        entry[key] = copy.deepcopy(value)
    return entry


def _single_repo(diff_range: Any) -> tuple[str | None, str | None, str | None]:
    """(repo, base, head) when diff_range names exactly one repo (D3)."""
    if not (isinstance(diff_range, dict) and len(diff_range) == 1):
        return None, None, None
    (repo, span), = diff_range.items()
    if not isinstance(span, dict):
        return repo, None, None
    base, head = span.get("base"), span.get("head")
    return (repo, base if isinstance(base, str) else None,
            head if isinstance(head, str) else None)


def derive_rounds(record: dict) -> list[dict]:
    """The rounds of one gate, in audit-trail order."""
    trail = record.get("audit_trail")
    if not isinstance(trail, list):
        raise BuildRefused("no_audit_trail", type(trail).__name__)
    _, _, range_head = _single_repo(record.get("diff_range"))
    rounds: list[dict] = []
    pending: dict[str, dict] = {}  # lens -> its unanswered dispatch event
    reviewed: set[str] = set()
    fix: dict | None = None  # the open fix round, until the next dispatch
    head = range_head

    for event in trail:
        if not (isinstance(event, dict) and isinstance(event.get("event"), str)):
            raise BuildRefused("bad_event", repr(event)[:120])
        name = event["event"]
        if name == DISPATCH:
            lens = _lens_of(event)
            pending[lens] = event  # a re-sent dispatch replaces an unanswered one
            fix = None
        elif name in RECEIPTS:
            lens = _lens_of(event)
            dispatch = pending.pop(lens, None)
            stated = (dispatch or {}).get("mode")
            mode = stated if stated in MODES else ("verify" if lens in reviewed else "review")
            reviewed.add(lens)
            round_head = (dispatch or {}).get("head") or event.get("head") or head
            started = dispatch.get("ts") if dispatch else None
            rounds.append({
                "kind": mode, "head": round_head if isinstance(round_head, str) else None,
                "started": started, "ended": event.get("ts"),
                "lenses": {lens: _lens_entry(dispatch, event, mode)},
            })
            fix = None
        elif name in FIX_OPENERS:
            statuses = event.get("statuses")
            if fix is None:
                fix = {"kind": "fix", "head": None, "started": event.get("ts"),
                       "ended": event.get("ts"), "lenses": {},
                       "fix": {"commit": None, "statuses": {}, "scope_breaches": []}}
                fix["_commits"] = []
                rounds.append(fix)
            fix["ended"] = event.get("ts")
            if isinstance(statuses, dict):
                fix["fix"]["statuses"].update(copy.deepcopy(statuses))
        elif name == COMMIT and fix is not None:
            shas = [event.get("sha")] if isinstance(event.get("sha"), str) else []
            shas += [s for s in event.get("shas") or [] if isinstance(s, str)]
            fix["_commits"].extend(shas)
            fix["ended"] = event.get("ts")
            if shas:
                head = shas[-1]

    for n, rnd in enumerate(rounds, 1):
        rnd["n"] = n
        commits = rnd.pop("_commits", None)
        # One commit is the round's commit and its head. Several (a gate over
        # more than one repo) have no single one: null, and the audit trail
        # keeps them all (section 6 has one commit per round).
        if commits is not None and len(commits) == 1:
            rnd["fix"]["commit"] = rnd["head"] = commits[0]
    return [_ordered(r) for r in rounds]


def _ordered(rnd: dict) -> dict:
    order = ("n", "kind", "head", "started", "ended", "lenses", "fix")
    return {k: rnd[k] for k in order if k in rnd}


def lens_tally(rounds: list[dict]) -> dict[str, dict[str, int]]:
    """Per lens: review, verify and fix rounds. A fix round belongs to the
    lens of the review or verify round before it (the sequential gate fixes
    one lens's findings at a time)."""
    tally: dict[str, dict[str, int]] = {}
    last = None
    for rnd in rounds:
        if rnd["kind"] in MODES:
            last = next(iter(rnd["lenses"]))
            tally.setdefault(last, {"review": 0, "verify": 0, "fix": 0})[rnd["kind"]] += 1
        elif rnd["kind"] == "fix" and last is not None:
            tally[last]["fix"] += 1
    return tally


def check_against_summary(record: dict, rounds: list[dict]) -> None:
    """Refuse rounds that contradict the record's own pass summaries.

    ``completed_passes`` is what the supervisor said happened; rounds derived
    from other events than that would be a plausible wrong record (a pass
    with no reviewer, or more or fewer re-reviews than it ran), so ``build``
    refuses instead of writing one.

    ``fix_iterations`` counts fix-then-re-review loops, so it is compared
    with verify rounds, not fix rounds: a MINOR fixed in passing is a fix
    round (section 6: each fix is one) with no re-review after it
    (opensrm-6kqs.11's correctness pass)."""
    tally = lens_tally(rounds)
    for summary in record.get("completed_passes") or []:
        if not isinstance(summary, dict) or not isinstance(summary.get("name"), str):
            continue
        lens = _lens_of({"pass": summary["name"]})
        got = tally.get(lens)
        if got is None:
            raise BuildRefused("pass_without_review", summary["name"])
        want = summary.get("fix_iterations")
        if isinstance(want, int) and not isinstance(want, bool) and want != got["verify"]:
            raise BuildRefused("verify_count_mismatch",
                               f"{summary['name']}: fix_iterations {want}, verify rounds {got['verify']}")


def build(record: Any) -> dict:
    """The record with its derived keys replaced; the input is not touched."""
    if not isinstance(record, dict):
        raise BuildRefused("not_an_object", type(record).__name__)
    rounds = derive_rounds(record)
    check_against_summary(record, rounds)
    out = {k: copy.deepcopy(v) for k, v in record.items() if k not in DERIVED_KEYS}
    repo, base, head = _single_repo(record.get("diff_range"))
    if repo is not None:
        # diff_range's head is where the gate started; fix commits move it,
        # and the record's head is where the gate ended.
        heads = [r["head"] for r in rounds if r["head"] is not None]
        head = heads[-1] if heads else head
    bead = record.get("target_bead")
    branch = record.get("branch_name")
    out.update({"bead": bead if isinstance(bead, str) else None, "repo": repo,
                "branch": branch if isinstance(branch, str) else None,
                "base": base, "head": head, "rounds": rounds})
    return out


# ---------------------------------------------------------------- validate

def _is_str_or_none(v: Any) -> bool:
    return v is None or isinstance(v, str)


def _is_count(v: Any) -> bool:
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= 0)


def _check_lens(where: str, lens: str, entry: Any, kind: str, errors: list) -> None:
    if lens not in LENSES:
        errors.append(f"{where}: lens {lens!r} is not one of {LENSES}")
    if not isinstance(entry, dict):
        errors.append(f"{where}.{lens}: not an object")
        return
    if entry.get("mode") != kind:
        errors.append(f"{where}.{lens}: mode {entry.get('mode')!r} does not match kind {kind!r}")
    for key in ("model", "tier", "skip_rule"):
        if not _is_str_or_none(entry.get(key)):
            errors.append(f"{where}.{lens}.{key}: not a string or null")
    for key in ("tokens_in", "tokens_out", "tokens_total"):
        if not _is_count(entry.get(key)):
            errors.append(f"{where}.{lens}.{key}: not a non-negative integer or null")
    d = entry.get("duration_s")
    if not (d is None or (isinstance(d, (int, float)) and not isinstance(d, bool) and d >= 0)):
        errors.append(f"{where}.{lens}.duration_s: not a non-negative number or null")
    if entry.get("status") not in LENS_STATUSES:
        errors.append(f"{where}.{lens}.status: {entry.get('status')!r} not in {LENS_STATUSES}")
    for key in PARSER_LISTS:
        if key not in entry:
            errors.append(f"{where}.{lens}.{key}: missing")
        elif not (entry[key] is None or isinstance(entry[key], list)):
            errors.append(f"{where}.{lens}.{key}: not a list or null")
    for key in MEASURED + ("mode", "status", "skip_rule"):
        if key not in entry:
            errors.append(f"{where}.{lens}.{key}: missing")


def validate(record: Any) -> dict:
    """Errors against the section 6 shape, and notes that are not errors."""
    errors: list[str] = []
    notes: list[str] = []
    if not isinstance(record, dict):
        return {"valid": False, "errors": ["not a JSON object"], "notes": []}
    for key in DERIVED_KEYS:
        if key not in record:
            errors.append(f"{key}: missing")
    for key in ("bead", "repo", "branch", "base", "head"):
        if not _is_str_or_none(record.get(key)):
            errors.append(f"{key}: not a string or null")
    dr = record.get("diff_range")
    if isinstance(dr, dict) and len(dr) > 1:
        notes.append(f"multi_repo: {sorted(dr)}; repo, base and head stay null (D3)")
        for key in ("repo", "base", "head"):
            if record.get(key) is not None:
                errors.append(f"{key}: set on a multi-repo gate (D3 says null)")
    rounds = record.get("rounds")
    if not isinstance(rounds, list):
        errors.append("rounds: not a list")
        rounds = []
    for i, rnd in enumerate(rounds):
        where = f"rounds[{i}]"
        if not isinstance(rnd, dict):
            errors.append(f"{where}: not an object")
            continue
        if rnd.get("n") != i + 1:
            errors.append(f"{where}.n: {rnd.get('n')!r}, expected {i + 1}")
        kind = rnd.get("kind")
        if kind not in KINDS:
            errors.append(f"{where}.kind: {kind!r} not in {KINDS}")
        for key in ("head", "started", "ended"):
            if not _is_str_or_none(rnd.get(key)):
                errors.append(f"{where}.{key}: not a string or null")
        a, b = _instant(rnd.get("started")), _instant(rnd.get("ended"))
        if a and b and b < a:
            errors.append(f"{where}: ended before started")
        lenses = rnd.get("lenses")
        if not isinstance(lenses, dict):
            errors.append(f"{where}.lenses: not an object")
            lenses = {}
        if kind in MODES:
            # Sequential gate: one lens per review or verify round (bead 4).
            if len(lenses) != 1:
                errors.append(f"{where}: a {kind} round has {len(lenses)} lenses, expected 1")
            for lens, entry in lenses.items():
                _check_lens(where, lens, entry, kind, errors)
        if kind == "fix":
            if lenses:
                errors.append(f"{where}: a fix round dispatches no lens")
            fx = rnd.get("fix")
            if not isinstance(fx, dict):
                errors.append(f"{where}.fix: missing or not an object")
            else:
                if not _is_str_or_none(fx.get("commit")):
                    errors.append(f"{where}.fix.commit: not a string or null")
                st = fx.get("statuses")
                if not isinstance(st, dict) or any(v not in FIX_STATUSES for v in st.values()):
                    errors.append(f"{where}.fix.statuses: not a map to {FIX_STATUSES}")
                if not isinstance(fx.get("scope_breaches"), list):
                    errors.append(f"{where}.fix.scope_breaches: not a list")
                if fx.get("commit") is None:
                    notes.append(f"{where}: fix round with no single commit")
        elif "fix" in rnd:
            errors.append(f"{where}: fix object on a {kind} round")
    verdict = record.get("verdict")
    if verdict is not None and (
            not isinstance(verdict, dict) or verdict.get("state") not in VERDICT_STATES):
        errors.append(f"verdict.state: not in {VERDICT_STATES}")
    return {"valid": not errors, "errors": errors, "notes": notes}


# --------------------------------------------------------------------- CLI

def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list) -> int:
    if len(argv) != 2 or argv[0] not in ("build", "validate"):
        print("usage: r5_record.py build <state.json> | validate <record.json>", file=sys.stderr)
        return 1
    command, path = argv
    try:
        data = _load(path)
    except (OSError, ValueError) as exc:
        print(f"r5_record: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    if command == "build":
        try:
            out = build(data)
        except BuildRefused as exc:
            print(f"r5_record: refused: {exc}", file=sys.stderr)
            return 2
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    result = validate(data)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
