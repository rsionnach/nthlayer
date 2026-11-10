#!/usr/bin/env python3
"""Parse an R5 reviewer's report into the shared Finding schema [opensrm-6kqs.3].

The contract is section 6 of
docs/superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md, shared word for
word with cúramóir (section 10 of its spec). cúramóir's
``.claude/hooks/lib/r5_findings.py`` (cm-70j) is normative: this file matches
it rule for rule, and where the two disagree, cúramóir's code is right
(Rob, 2026-11-10). It is also the one claim normaliser in this repository;
r5_corpus imports it rather than keeping its own.

A reviewer's LAST non-empty output line is ``R5-FINDINGS:`` followed by a JSON
array of findings. r5-supervise calls this on every report; it never trusts
counts typed by the supervisor.

    r5_findings.py parse <lens> <report-file> [--floor <level>] [--prior <file>]
    r5_findings.py compare <recorded.json> <replay-state.json>

``--prior`` is a JSON file holding the previous round's open set for this lens
(a list of findings; none on a first review). ``parse`` prints one JSON object:

- ``findings``: every record in the report, normalised;
- ``open_set``: the findings still open after this round, which the caller
  hands back as ``--prior`` next time;
- ``counts`` (critical, important, minor) and ``unproven`` (blocking findings
  whose verification_level is below the floor), both over the open set;
- ``closures`` (the prior fingerprints validly closed), ``closure_rejected``
  (each rejected closure with its reason), ``unaccounted`` (prior open
  findings the report neither closed nor re-raised) and
  ``downgrades_refused`` (re-raises held at the prior, higher severity).

``compare`` is the dry-run acceptance of bead 3 (see ``compare_records``).

Closures, per section 6 (settled 2026-11-07). A record with ``resolves`` set
is a closure, not a finding: it is never counted, whatever its severity, and
its path, lines and evidence are the resolving lines. It is valid only if
``resolves`` names a fingerprint in the previous round's open set and its
evidence is non-empty; an invalid closure is ignored and rejected with the
reason, and a second closure of the same fingerprint is dropped. The
closure's own fingerprint is never compared to ``resolves``. A re-raised
finding is the prior record copied verbatim (path and claim, so the same
fingerprint) with no ``resolves``. The open set is the previous open set
minus valid closures, plus new and re-raised findings; a prior open finding
with neither a closure nor a re-raise is carried forward unchanged, tagged
``unaccounted``: silence never closes. A re-raise keeps the more severe of
its own and the prior finding's severity (``downgrades_refused`` lists those
it held up): severity goes down only through a valid closure. A report that
closes every prior finding with empty evidence is a contract failure
(R5-R25).

``parse`` exits 0; 2 if the report does not meet the contract (the reason on
stderr: the caller records the reviewer UNAVAILABLE, R5-R9); 1 on a usage
error. ``compare`` exits 0, or 1 on a usage error or an unreadable file.

Standard library only, and Python 3.9 compatible: the hooks run under
whatever python3 the session finds (macOS ships 3.9).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any

PREFIX = "R5-FINDINGS:"
LENSES = ("correctness", "clarity", "edge_cases", "provenance", "excellence")
SEVERITIES = ("CRITICAL", "IMPORTANT", "MINOR")
# The E5-R11 ladder, weakest first.
LEVELS = ("asserted", "cited", "walked", "script", "reproduced")
DEFAULT_FLOOR = "script"
BLOCKING = ("CRITICAL", "IMPORTANT")
# Excellence is advisory: it never blocks, so it has nothing to prove.
ADVISORY_LENSES = ("excellence",)

# Removed from a claim before it is fingerprinted, so a finding keeps its key
# when the code it points at moves: line references (line 42, lines 4-9,
# :42, :4-9, L42) and SHA-like tokens (7 to 40 hex characters with at least
# one digit, so a word like "defaced" stays). Other numbers stay: "exits 2"
# and "exits 4" are different claims.
_LINE_REF = re.compile(r"\blines?\s+\d+(?:\s*[-\u2013]\s*\d+)?\b|:\d+(?:-\d+)?\b|\bl\d+\b")
_SHA = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b")
_SPACE = re.compile(r"\s+")
_FINGERPRINT = re.compile(r"[0-9a-f]{16}")


class ReportError(Exception):
    """The report does not meet the section 6 contract."""


def normalise_claim(claim: str) -> str:
    """Lower-case, line references and SHAs removed, whitespace collapsed."""
    text = claim.lower()
    text = _LINE_REF.sub(" ", text)
    text = _SHA.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def fingerprint(lens: str, path: str, claim: str) -> str:
    """First 16 hex of sha256(lens|path|normalised claim)."""
    key = f"{lens}|{path}|{normalise_claim(claim)}"
    try:
        data = key.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate, from a JSON \ud800 escape
        raise ReportError("a path or claim is not valid Unicode") from None
    return hashlib.sha256(data).hexdigest()[:16]


def _last_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    raise ReportError("the report is empty")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _unicode(value: str, key: str, n: int) -> str:
    """The value, if it can be written as UTF-8 (a JSON \\ud800 escape cannot)."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ReportError(f"finding {n}: {key} is not valid Unicode") from None
    return value


