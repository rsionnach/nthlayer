"""Tests for scripts/r5_findings.py (opensrm-6kqs.3).

Each fixture comes from a sentence of section 6 of
docs/superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md (quoted in the
test's docstring), not from the port, and the expected values are read off
that sentence. Two shapes are not in section 6: the corpus's recorded.json
(``rounds[]`` of ``lens``/``iteration``/``findings``, as scripts/r5_corpus.py
writes it and corpus-v1 publishes it) and the dry-run state the supervisor
writes (a ``findings_received`` audit event carrying the parser's
``findings``, r5-supervise Step 4).

Run: uv run --no-project --with pytest pytest -q test/test_r5_findings.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "r5_findings.py"
sys.path.insert(0, str(SCRIPT.parent))
_spec = importlib.util.spec_from_file_location("r5_findings", SCRIPT)
assert _spec and _spec.loader
r5_findings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r5_findings)
import r5_corpus  # noqa: E402  (a sibling script, not a package)

ReportError = r5_findings.ReportError


def finding(**over) -> dict:
    """A finding in the section 6 example's shape, with real values."""
    base = {"lens": "correctness", "severity": "IMPORTANT", "path": "src/opensrm/parser/v2.py",
            "start_line": 118, "end_line": 131, "claim": "the v2 branch never fires",
            "evidence": "pytest -k v2 collects 0 items", "fix": "test the mapping shape",
            "verification_level": "script", "resolves": None, "regression": False}
    base.update(over)
    return base


def report(records: list, prose: str = "### Correctness Assessment\n**Verdict:** FAIL\n") -> str:
    return f"{prose}\nR5-FINDINGS: {json.dumps(records)}\n"


def parse(records: list, lens: str = "correctness", **kw) -> dict:
    return r5_findings.parse_report(report(records), lens, **kw)


# --- "A reviewer's last non-empty output line is R5-FINDINGS: followed by a
#      JSON array of them; anything else is UNAVAILABLE."

def test_the_last_non_empty_line_carries_the_array():
    out = r5_findings.parse_report(report([finding()]) + "\n\n   \n", "correctness")
    assert [f["claim"] for f in out["findings"]] == ["the v2 branch never fires"]


def test_an_empty_array_is_a_clean_report():
    out = parse([])
    assert out["findings"] == [] and out["counts"] == {"critical": 0, "important": 0, "minor": 0}


@pytest.mark.parametrize("text", [
    "",                                                   # nothing at all
    "### Verdict: PASS\n",                                # prose only, the old template
    report([finding()]) + "Done.\n",                      # prose after the line
    "R5-FINDINGS: {\"lens\": \"correctness\"}\n",         # an object, not an array
    "R5-FINDINGS: [{\"lens\": \"correctness\",}]\n",      # not JSON
    "R5-FINDINGS:\n",                                     # no array
])
def test_anything_else_is_unavailable(text):
    with pytest.raises(ReportError):
        r5_findings.parse_report(text, "correctness")


# --- the finding object

def test_severities_are_the_only_scale():
    """"Severities are the only scale": P1 is not a severity."""
    with pytest.raises(ReportError):
        parse([finding(severity="P1")])


def test_a_finding_belongs_to_its_reviewers_lens():
    with pytest.raises(ReportError):
        parse([finding(lens="clarity")])


def test_status_is_set_by_the_fixer_never_by_a_reviewer():
    """"status is set by the fixer, never by a reviewer"."""
    out = parse([finding(status="fixed")])
    assert out["findings"][0]["status"] == "open"
    assert out["counts"]["important"] == 1


def test_a_stored_fingerprint_is_never_the_key():
    """"A stored fingerprint is a cache, never a comparison key"."""
    out = parse([finding(fingerprint="0000000000000000")])
    assert out["findings"][0]["fingerprint"] == r5_findings.fingerprint(
        "correctness", "src/opensrm/parser/v2.py", "the v2 branch never fires")


