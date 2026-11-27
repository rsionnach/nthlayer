"""The content options of three_tier_assertions.py's wait commands, against a
real nthlayer-core in one process (opensrm-yze8).

``integration-three-tier.sh`` and ``e2e-test.sh`` used to assert that a
breach verdict, a snapshot, a triage verdict and a case EXIST. They now
assert what those rows say. The full run is nightly and needs the whole
stack; this file checks the commands on every pull request that touches
them, and above all that each one refuses a row with the wrong content: a
content check nobody has seen fail is a presence check with more arguments.

The rows seeded here have the shapes nthlayer-workers writes, read from its
source at ``main`` on 2026-11-27, not from this helper:

- measure's SLO breach, ``measure/worker.py``: ``data`` = slo_name, slo_key,
  severity, judgment_type, target, current_value (percentages, opensrm-5fff.1).
- correlate's snapshot, ``correlate/worker.py``: ``data.domain.service``,
  ``data.event_count``, ``data.parent_ids`` (the triggering breach ids).
- respond's case, ``respond/worker.py``: ``underlying_verdict`` is the
  breach id.

The severities expected of a breach are nthlayer-workers' documented
thresholds (its ``docs/architecture.md``, measure: under 200% of the error
budget consumed is low, 200 to 500% high, over 500% critical), worked by hand
in BUDGET_CASES below, not computed by the code under test.

The bench check is exercised with a stand-in for ``fetch_case_bench``: this
environment is core's and has no nthlayer-bench. The real bench call is
covered by the integration run.

CI: ``.github/workflows/retrospective-seam.yml``, siblings at ``main``. By
hand, from the ecosystem root:

    uv run --frozen --directory nthlayer-core --extra dev python -m pytest \\
        -o asyncio_mode=auto ../nthlayer/test/test_three_tier_content.py
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from nthlayer_common.api_client import CoreAPIClient
from nthlayer_core import server
from nthlayer_core.store import Store

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "three_tier_assertions_content", HERE / "three_tier_assertions.py",
)
assert _spec and _spec.loader
tta = importlib.util.module_from_spec(_spec)
sys.modules["three_tier_assertions_content"] = tta
_spec.loader.exec_module(tta)

CORE_URL = "http://core-in-process"
BREACH = "vrd-breach-fraud-detect-reversal_rate-1a2b3c4d"
SNAPSHOT = "csn-fraud-detect-production-1a2b3c4d"


class _InProcessClient(CoreAPIClient):
    """CoreAPIClient, with its HTTP client pointed at core's ASGI app."""

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                transport=ASGITransport(app=server.app), base_url=self.base_url,
            )
        return self._client


@pytest.fixture
def store(tmp_path):
    store = Store(str(tmp_path / "core.db"))
    server.set_store(store)
    return store


@pytest.fixture
def core(store, monkeypatch):
    """The real app over a real Store, and the commands' client rewired to it."""
    monkeypatch.setattr(tta, "CoreAPIClient", _InProcessClient)
    return _InProcessClient(base_url=CORE_URL)


def _args(**kwargs) -> argparse.Namespace:
    """A command's arguments. The poll is short: a row that does not match
    never will, so a refusal costs a fraction of a second."""
    defaults = {
        "core_url": CORE_URL, "timeout": 0.3, "interval": 0.05, "service": None,
        "where": None, "contains": None, "at_least": None, "severity_by_budget": False,
    }
    return argparse.Namespace(**{**defaults, **kwargs})


def _kv(capsys) -> dict[str, str]:
    return dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines() if line)


async def _post(result_coro) -> None:
    result = await result_coro
    assert result.ok, (result.status_code, result.error, result.detail)


def _breach_data(**overrides) -> dict:
    """measure's breach data for the harness scenario: reversal_rate, target
    98.5, settled SLI 92.0, which is 433% of the budget: high."""
    data = {
        "slo_name": "reversal_rate", "slo_key": "fraud-detect/reversal_rate",
        "severity": "high", "judgment_type": "reversal_rate",
        "target": 98.5, "current_value": 92.0,
    }
    return {**data, **overrides}


async def _breach(core, *, breach_id: str = BREACH, service: str = "fraud-detect",
                  minute: int = 0, **data) -> None:
    await _post(core.submit_verdict({
        "id": breach_id, "type": "quality_breach", "service": service,
        "created_at": f"2026-11-27T10:{minute:02d}:00+00:00", "parent_ids": [],
        "data": _breach_data(**data),
    }))


BREACH_ARGS = {
    "verdict_type": "quality_breach", "service": "fraud-detect",
    "where": ["data.slo_name=reversal_rate", "data.judgment_type=reversal_rate",
              "data.target=98.5"],
    "severity_by_budget": True,
}