def _text(finding: dict, key: str, n: int) -> str:
    value = finding.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"finding {n}: {key} must be a non-empty string")
    return _unicode(value, key, n)


def _finding(raw: Any, lens: str, n: int) -> dict:
    if not isinstance(raw, dict):
        raise ReportError(f"finding {n} is not an object")
    if raw.get("lens", lens) != lens:
        raise ReportError(f"finding {n}: lens {raw.get('lens')!r} is not this reviewer's ({lens})")
    severity = raw.get("severity")
    if severity not in SEVERITIES:
        raise ReportError(f"finding {n}: severity must be one of {', '.join(SEVERITIES)}")
    path = _text(raw, "path", n)
    start, end = raw.get("start_line"), raw.get("end_line")
    if not (_is_int(start) and _is_int(end) and 1 <= start <= end):
        raise ReportError(f"finding {n}: start_line and end_line must be integers with 1 <= start <= end")
    claim = _text(raw, "claim", n)
    resolves = raw.get("resolves")
    # A copied fingerprint is forgiven surrounding space and upper case; a
    # value that cannot be a fingerprint at all is a malformed record, not a
    # closure to reject: it would otherwise turn a finding into an ignored one.
    if isinstance(resolves, str):
        resolves = resolves.strip().lower()
    if resolves is not None and not (isinstance(resolves, str) and _FINGERPRINT.fullmatch(resolves)):
        raise ReportError(f"finding {n}: resolves must be a 16-hex fingerprint or null")
    evidence = raw.get("evidence")
    if resolves is None:
        evidence = _text(raw, "evidence", n)
    elif evidence is None:
        # A closure without evidence is a contract matter for the round (it
        # is rejected, or the reviewer UNAVAILABLE), not a malformed record.
        evidence = ""
    elif not isinstance(evidence, str):
        raise ReportError(f"finding {n}: evidence must be a string")
    else:
        _unicode(evidence, "evidence", n)
    fix = raw.get("fix")
    if fix is not None and not isinstance(fix, str):
        raise ReportError(f"finding {n}: fix must be a string or null")
    if fix is not None:
        _unicode(fix, "fix", n)
    regression = raw.get("regression", False)
    if not isinstance(regression, bool):
        raise ReportError(f"finding {n}: regression must be true or false")
    level = raw.get("verification_level")
    if level is not None and level not in LEVELS:
        raise ReportError(f"finding {n}: verification_level must be one of {', '.join(LEVELS)}")
    finding = {
        "lens": lens, "severity": severity, "path": path,
        "start_line": start, "end_line": end,
        "claim": claim, "evidence": evidence, "fix": fix,
        # Computed here, never taken from the reviewer: it is the merge key.
        "fingerprint": fingerprint(lens, path, claim),
        "resolves": resolves, "regression": regression,
        # Set by the fixer, never by a reviewer.
        "status": "open",
    }
    if level is not None:
        finding["verification_level"] = level
    return finding