def test_verification_level_is_the_ladder():
    with pytest.raises(ReportError):
        parse([finding(verification_level="proven")])


# --- "normalised claim": lower-case; replace each line reference and SHA-like
#      token with a single space; collapse whitespace; strip.

@pytest.mark.parametrize("claim, expected", [
    ("Guard fails at line 42", "guard fails at"),
    ("Guard fails at lines 4-9", "guard fails at"),
    ("Guard fails at lines 4–9", "guard fails at"),
    ("Guard fails at v2.py:42", "guard fails at v2.py"),
    ("Guard fails at v2.py:4-9", "guard fails at v2.py"),
    ("Guard fails at L42", "guard fails at"),
    ("Guard fails since 3f2a9c1", "guard fails since"),
    ("Guard fails since 1234567", "guard fails since"),   # "at least one digit": no letter needed
    ("A  Guard\nFAILS ", "a guard fails"),
])
def test_line_references_and_shas_go(claim, expected):
    assert r5_findings.normalise_claim(claim) == expected


def test_a_word_of_hex_letters_survives():
    """"at least one digit, so a word like "defaced" survives"."""
    assert r5_findings.normalise_claim("defaced cafebabe") == "defaced cafebabe"


def test_other_numbers_stay():
    """""exits 2" and "exits 4" are different claims"."""
    assert r5_findings.fingerprint("correctness", "a.py", "exits 2") != \
        r5_findings.fingerprint("correctness", "a.py", "exits 4")


def test_a_reference_is_replaced_by_a_space_not_deleted():
    """"with a single space": the corpus-v1 claim whose fingerprint went stale."""
    claim = "they contradict concepts/deployment-gates.md:41-45, which states it"
    assert r5_findings.normalise_claim(claim) == \
        "they contradict concepts/deployment-gates.md , which states it"


def test_the_corpus_uses_the_one_normaliser():
    """"NthLayer's scripts import it rather than reimplement it"."""
    claim = "they contradict concepts/deployment-gates.md:41-45, which states it"
    assert r5_corpus.normalise_claim(claim) == r5_findings.normalise_claim(claim)
    assert r5_corpus.fingerprint("clarity", "docs/tiers.md", claim) == \
        r5_findings.fingerprint("clarity", "docs/tiers.md", claim)
    assert r5_corpus.fingerprint("clarity", None, claim) == \
        r5_findings.fingerprint("clarity", "", claim)


# --- "A blocking finding below the configured floor (default script) is
#      labelled UNPROVEN ... Excellence is advisory and has nothing to prove."

def test_blocking_below_the_floor_is_unproven():
    out = parse([finding(verification_level="walked"),
                 finding(claim="second", verification_level="script"),
                 finding(claim="third", severity="MINOR", verification_level="asserted")])
    walked = r5_findings.fingerprint("correctness", "src/opensrm/parser/v2.py",
                                     "the v2 branch never fires")
    assert out["unproven"] == [walked]
    assert out["counts"]["important"] == 2           # UNPROVEN still blocks


def test_the_floor_is_configurable():
    out = parse([finding(verification_level="script")], floor="reproduced")
    assert len(out["unproven"]) == 1


def test_excellence_has_nothing_to_prove():
    out = parse([finding(lens="excellence", verification_level="asserted")], lens="excellence")
    assert out["unproven"] == []


# --- Closures (verify mode)

def prior(*records: dict, lens: str = "correctness") -> list:
    return parse(list(records), lens=lens)["open_set"]


def fp(claim: str, path: str = "src/opensrm/parser/v2.py") -> str:
    return r5_findings.fingerprint("correctness", path, claim)


def closure(target: str, **over) -> dict:
    return finding(**{"claim": "the mapping shape is now tested", "resolves": target,
                      "evidence": "test_v2_mapping passes; it failed before", **over})


