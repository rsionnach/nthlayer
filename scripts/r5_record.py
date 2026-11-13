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
    r5_record.py sweep <dir>              build + validate every archive in <dir>

Exit codes: 0 ok; 2 the record cannot be derived (``build``, with a named
reason) or does not match the shape (``validate``); 1 usage or unreadable file.
``sweep`` exits 0 when every ``r5-state-*-completed.json`` in the directory
either builds into a valid record or refuses with a reason in ``REFUSALS``,
and 2 when any built record fails ``validate`` or no archive is found: it is
the re-derivation over the whole archive a change in the shape needs.

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

Round kinds. A lens's first answered reviewer in the gate is a ``review``
round and each later one a ``verify`` round (r5-supervise Step 8 re-dispatches
only in verify mode; a ``mode`` on the dispatch is not read, since no step
writes one that differs). ``fixes_applied`` or ``fix_dispatched`` opens a ``fix`` round, and so
does a ``commit_made`` after a review with neither (older supervisors logged
only the commit); the ``commit_made`` events before the next dispatch are its
commits, and the round's head is the last of them. A ``reviewer_dispatched``
for a lens whose last dispatch is unanswered is a re-send (Rob, 2026-11-13,
opensrm-6kqs.14). When a ``supervisor_blocked`` or ``reviewer_dispatch_blocked``
for that pass, or naming no pass, lies between the two, the hook refused the
earlier launch: no reviewer ran and the re-send replaces it. Otherwise the
earlier reviewer ran and stalled: it is a round of its own, lens status
``UNAVAILABLE`` with null parser lists, whose mode follows the order rule (it
is not the lens's first review), started at the stalled dispatch and ended at
the re-send. Its ``duration_s`` is null: the span to the re-send is how long
the supervisor waited, not a measurement of the reviewer, which may have
stopped long before (D2). ``preflight``
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
# A report the parser refused (exit 2, R5-R9): a round whose lens status is
# UNAVAILABLE, with no parser output. r5-supervise re-dispatches the same
# brief once, so the retry keeps the refused round's mode.
UNAVAILABLE = "reviewer_unavailable"
# The events that say a reviewer_dispatched never launched a reviewer: the
# parallel-block hook refused it (r5-supervise Step 3/4). A re-send after one
# of these replaces the refused dispatch; a re-send after none follows a
# reviewer that ran and stalled, which is a round of its own.
BLOCKS = ("supervisor_blocked", "reviewer_dispatch_blocked")
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
    "bad_commit_event": "a commit_made sha or shas is not a string, a list of strings or a map to strings",
    "bad_summary": "completed_passes is present but not a list",
    "dispatch_unanswered": "a reviewer dispatch has no receipt by the end of audit_trail",
}


class BuildRefused(ValueError):
    """The record cannot be turned into rounds without guessing."""

    def __init__(self, reason: str, detail: str):
        assert reason in REFUSALS, reason
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


def _instant(ts: Any) -> datetime.datetime | None:
    """An aware timestamp, or None. A date-only stamp parses to a naive
    midnight, so it is None too: it carries no time of day to measure."""
    if not isinstance(ts, str):
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


def _lens_entry(dispatch: dict | None, receipt: dict, mode: str,
                unavailable: bool = False) -> dict:
    """One lens's entry in a review or verify round."""
    started = dispatch.get("ts") if dispatch else None
    measured = dict(dispatch or {})
    measured.update(receipt)  # the receipt is later, so it wins
    # D2: from the audit timestamps first; a duration the event states is the
    # fallback (an event with no dispatch stamp); null when neither exists.
    duration = _duration(started, receipt.get("ts"))
    stated = measured.get("duration_s")
    if duration is None and isinstance(stated, (int, float)) and not isinstance(stated, bool) \
            and stated >= 0:
        duration = stated
    entry = {
        "model": measured.get("model") if isinstance(measured.get("model"), str) else None,
        "tier": measured.get("tier") if isinstance(measured.get("tier"), str) else None,
        "mode": mode,
        "tokens_in": _int_or_none(measured.get("tokens_in")),
        "tokens_out": _int_or_none(measured.get("tokens_out")),
        "tokens_total": _int_or_none(measured.get("tokens_total")),
        "duration_s": duration,
        # Only reviewer_unavailable sets a status: no supervisor step writes a
        # status or a skip rule on an event (skipped lenses are Phase B's).
        "status": "UNAVAILABLE" if unavailable else "ok",
        "skip_rule": None,
    }
    for key in PARSER_LISTS:
        value = None if unavailable else receipt.get(key)
        if value is not None and not isinstance(value, list):
            raise BuildRefused("bad_parser_field", f"{key} is {type(value).__name__}")
        entry[key] = copy.deepcopy(value)
    return entry


_HEX = frozenset("0123456789abcdef")


def _sha_or_none(value: Any) -> str | None:
    """A commit SHA (4 to 40 hex digits), else None: diff_range sometimes
    holds a revision expression ("65ba2bc^", "HEAD"), which names no commit
    once the branch moves."""
    if isinstance(value, str) and 4 <= len(value) <= 40 and set(value.lower()) <= _HEX:
        return value
    return None