# --- the severity table ------------------------------------------------------

# (target, current_value, severity). Consumption = (target - current) /
# (100 - target) * 100, worked by hand against the documented thresholds.
BUDGET_CASES = [
    (98.5, 98.0, "low"),        # 0.5 / 1.5 = 33%
    (98.5, 95.6, "low"),        # 2.9 / 1.5 = 193%
    (98.5, 95.5, "high"),       # 3.0 / 1.5 = 200%, the boundary is high
    (98.5, 92.0, "high"),       # 6.5 / 1.5 = 433%, the harness's settled SLI
    (98.5, 91.0, "critical"),   # 7.5 / 1.5 = 500%, the boundary is critical
    (98.5, 60.0, "critical"),   # 38.5 / 1.5 = 2567%
    (99.0, 97.5, "low"),        # 1.5 / 1.0 = 150%
    (99.0, 96.0, "high"),       # 3.0 / 1.0 = 300%
    (100.0, 99.9, "critical"),  # no budget at all
]


@pytest.mark.parametrize(("target", "current", "severity"), BUDGET_CASES)
def test_budget_severity_follows_the_documented_thresholds(target, current, severity):
    assert len(BUDGET_CASES) == 9
    assert tta.budget_severity(target, current) == severity


# --- finding 1: the breach ---------------------------------------------------


async def test_a_consistent_breach_is_accepted(core, capsys):
    await _breach(core)

    await tta.cmd_wait_verdict_type(_args(**BREACH_ARGS))

    assert _kv(capsys) == {
        "VERDICT_ID": BREACH,
        "VERDICT_CREATED_AT": "2026-11-27T10:00:00+00:00",
        "VERDICT_SERVICE": "fraud-detect",
        "VERDICT_SEVERITY": "high",
    }


@pytest.mark.parametrize(("current", "severity"), [(98.0, "low"), (92.0, "high"), (60.0, "critical")])
async def test_each_severity_is_accepted_when_the_value_earns_it(core, capsys, current, severity):
    """The first breach may fire anywhere between just under target and the
    settled SLI, so no one severity is expected, only the consistent one."""
    await _breach(core, current_value=current, severity=severity)

    await tta.cmd_wait_verdict_type(_args(**BREACH_ARGS))

    assert _kv(capsys)["VERDICT_SEVERITY"] == severity


# What opensrm-pa2w shipped (critical for every breach), and the other ways a
# breach's content can be wrong while a breach still exists.
WRONG_BREACHES = [
    {"severity": "critical"},                               # pa2w: 433% is high
    {"severity": "low"},
    {"current_value": 98.0, "severity": "high"},            # 33% is low
    {"severity": None},
    {"target": 0.985, "current_value": 0.92},               # ratios, not percentages
    {"current_value": 0.92},                                # a ratio beside a percentage
    {"current_value": 99.0, "severity": "low"},             # not below target: no breach
    {"current_value": None},
    {"target": 99.0, "severity": "critical"},               # not the manifest's target
    {"slo_name": "availability"},
    {"judgment_type": None},
]


@pytest.mark.parametrize("wrong", WRONG_BREACHES)
async def test_a_breach_with_wrong_content_is_refused(core, capsys, wrong):
    assert len(WRONG_BREACHES) == 11
    await _breach(core, **wrong)
    # The same row passes the presence check this replaces.
    await tta.cmd_wait_verdict_type(_args(verdict_type="quality_breach", service="fraud-detect"))
    assert _kv(capsys)["VERDICT_ID"] == BREACH

    with pytest.raises(TimeoutError):
        await tta.cmd_wait_verdict_type(_args(**BREACH_ARGS))

    assert capsys.readouterr().out == ""


async def test_the_matching_breach_is_found_behind_a_newer_one_that_does_not_match(core, capsys):
    """Core returns verdicts newest first. A second, newer row must not hide
    the one the harness is waiting for (the review's finding 8)."""
    await _breach(core, minute=0)
    await _breach(core, breach_id="vrd-breach-newer", minute=5, slo_name="availability")

    await tta.cmd_wait_verdict_type(_args(**BREACH_ARGS))

    assert _kv(capsys)["VERDICT_ID"] == BREACH


async def test_no_options_still_means_the_newest_row(core, capsys):
    await _breach(core, minute=0)
    await _breach(core, breach_id="vrd-breach-newer", minute=5, slo_name="availability")

    await tta.cmd_wait_verdict_type(_args(verdict_type="quality_breach", service="fraud-detect"))

    assert _kv(capsys)["VERDICT_ID"] == "vrd-breach-newer"


# --- finding 2: the snapshot -------------------------------------------------