def test_a_valid_closure_leaves_the_open_set_and_is_never_counted():
    """"never counted toward termination, whatever severity it carries"."""
    before = prior(finding())
    out = parse([closure(fp("the v2 branch never fires"), severity="CRITICAL")], prior_open=before)
    assert out["closures"] == [fp("the v2 branch never fires")]
    assert out["open_set"] == [] and out["counts"] == {"critical": 0, "important": 0, "minor": 0}


def test_a_closure_must_name_the_previous_open_set():
    out = parse([closure("abcdef0123456789")], prior_open=prior(finding()))
    assert [r["resolves"] for r in out["closure_rejected"]] == ["abcdef0123456789"]
    assert out["unaccounted"] == [fp("the v2 branch never fires")]


def test_a_closure_needs_evidence():
    before = prior(finding(), finding(claim="second"))
    out = parse([closure(fp("the v2 branch never fires"), evidence=""),
                 closure(fp("second"))], prior_open=before)
    assert [r["resolves"] for r in out["closure_rejected"]] == [fp("the v2 branch never fires")]
    assert out["closures"] == [fp("second")]


def test_a_second_closure_of_the_same_fingerprint_is_dropped():
    target = fp("the v2 branch never fires")
    out = parse([closure(target), closure(target, claim="also fixed")], prior_open=prior(finding()))
    assert out["closures"] == [target] and len(out["closure_rejected"]) == 1


def test_a_closure_s_own_fingerprint_is_never_compared_to_resolves():
    """A closure copying the prior claim is still a closure of it."""
    target = fp("the v2 branch never fires")
    out = parse([closure(target, claim="the v2 branch never fires")], prior_open=prior(finding()))
    assert out["closures"] == [target] and out["open_set"] == []


def test_a_re_raise_keeps_the_more_severe_severity():
    """"severity goes down only through a valid closure"."""
    out = parse([finding(severity="MINOR")], prior_open=prior(finding(severity="CRITICAL")))
    assert out["open_set"][0]["severity"] == "CRITICAL"
    assert out["downgrades_refused"] == [fp("the v2 branch never fires")]


def test_silence_never_closes():
    """"carried forward unchanged and tagged unaccounted"."""
    out = parse([], prior_open=prior(finding()))
    assert out["unaccounted"] == [fp("the v2 branch never fires")]
    assert out["open_set"][0]["unaccounted"] is True and out["counts"]["important"] == 1


def test_closing_everything_with_empty_evidence_is_unavailable():
    before = prior(finding(), finding(claim="second"))
    with pytest.raises(ReportError):
        parse([closure(fp("the v2 branch never fires"), evidence=""),
               closure(fp("second"), evidence="")], prior_open=before)


# --- the CLI: exit 0, 2 for UNAVAILABLE, 1 for the caller's mistake

def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_cli_exit_codes(tmp_path):
    good, bad, prior_file = tmp_path / "good.md", tmp_path / "bad.md", tmp_path / "prior.json"
    good.write_text(report([finding()]))
    bad.write_text("### Verdict: PASS\n")
    prior_file.write_text(json.dumps(prior(finding(severity="CRITICAL"))))
    done = cli("parse", "correctness", str(good), "--prior", str(prior_file))
    assert done.returncode == 0
    assert json.loads(done.stdout)["counts"]["critical"] == 1
    assert cli("parse", "correctness", str(bad)).returncode == 2
    assert cli("parse", "style", str(good)).returncode == 1
    assert cli("parse", "correctness", str(good), "--floor").returncode == 1
    assert cli("parse", "correctness", str(tmp_path / "missing.md")).returncode == 1


# --- compare: the dry-run acceptance (spec section 3, bead 3)

def recorded(*rounds: tuple) -> dict:
    """recorded.json as corpus-v1 holds it: lens in schema form, a stale or
    absent evidence, and the corpus's own (possibly stale) fingerprint."""
    return {"rounds": [{"lens": lens, "iteration": it, "findings": fs} for lens, it, fs in rounds]}


def replay(*events: tuple) -> dict:
    return {"audit_trail": [{"event": "findings_received", "pass": p, "findings": fs}
                            for p, fs in events]}