def parse_report(text: str, lens: str, floor: str = DEFAULT_FLOOR,
                 prior_open: list = ()) -> dict:
    """The report's records, the open set after it, and its accounting."""
    if lens not in LENSES:
        raise ValueError(f"unknown lens {lens!r}")
    if floor not in LEVELS:
        raise ValueError(f"unknown verification floor {floor!r}")
    line = _last_line(text)
    if not line.startswith(PREFIX):
        raise ReportError(f"the last line does not start with {PREFIX}")
    try:
        raw = json.loads(line[len(PREFIX):])
    except json.JSONDecodeError as exc:
        raise ReportError(f"the {PREFIX} line is not JSON ({exc.msg})") from None
    if not isinstance(raw, list):
        raise ReportError(f"the {PREFIX} line is not a JSON array")
    records = [_finding(item, lens, n) for n, item in enumerate(raw, 1)]

    prior = {f["fingerprint"]: f for f in prior_open}
    claimed, rejected = [], []
    for record in (r for r in records if r["resolves"] is not None):
        target = record["resolves"]
        if target not in prior:
            reason = "resolves names no fingerprint in the previous round's open set"
        elif not record["evidence"].strip():
            reason = "a closure needs evidence (the resolving lines)"
        elif target in claimed:
            reason = "a second closure of the same fingerprint is dropped"
        else:
            claimed.append(target)
            continue
        rejected.append({"resolves": target, "fingerprint": record["fingerprint"],
                         "reason": reason})
    # R5-R25: closing everything without citing the resolving lines.
    if prior and not claimed and all(
            any(r["resolves"] == fp and not r["evidence"].strip() for r in records)
            for fp in prior):
        raise ReportError("every prior finding is closed with empty evidence")

    # One entry per fingerprint: the same claim at two sites (or two claims
    # differing only in a line reference) share one; the most severe wins.
    by_fp = {}
    for record in (r for r in records if r["resolves"] is None):
        kept = by_fp.get(record["fingerprint"])
        if kept is None or SEVERITIES.index(record["severity"]) < SEVERITIES.index(kept["severity"]):
            by_fp[record["fingerprint"]] = record
    seen = set(by_fp)
    current, downgrades_refused = [], []
    for fp, record in by_fp.items():
        before = prior.get(fp)
        if before and SEVERITIES.index(before["severity"]) < SEVERITIES.index(record["severity"]):
            # A re-raise may not lower a finding's severity: only a valid
            # closure, with evidence, takes a finding down.
            record = {**record, "severity": before["severity"]}
            downgrades_refused.append(fp)
        current.append(record)
    # A closure is valid unless the same report also re-raises the finding,
    # which keeps it open (it is then neither a closure nor a rejection).
    valid_closures = [fp for fp in claimed if fp not in seen]
    carried = [{**f, "unaccounted": True} for fp, f in prior.items()
               if fp not in seen and fp not in valid_closures]
    open_set = current + carried

    counts = {s.lower(): sum(f["severity"] == s for f in open_set) for s in SEVERITIES}
    floor_rank = LEVELS.index(floor)
    # A finding with no level is "asserted", the bottom of the ladder.
    unproven = [
        f["fingerprint"] for f in open_set
        if lens not in ADVISORY_LENSES and f["severity"] in BLOCKING
        and LEVELS.index(f.get("verification_level", "asserted")) < floor_rank
    ]
    return {"findings": records, "open_set": open_set, "counts": counts,
            "unproven": unproven, "closures": valid_closures, "closure_rejected": rejected,
            "unaccounted": [f["fingerprint"] for f in carried],
            "downgrades_refused": downgrades_refused}


def _schema_lens(name: str) -> str:
    """r5-state names passes ``edge-cases``; the schema says ``edge_cases``."""
    return name.replace("-", "_")


def _blocking_records(findings: Any) -> list:
    """The blocking findings (not closures) of a non-advisory lens."""
    return [f for f in findings or ()
            if isinstance(f, dict) and f.get("severity") in BLOCKING
            and f.get("resolves") is None]


def _recorded_findings(recorded: dict) -> list:
    """Each blocking finding of a corpus ``recorded.json``, with its iteration."""
    out = []
    for review in recorded.get("rounds") or ():
        lens = _schema_lens(review.get("lens", ""))
        if lens in ADVISORY_LENSES:
            continue
        for f in _blocking_records(review.get("findings")):
            out.append({**f, "lens": lens, "iteration": review.get("iteration")})
    return out


def _replay_findings(state: dict) -> list:
    """Each blocking finding of a dry run's first review of each lens.

    A dry run reviews the frozen pre-gate tree once per lens (it commits no
    fixes, so there is nothing to re-review); a second ``findings_received``
    for a lens would be a retry, and only the first is the review."""
    seen, out = set(), []
    for event in state.get("audit_trail") or ():
        if event.get("event") != "findings_received":
            continue
        lens = _schema_lens(event.get("pass", ""))
        if lens in ADVISORY_LENSES or lens in seen:
            continue
        seen.add(lens)
        out.extend({**f, "lens": lens} for f in _blocking_records(event.get("findings")))
    return out