async def _snapshot(core, *, service: str = "fraud-detect", parent_ids=(BREACH,),
                    event_count: int = 3, snapshot_id: str = SNAPSHOT) -> None:
    await _post(core.submit_assessment({
        "id": snapshot_id, "kind": "correlation_snapshot", "service": service,
        "created_at": "2026-11-27T10:01:00+00:00",
        "data": {
            "domain": {"service": service, "environment": "production"},
            "event_count": event_count, "parent_ids": list(parent_ids),
        },
    }))


def _snapshot_args() -> argparse.Namespace:
    return _args(
        kind="correlation_snapshot", service="fraud-detect",
        where=["data.domain.service=fraud-detect"],
        contains=[f"data.parent_ids={BREACH}"], at_least=["data.event_count=1"],
    )


async def test_the_snapshot_that_names_the_breach_is_accepted(core, capsys):
    await _snapshot(core)

    await tta.cmd_wait_assessment_kind(_snapshot_args())

    assert _kv(capsys)["ASSESSMENT_ID"] == SNAPSHOT


WRONG_SNAPSHOTS = [
    {"parent_ids": ("vrd-breach-of-another-run",)},
    {"parent_ids": ()},
    {"event_count": 0},
    {"service": "payment-api"},
]


@pytest.mark.parametrize("wrong", WRONG_SNAPSHOTS)
async def test_a_snapshot_with_wrong_content_is_refused(core, capsys, wrong):
    assert len(WRONG_SNAPSHOTS) == 4
    await _snapshot(core, **wrong)
    # Present, for the check this replaces (which named no service).
    await tta.cmd_wait_assessment_kind(_args(kind="correlation_snapshot"))
    assert _kv(capsys)["ASSESSMENT_ID"] == SNAPSHOT

    with pytest.raises(TimeoutError):
        await tta.cmd_wait_assessment_kind(_snapshot_args())

    assert capsys.readouterr().out == ""


# --- finding 4: the case's anchor --------------------------------------------


async def _case(core, *, underlying_verdict: str = BREACH) -> None:
    await _breach(core)
    await _post(core.create_case({
        "id": "case-1", "kind": "incident", "created_at": "2026-11-27T10:02:00+00:00",
        "underlying_verdict": underlying_verdict, "service": "fraud-detect", "priority": "P1",
    }))


async def test_the_case_anchored_on_the_breach_is_accepted(core, capsys):
    await _case(core)

    await tta.cmd_wait_case(_args(service="fraud-detect", where=[f"underlying_verdict={BREACH}"]))

    assert _kv(capsys)["CASE_UNDERLYING_VERDICT"] == BREACH


async def test_a_case_anchored_on_another_verdict_is_refused(core, capsys):
    await _breach(core, breach_id="vrd-breach-of-another-run", minute=1)
    await _case(core, underlying_verdict="vrd-breach-of-another-run")
    await tta.cmd_wait_case(_args(service="fraud-detect"))
    assert _kv(capsys)["CASE_ID"] == "case-1"

    with pytest.raises(TimeoutError):
        await tta.cmd_wait_case(
            _args(service="fraud-detect", where=[f"underlying_verdict={BREACH}"]),
        )

    assert capsys.readouterr().out == ""


# --- finding 7: heartbeat health ---------------------------------------------


async def test_a_fresh_heartbeat_is_healthy(core, capsys):
    await _post(core.heartbeat("measure", "instance-1"))

    await tta.cmd_wait_heartbeat(_args(component=None, expect_health="healthy"))

    assert _kv(capsys) == {"HEARTBEAT_COMPONENT": "measure", "HEARTBEAT_HEALTH": "healthy"}


async def test_a_stale_heartbeat_is_refused_as_healthy(core, store, capsys):
    """Core calls a component degraded once its heartbeat is older than the
    threshold. The row still exists, which is all the old check asked."""
    await _post(core.heartbeat("measure", "instance-1"))
    conn = store._get_conn()
    conn.execute("UPDATE heartbeats SET last_seen = '2026-01-01T00:00:00+00:00'")
    conn.commit()
    await tta.cmd_wait_heartbeat(_args(component=None, expect_health=None))
    assert _kv(capsys)["HEARTBEAT_HEALTH"] == "degraded"

    with pytest.raises(TimeoutError):
        await tta.cmd_wait_heartbeat(_args(component=None, expect_health="healthy"))

    assert capsys.readouterr().out == ""


# --- finding 6: bench returns THIS case --------------------------------------