STALE = {"fingerprint": "ffffffffffffffff", "evidence": None}


def test_compare_recomputes_fingerprints_on_both_sides():
    rec = recorded(("edge_cases", 1, [finding(lens="edge_cases", **STALE)]))
    rep = replay(("edge-cases", [finding(lens="edge_cases", claim="The  v2 branch never FIRES L9")]))
    out = r5_findings.compare_records(rec, rep)
    assert [m["claim"] for m in out["matched"]] == ["the v2 branch never fires"]
    assert out["unmatched"] == [] and out["replay_only"] == []


def test_compare_lists_what_is_left_for_a_claim_ruling():
    rec = recorded(("correctness", 1, [finding(**STALE)]))
    rep = replay(("correctness", [finding(path="src/opensrm/parser/v1.py")]))
    out = r5_findings.compare_records(rec, rep)
    assert [u["path"] for u in out["unmatched"]] == ["src/opensrm/parser/v2.py"]
    assert [r["path"] for r in out["replay_only"]] == ["src/opensrm/parser/v1.py"]


def test_compare_keeps_later_iterations_apart():
    rec = recorded(("correctness", 1, []), ("correctness", 2, [finding(**STALE)]))
    out = r5_findings.compare_records(rec, replay(("correctness", [])))
    assert out["unmatched"] == []
    assert [(f["iteration"], f["matched"]) for f in out["later_iterations"]] == [(2, False)]


def test_compare_reports_a_lowered_severity():
    rec = recorded(("correctness", 1, [finding(severity="CRITICAL", **STALE)]))
    out = r5_findings.compare_records(rec, replay(("correctness", [finding(severity="IMPORTANT")])))
    assert [(s["severity"], s["replayed"]) for s in out["severity_lowered"]] == [("CRITICAL", "IMPORTANT")]


def test_compare_counts_blocking_findings_of_blocking_lenses_only():
    rec = recorded(("correctness", 1, [finding(severity="MINOR", **STALE)]),
                   ("excellence", 1, [finding(lens="excellence", **STALE)]))
    rep = replay(("excellence", [finding(lens="excellence")]),
                 ("correctness", [finding(severity="MINOR")]))
    out = r5_findings.compare_records(rec, rep)
    assert out == {"matched": [], "severity_lowered": [], "unmatched": [],
                   "later_iterations": [], "replay_only": []}


def test_compare_reads_only_the_first_review_of_a_lens():
    rec = recorded(("correctness", 1, [finding(**STALE)]))
    rep = replay(("correctness", []), ("correctness", [finding()]))
    out = r5_findings.compare_records(rec, rep)
    assert len(out["unmatched"]) == 1 and out["replay_only"] == []


def test_compare_skips_an_event_that_is_not_a_parsed_review():
    """r5-supervise Step 3: a provenance reviewer that left the tree dirty is
    logged as findings_received with reviewer_left_tree_dirty and no findings."""
    rec = recorded(("provenance", 1, [finding(lens="provenance", **STALE)]))
    rep = {"audit_trail": [
        {"event": "findings_received", "pass": "provenance", "reviewer_left_tree_dirty": True},
        {"event": "findings_received", "pass": "provenance", "findings": [finding(lens="provenance")]}]}
    out = r5_findings.compare_records(rec, rep)
    assert len(out["matched"]) == 1 and out["unmatched"] == []


# --- prose_unfiled, section 6 "Prose and entries": "The parser logs
#     prose_unfiled, as {"heading": "", "text": ""}, for each item under a
#     severity heading with no matching entry and each Not filed line with no
#     reason". The prose shape is the templates' Output Format: bold-led items
#     under severity headings, e.g. correctness-reviewer.md "#### Important ...
#     1. **[Short description]**".

PROSE = """### Correctness Issues

#### Critical
None.

#### Important
1. **The stub is pinned instead of failing**
   - File: tests/golden/test_golden_legacy_cli.py:157
   - What's wrong: except Exception catches AssertionError

#### Minor
- **Docstring names one stub only**

```
#### Important
1. **not an item: inside a fence**
```
"""