def _single_repo(diff_range: Any) -> tuple[str | None, str | None, str | None]:
    """(repo, base, head) when diff_range names exactly one repo (D3)."""
    if not (isinstance(diff_range, dict) and len(diff_range) == 1):
        return None, None, None
    (repo, span), = diff_range.items()
    if not isinstance(span, dict):
        return repo, None, None
    return repo, _sha_or_none(span.get("base")), _sha_or_none(span.get("head"))


def _commit_shas(event: dict) -> list[str]:
    """The commits a commit_made names: ``sha``, then ``shas`` as a list or as
    a per-repo map (7zpz-pinrepos logs one). Anything else is refused: a
    commit that cannot be read would leave the next round on a stale head."""
    sha, many = event.get("sha"), event.get("shas")
    if sha is not None and not isinstance(sha, str):
        raise BuildRefused("bad_commit_event", f"sha {sha!r}")
    out = [sha] if sha is not None else []
    if isinstance(many, dict):
        many = list(many.values())
    if many is not None and not (isinstance(many, list) and all(isinstance(s, str) for s in many)):
        raise BuildRefused("bad_commit_event", f"shas {many!r}"[:120])
    return out + list(many or [])


def _same_commit(a: str, b: str) -> bool:
    """Abbreviated SHAs of one commit: one is a prefix of the other."""
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def _start_head(trail: list, range_head: str | None) -> str | None:
    """The head the gate's first reviews ran against, or None if unknown.

    Some supervisors left diff_range's head where the gate started; others
    moved it to the last fix commit when the gate ended (the archives hold
    both). A head that is one of the gate's own commits after its first
    review is an end head, so the start is not recorded."""
    if range_head is None:
        return None
    seen_review = False
    for event in trail:
        if not isinstance(event, dict):
            continue
        if event.get("event") in RECEIPTS or event.get("event") == UNAVAILABLE:
            seen_review = True
        elif event.get("event") == COMMIT and seen_review and any(
                _same_commit(sha, range_head) for sha in _commit_shas(event)):
            return None
    return range_head


def derive_rounds(record: dict) -> list[dict]:
    """The rounds of one gate, in audit-trail order."""
    trail = record.get("audit_trail")
    if not isinstance(trail, list):
        raise BuildRefused("no_audit_trail", type(trail).__name__)
    _, _, range_head = _single_repo(record.get("diff_range"))
    range_head = _start_head(trail, range_head)
    # A gate over several repos has no one tree per round: one repo's commit
    # would name a review that read them all (D3's reason, per round).
    dr = record.get("diff_range")
    multi_repo = isinstance(dr, dict) and len(dr) > 1
    rounds: list[dict] = []
    pending: dict[str, dict] = {}  # lens -> its unanswered dispatch event
    refused: set[str] = set()  # pending lenses with a block event since dispatch
    reviewed: set[str] = set()
    fix: dict | None = None  # the open fix round, until the next dispatch
    reviewed_since_dispatch = False  # a receipt came after the last dispatch
    head = range_head

    def open_fix(ts: Any) -> dict:
        rnd = {"kind": "fix", "head": None, "started": ts, "ended": ts, "lenses": {},
               "fix": {"commit": None, "statuses": {}, "scope_breaches": []}, "_commits": []}
        rounds.append(rnd)
        return rnd

    for event in trail:
        if not (isinstance(event, dict) and isinstance(event.get("event"), str)):
            raise BuildRefused("bad_event", repr(event)[:120])
        name = event["event"]
        if name == DISPATCH:
            lens = _lens_of(event)
            stalled = pending.get(lens)
            if stalled is not None and lens not in refused:
                # The earlier reviewer ran and gave no answer: its own round.
                mode = "verify" if lens in reviewed else "review"
                entry = _lens_entry(stalled, {}, mode, unavailable=True)
                entry["duration_s"] = None
                stalled_head = stalled.get("head") or head
                rounds.append({
                    "kind": mode,
                    "head": stalled_head if isinstance(stalled_head, str) else None,
                    "started": stalled.get("ts"), "ended": event.get("ts"),
                    "lenses": {lens: entry},
                })
            # A refused dispatch never ran: the re-send replaces it.
            pending[lens] = event
            refused.discard(lens)
            fix = None
            reviewed_since_dispatch = False
        elif name in RECEIPTS or name == UNAVAILABLE:
            lens = _lens_of(event)
            dispatch = pending.pop(lens, None)
            refused.discard(lens)
            mode = "verify" if lens in reviewed else "review"
            unavailable = name == UNAVAILABLE
            if not unavailable:
                reviewed.add(lens)
            round_head = (dispatch or {}).get("head") or event.get("head") or head
            started = dispatch.get("ts") if dispatch else None
            rounds.append({
                "kind": mode, "head": round_head if isinstance(round_head, str) else None,
                "started": started, "ended": event.get("ts"),
                "lenses": {lens: _lens_entry(dispatch, event, mode, unavailable)},
            })
            fix = None
            reviewed_since_dispatch = True
        elif name in BLOCKS:
            target = event.get("pass")
            if not isinstance(target, str):
                refused.update(pending)
            elif _schema_lens(target) in pending:
                refused.add(_schema_lens(target))
        elif name in FIX_OPENERS:
            statuses = event.get("statuses")
            if fix is None:
                fix = open_fix(event.get("ts"))
            fix["ended"] = event.get("ts")
            if isinstance(statuses, dict):
                fix["fix"]["statuses"].update(copy.deepcopy(statuses))
        elif name == COMMIT and (fix is not None or reviewed_since_dispatch):
            # Supervisors before 6kqs.3 often logged findings_received ->
            # commit_made -> reviewer_dispatched with no fixes_applied: a
            # commit after a review is that review's fix. A commit before
            # any review (the implementation itself) is not a round.
            if fix is None:
                fix = open_fix(event.get("ts"))
            shas = _commit_shas(event)
            fix["_commits"].extend(shas)
            fix["ended"] = event.get("ts")
            if shas and not multi_repo:
                head = shas[-1]

    if pending:
        # A reviewer that never answered is not a round we can describe, and
        # dropping it would record a gate with one review fewer than it ran.
        raise BuildRefused("dispatch_unanswered", ", ".join(sorted(pending)))
    for n, rnd in enumerate(rounds, 1):
        rnd["n"] = n
        commits = rnd.pop("_commits", None)
        # One commit is the round's commit. Several have no single one: null
        # (ruling b; the audit trail keeps them all, section 6 has one commit
        # per round). Either way a single-repo round ends at its last commit.
        if commits and not multi_repo:
            rnd["head"] = commits[-1]
            if len(commits) == 1:
                rnd["fix"]["commit"] = commits[0]
    return [_ordered(r) for r in rounds]