@pytest.fixture
def bench(monkeypatch):
    """A stand-in for nthlayer_bench.sre.case_bench, which core's environment
    does not have: fetch_case_bench returns a view of the given case ids."""
    returned: list[str] = []

    async def fetch_case_bench(client, *, state, limit):
        flat = [types.SimpleNamespace(case_id=cid, priority="P1") for cid in returned]
        return types.SimpleNamespace(flat=flat)

    module = types.ModuleType("nthlayer_bench.sre.case_bench")
    module.fetch_case_bench = fetch_case_bench
    for name in ("nthlayer_bench", "nthlayer_bench.sre"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "nthlayer_bench.sre.case_bench", module)
    return returned


def _bench_args(expect_case_id: str | None) -> argparse.Namespace:
    return argparse.Namespace(core_url=CORE_URL, state="pending", limit=50,
                              expect_case_id=expect_case_id)


async def test_bench_returning_the_case_is_accepted(core, bench, capsys):
    bench.extend(["case-older", "case-1"])

    await tta.cmd_fetch_case_via_bench(_bench_args("case-1"))

    assert _kv(capsys)["BENCH_CASE_COUNT"] == "2"


async def test_bench_returning_only_other_cases_is_refused(core, bench, capsys):
    bench.append("case-older")
    await tta.cmd_fetch_case_via_bench(_bench_args(None))
    assert _kv(capsys)["BENCH_CASE_ID"] == "case-older"

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_fetch_case_via_bench(_bench_args("case-1"))

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == ""


# --- PATH=VALUE ---------------------------------------------------------------

# What a caller types -> what the row must hold. Only a finite number is read
# as a number; everything else, ids and JSON-looking words included, is the
# string it is.
SPLIT_CASES = [
    ("data.target=98.5", ("data.target", 98.5)),
    ("data.event_count=1", ("data.event_count", 1)),
    (f"underlying_verdict={BREACH}", ("underlying_verdict", BREACH)),
    ("data.label=true", ("data.label", "true")),
    ("data.label=null", ("data.label", "null")),
    ("data.label=NaN", ("data.label", "NaN")),
    ("data.label=Infinity", ("data.label", "Infinity")),
    ("data.note=a=b", ("data.note", "a=b")),
    ("data.note=", ("data.note", "")),
]


@pytest.mark.parametrize(("spec", "expected"), SPLIT_CASES)
def test_a_value_is_a_number_only_when_it_reads_as_a_finite_one(spec, expected):
    assert len(SPLIT_CASES) == 9
    path, value = tta._split(spec)
    assert (path, value, type(value)) == (*expected, type(expected[1]))


@pytest.mark.parametrize("spec", ["no-equals-sign", "=value"])
def test_a_spec_without_a_path_or_a_value_is_refused(spec):
    with pytest.raises(SystemExit) as exc_info:
        tta._split(spec)
    assert exc_info.value.code == 1


async def test_a_string_field_matches_a_word_that_is_also_json(core, capsys):
    await _breach(core, slo_name="true")

    await tta.cmd_wait_verdict_type(_args(
        verdict_type="quality_breach", service="fraud-detect", where=["data.slo_name=true"],
    ))

    assert _kv(capsys)["VERDICT_ID"] == BREACH


# --- the option parser, as the scripts call it -------------------------------


async def test_the_scripts_argument_lists_parse_and_pass(core, capsys):
    """The exact options integration-three-tier.sh passes, through main()."""
    await _case(core)
    await _snapshot(core)
    common = ["--core-url", CORE_URL, "--timeout", "0.3", "--interval", "0.05"]

    codes = [
        await _main(["wait-verdict-type", "quality_breach", "--service", "fraud-detect",
                     "--where", "data.slo_name=reversal_rate",
                     "--where", "data.judgment_type=reversal_rate",
                     "--where", "data.target=98.5", "--severity-by-budget", *common]),
        await _main(["wait-assessment-kind", "correlation_snapshot", "--service", "fraud-detect",
                     "--where", "data.domain.service=fraud-detect",
                     "--contains", f"data.parent_ids={BREACH}",
                     "--at-least", "data.event_count=1", *common]),
        await _main(["wait-case", "--service", "fraud-detect",
                     "--where", f"underlying_verdict={BREACH}", *common]),
    ]

    assert codes == [0, 0, 0]
    assert _kv(capsys)["CASE_UNDERLYING_VERDICT"] == BREACH


async def test_main_exits_one_when_the_content_never_matches(core, capsys):
    await _breach(core, severity="critical")

    code = await _main(["wait-verdict-type", "quality_breach", "--service", "fraud-detect",
                        "--severity-by-budget", "--core-url", CORE_URL,
                        "--timeout", "0.3", "--interval", "0.05"])

    assert code == 1
    assert capsys.readouterr().out == ""


async def _main(argv: list[str]) -> int:
    """main() calls asyncio.run, which cannot nest in the test's loop: run it
    in a worker thread."""
    import asyncio

    return await asyncio.to_thread(tta.main, argv)