def test_an_issue_in_the_prose_with_no_entry_is_prose_unfiled():
    out = r5_findings.parse_report(report([finding(severity="MINOR")], prose=PROSE), "correctness")
    assert out["prose_unfiled"] == [{"heading": "IMPORTANT", "text": "The stub is pinned instead of failing"}]
    assert out["counts"]["important"] == 0          # telemetry: it never blocks or fails


def test_every_prose_issue_filed_is_not_prose_unfiled():
    out = r5_findings.parse_report(
        report([finding(), finding(claim="docstring", severity="MINOR")], prose=PROSE), "correctness")
    assert out["prose_unfiled"] == []


def test_a_closure_does_not_count_as_filing_a_prose_issue():
    before = prior(finding())
    out = r5_findings.parse_report(
        report([closure(fp("the v2 branch never fires")), finding(claim="docstring", severity="MINOR")],
               prose=PROSE), "correctness", prior_open=before)
    assert [u["heading"] for u in out["prose_unfiled"]] == ["IMPORTANT"]
    assert out["closures"] == [fp("the v2 branch never fires")]


def test_none_and_sub_bullets_are_not_issues():
    prose = "#### Critical\nNone.\n\n#### Important\nNone.\n   - **indented, a sub-bullet**\n"
    assert r5_findings.parse_report(report([], prose=prose), "correctness")["prose_unfiled"] == []


def test_a_plain_bullet_under_a_heading_is_an_issue():
    """Reviewers also write MINORs as plain bullets: ``- tests/x.py:12 foo``."""
    prose = "#### Minor\n- tests/golden/x.py:277 results matched by position\n"
    out = r5_findings.parse_report(report([], prose=prose), "correctness")
    assert out["prose_unfiled"] == [{"heading": "MINOR", "text": "tests/golden/x.py:277 results matched by position"}]


def test_a_list_after_none_or_a_prose_line_is_not_issues():
    prose = ("#### Minor\nNone.\n\nChecks performed:\n- patch targets match\n\n"
             "#### Important\n- **a real one**\n\nVerified with no finding:\n- each cell\n")
    out = r5_findings.parse_report(report([], prose=prose), "correctness")
    assert out["prose_unfiled"] == [{"heading": "IMPORTANT", "text": "a real one"}]


def test_with_fewer_entries_the_least_matching_item_is_unfiled():
    prose = ("#### Important\n1. **The stub is pinned instead of failing**\n"
             "2. **Recording rules are sorted in the CLI cells**\n")
    out = r5_findings.parse_report(
        report([finding(claim="Env.files sorts recording rules in the CLI cells")], prose=prose), "correctness")
    assert out["prose_unfiled"] == [{"heading": "IMPORTANT", "text": "The stub is pinned instead of failing"}]


# "A remark that is not a finding goes under a Not filed heading, one line
#  each, ending in its reason: out_of_scope, pre_existing or not_an_issue."

def test_a_not_filed_line_needs_its_reason():
    prose = ("#### Not filed\n"
             "- The old cells sort too; pre_existing\n"
             "- `id` masking in dashboards is documented — not_an_issue\n"
             "- Panel ids are masked globally (out_of_scope)\n"
             "- The loader walks up from the cwd\n")
    out = r5_findings.parse_report(report([], prose=prose), "correctness")
    assert out["prose_unfiled"] == [{"heading": "Not filed", "text": "The loader walks up from the cwd"}]
    assert out["counts"] == {"critical": 0, "important": 0, "minor": 0}


def test_a_not_filed_line_is_never_an_unfiled_finding():
    """A reasoned remark under Not filed is not compared with the array."""
    prose = "### Not filed\n- **Bold remark** about scope; out_of_scope\n"
    assert r5_findings.parse_report(report([], prose=prose), "correctness")["prose_unfiled"] == []