def _ordered(rnd: dict) -> dict:
    order = ("n", "kind", "head", "started", "ended", "lenses", "fix")
    return {k: rnd[k] for k in order if k in rnd}


def lens_tally(rounds: list[dict]) -> dict[str, dict[str, int]]:
    """Per lens: answered review and verify rounds, and fix rounds. A fix
    round belongs to the lens of the review or verify round before it (the
    sequential gate fixes one lens's findings at a time). An UNAVAILABLE
    round is not counted: its retry is the same review."""
    tally: dict[str, dict[str, int]] = {}
    last = None
    for rnd in rounds:
        if rnd["kind"] in MODES:
            last, entry = next(iter(rnd["lenses"].items()))
            if entry["status"] == "UNAVAILABLE":
                continue
            tally.setdefault(last, {"review": 0, "verify": 0, "fix": 0})[rnd["kind"]] += 1
        elif rnd["kind"] == "fix" and last is not None:
            tally.setdefault(last, {"review": 0, "verify": 0, "fix": 0})["fix"] += 1
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
    summaries = record.get("completed_passes")
    if summaries is not None and not isinstance(summaries, list):
        raise BuildRefused("bad_summary", type(summaries).__name__)
    for summary in summaries or []:
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
        # The record's head is where the gate ended: its last round's head,
        # else diff_range's (a gate with no fix commit ends where it began).
        heads = [r["head"] for r in rounds if r["head"] is not None]
        head = heads[-1] if heads else head
    bead = record.get("target_bead")
    out.update({"bead": bead if isinstance(bead, str) else None, "repo": repo,
                # r5-state records no branch (Step 1's shape, 0 of 96 archives).
                "branch": None,
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


def sweep(directory: Path) -> dict:
    """Build and validate every archived record in ``directory``."""
    outcome: dict[str, Any] = {"built": [], "refused": {}, "invalid": {}, "unreadable": {}}
    for path in sorted(directory.glob("r5-state-*-completed.json")):
        try:
            record = _load(str(path))
        except (OSError, ValueError) as exc:
            outcome["unreadable"][path.name] = str(exc)
            continue
        try:
            built = build(record)
        except BuildRefused as exc:
            outcome["refused"][path.name] = exc.reason
            continue
        except Exception as exc:  # noqa: BLE001  one bad archive must not hide the rest
            outcome["invalid"][path.name] = [f"build crashed: {type(exc).__name__}: {exc}"]
            continue
        result = validate(built)
        if result["valid"]:
            outcome["built"].append(path.name)
        else:
            outcome["invalid"][path.name] = result["errors"]
    total = sum(len(v) for v in outcome.values())
    outcome["ok"] = total > 0 and not outcome["invalid"] and not outcome["unreadable"]
    return outcome


def main(argv: list) -> int:
    if len(argv) != 2 or argv[0] not in ("build", "validate", "sweep"):
        print("usage: r5_record.py build <state.json> | validate <record.json> | sweep <dir>",
              file=sys.stderr)
        return 1
    command, path = argv
    if command == "sweep":
        if not Path(path).is_dir():
            print(f"r5_record: {path} is not a directory", file=sys.stderr)
            return 1
        result = sweep(Path(path))
        json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write("\n")
        return 0 if result["ok"] else 2
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