def _key(f: dict) -> str:
    """The comparison key, recomputed: a stored fingerprint is a cache, and
    corpus-v1 was fingerprinted with an older normaliser (Rob, 2026-11-10)."""
    return fingerprint(f["lens"], f.get("path") or "", f["claim"])


def compare_records(recorded: dict, replay: dict) -> dict:
    """Which recorded blocking findings a dry-run replay raised again.

    Matching is by fingerprint, recomputed on both sides. The recorded
    findings of a first review (iteration 1) are what the frozen tree can
    reproduce; later iterations reviewed trees holding fixes the dry run never
    made, so they are listed apart (``later_iterations``), matched or not.
    ``unmatched`` is what remains for a claim-equivalence ruling: a recorded
    finding raised again at another location counts as recalled, with a
    location mismatch noted, never as a loss (spec section 3, Phase A
    acceptance). ``severity_lowered`` lists matches the replay rated below
    blocking-severity parity (CRITICAL recorded, IMPORTANT replayed)."""
    replayed = {}
    for f in _replay_findings(replay):
        replayed.setdefault(_key(f), f)
    result = {"matched": [], "severity_lowered": [], "unmatched": [],
              "later_iterations": [], "replay_only": []}
    claimed = set()
    for f in _recorded_findings(recorded):
        key = _key(f)
        entry = {"lens": f["lens"], "iteration": f["iteration"], "severity": f["severity"],
                 "path": f.get("path"), "claim": f["claim"], "fingerprint": key}
        hit = replayed.get(key)
        if f["iteration"] != 1:
            result["later_iterations"].append({**entry, "matched": hit is not None})
        elif hit is None:
            result["unmatched"].append(entry)
        else:
            result["matched"].append(entry)
            if SEVERITIES.index(hit["severity"]) > SEVERITIES.index(f["severity"]):
                result["severity_lowered"].append({**entry, "replayed": hit["severity"]})
        if hit is not None:
            claimed.add(key)
    result["replay_only"] = [
        {"lens": f["lens"], "severity": f["severity"], "path": f.get("path"),
         "claim": f["claim"], "fingerprint": key}
        for key, f in replayed.items() if key not in claimed]
    return result


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _compare_main(args: list) -> int:
    if len(args) != 2:
        print("usage: r5_findings.py compare <recorded.json> <replay-state.json>", file=sys.stderr)
        return 1
    try:
        recorded, replay = (_load_json(a) for a in args)
    except (OSError, ValueError) as exc:
        print(f"r5_findings: cannot read {exc}", file=sys.stderr)
        return 1
    if not (isinstance(recorded, dict) and isinstance(replay, dict)):
        print("r5_findings: both files must hold a JSON object", file=sys.stderr)
        return 1
    json.dump(compare_records(recorded, replay), sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0


def main(argv: list) -> int:
    args = list(argv)
    if args[:1] == ["compare"]:
        return _compare_main(args[1:])
    options = {"--floor": DEFAULT_FLOOR, "--prior": ""}
    for flag in options:
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                print(f"r5_findings: {flag} needs a value", file=sys.stderr)
                return 1
            options[flag] = args[i + 1]
            del args[i:i + 2]
    floor = options["--floor"]
    if len(args) != 3 or args[0] != "parse":
        print("usage: r5_findings.py parse <lens> <report-file> [--floor <level>] "
              "[--prior <file>]", file=sys.stderr)
        return 1
    prior_open = []
    if options["--prior"]:
        try:
            with open(options["--prior"], encoding="utf-8") as handle:
                prior_open = json.load(handle)
        except (OSError, ValueError) as exc:
            print(f"r5_findings: cannot read the prior open set: {exc}", file=sys.stderr)
            return 1
        if not (isinstance(prior_open, list)
                and all(isinstance(f, dict) and isinstance(f.get("fingerprint"), str)
                        for f in prior_open)):
            print("r5_findings: the prior open set must be a list of findings", file=sys.stderr)
            return 1
    _, lens, path = args
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except UnicodeDecodeError:  # the report itself fails the contract
        print(f"r5_findings: the report {path} is not valid UTF-8", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"r5_findings: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    try:
        result = parse_report(text, lens, floor, prior_open)
    except ValueError as exc:  # an unknown lens or floor: the caller's mistake
        print(f"r5_findings: {exc}", file=sys.stderr)
        return 1
    except ReportError as exc:
        print(f"r5_findings: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
