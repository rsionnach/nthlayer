"""The retrospective-seam commands of three_tier_assertions.py against a real
nthlayer-core, in one process (opensrm-mtxr).

``integration-three-tier.sh`` uses these commands to play the operator and
to assert learn's retrospective. That run is nightly and needs the whole
stack; this file checks the commands themselves, and core's half of the
seam, on every pull request that touches them: core's own app and Store,
reached through the commands' own ``CoreAPIClient`` over an ASGI transport.

What it pins about core: a verdict whose ``parent_ids`` name a correlation
snapshot (an ASSESSMENT id), and the verdicts chained after it, come back
from ``GET /verdicts/{snapshot id}/descendants``; ``PUT /cases/{id}/resolve``
takes a case out of the open states. nthlayer-workers' learn leans on both
(``fetch_incident_chain``, ``has_open_case``); core's own test of the first
is opensrm-brms. When opensrm-7t3q's typed relations land, this file, those
two and the harness change together.

(``--frozen`` below keeps a by-hand run from rewriting core's uv.lock when
the sibling nthlayer-common is newer than the one it locks.)

CI: ``.github/workflows/retrospective-seam.yml``, siblings at ``main``. By
hand, from the ecosystem root:

    uv run --frozen --directory nthlayer-core --extra dev python -m pytest \\
        -o asyncio_mode=auto ../nthlayer/test/test_three_tier_retrospective.py
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from nthlayer_common.api_client import APIResult, CoreAPIClient
from nthlayer_core import server
from nthlayer_core.store import Store

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("three_tier_assertions", HERE / "three_tier_assertions.py")
assert _spec and _spec.loader
tta = importlib.util.module_from_spec(_spec)
sys.modules["three_tier_assertions"] = tta
_spec.loader.exec_module(tta)

CORE_URL = "http://core-in-process"
SNAPSHOT = "csn-fraud-detect-production-1a2b3c4d"
BREACH = "vrd-breach-1"


class _InProcessClient(CoreAPIClient):
    """CoreAPIClient, with its HTTP client pointed at core's ASGI app."""

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                transport=ASGITransport(app=server.app), base_url=self.base_url,
            )
        return self._client


@pytest.fixture
def core(tmp_path, monkeypatch):
    """A real core Store behind the real app, and the commands' client
    rewired to reach it."""
    store = Store(str(tmp_path / "core.db"))
    server.set_store(store)
    monkeypatch.setattr(tta, "CoreAPIClient", _InProcessClient)
    return _InProcessClient(base_url=CORE_URL)


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(core_url=CORE_URL, **kwargs)


def _kv(capsys) -> dict[str, str]:
    """The KEY=value lines a command printed."""
    return dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines() if line)


async def _post(result_coro) -> None:
    result = await result_coro
    assert result.ok, (result.status_code, result.error, result.detail)


async def _seed_incident(core, *, snapshot_id: str = SNAPSHOT, breach_id: str = BREACH,
                         minute: int = 0, steps=("triage", "investigation", "remediation"),
                         case: bool = True) -> list[str]:
    """One incident as the tiers leave it on core: measure's breach verdict,
    correlate's snapshot (its ``data.parent_ids`` name the breach), respond's
    verdicts (the first names [snapshot id, breach id] as parents, each later
    one the one before), and respond's case, anchored on the breach."""
    def at(m: int) -> str:
        return f"2026-11-25T10:{minute + m:02d}:00+00:00"

    if (await core.get_verdict(breach_id)).status_code == 404:
        await _post(core.submit_verdict({
            "id": breach_id, "type": "quality_breach", "service": "fraud-detect",
            "created_at": at(0), "parent_ids": [],
        }))
    await _post(core.submit_assessment({
        "id": snapshot_id, "kind": "correlation_snapshot", "service": "fraud-detect",
        "created_at": at(1),
        "data": {"domain": {"service": "fraud-detect"}, "parent_ids": [breach_id]},
    }))
    ids: list[str] = []
    for n, step in enumerate(steps):
        vid = f"vrd-{snapshot_id}-{step}"
        await _post(core.submit_verdict({
            "id": vid, "type": step, "service": "fraud-detect", "created_at": at(2 + n),
            "parent_ids": [ids[-1]] if ids else [snapshot_id, breach_id],
        }))
        ids.append(vid)
    if case:
        await _post(core.create_case({
            "id": f"case-{snapshot_id}", "kind": "incident", "created_at": at(2),
            "underlying_verdict": breach_id, "service": "fraud-detect", "priority": "P1",
        }))
    return ids


async def _retrospective(core, snapshot_id: str = SNAPSHOT, *, closed_by: str = "quiet",
                         timeline_ids=(), retro_id: str | None = None) -> None:
    """A retrospective as learn writes it: id ``retro-<snapshot id>``."""
    await _post(core.submit_assessment({
        "id": retro_id or f"retro-{snapshot_id}", "kind": "retrospective",
        "service": "fraud-detect", "created_at": "2026-11-25T11:00:00+00:00",
        "data": {
            "correlation_snapshot_id": snapshot_id, "closed_by": closed_by,
            "verdict_count": len(timeline_ids),
            "timeline": [{"id": vid} for vid in timeline_ids],
        },
    }))


# --- core's half: descendants of an assessment id ---------------------------


async def test_the_snapshots_descendants_are_responds_chain(core):
    ids = await _seed_incident(core)

    result = await core.get_descendants(SNAPSHOT)

    assert result.ok
    assert [v["id"] for v in result.data] == ids


async def test_snapshot_of_verdict_names_the_incident_and_its_last_verdict(core, capsys):
    ids = await _seed_incident(core)
    await _seed_incident(core, snapshot_id="csn-other", breach_id="vrd-breach-2", minute=10)
    # An outcome resolution is not something respond did.
    await _post(core.resolve_outcome(ids[0], {"outcome_status": "confirmed"}))

    await tta.cmd_snapshot_of_verdict(_args(verdict_id=ids[-1]))

    assert _kv(capsys) == {
        "SNAPSHOT_ID": SNAPSHOT,
        "SNAPSHOT_SERVICE": "fraud-detect",
        "RESPOND_VERDICT_COUNT": "3",
        "RESPOND_LAST_VERDICT_ID": ids[-1],
        "RESPOND_LAST_VERDICT_TYPE": "remediation",
    }


async def test_snapshot_of_verdict_fails_for_a_verdict_no_snapshot_claims(core, capsys):
    await _seed_incident(core)

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_snapshot_of_verdict(_args(verdict_id=BREACH))

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == ""


async def test_snapshot_of_verdict_fails_for_a_verdict_two_snapshots_claim(core, capsys):
    """One verdict, two snapshots among its parents: which incident it
    belongs to cannot be told, and the harness must not guess."""
    ids = await _seed_incident(core)
    await _seed_incident(core, snapshot_id="csn-other", breach_id="vrd-breach-2", minute=10)
    await _post(core.submit_verdict({
        "id": "vrd-shared", "type": "remediation", "service": "fraud-detect",
        "created_at": "2026-11-25T10:30:00+00:00", "parent_ids": [SNAPSHOT, "csn-other"],
    }))

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_snapshot_of_verdict(_args(verdict_id="vrd-shared"))

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == ""
    # A verdict only one of them claims is still found.
    await tta.cmd_snapshot_of_verdict(_args(verdict_id=ids[0]))
    assert _kv(capsys)["SNAPSHOT_ID"] == SNAPSHOT


# --- no retrospective while the case is open --------------------------------


async def test_assert_no_retrospective_passes_when_only_another_snapshot_has_one(core, capsys):
    await _seed_incident(core)
    await _retrospective(core, "csn-other")

    await tta.cmd_assert_no_retrospective(_args(snapshot_id=SNAPSHOT))

    assert _kv(capsys) == {"NO_RETROSPECTIVE_OK": "true"}


async def test_assert_no_retrospective_fails_when_the_snapshot_has_one(core, capsys):
    await _seed_incident(core)
    await _retrospective(core, closed_by="max_age")

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_assert_no_retrospective(_args(snapshot_id=SNAPSHOT))

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == ""


# --- the operator resolves the case -----------------------------------------


async def test_the_operator_resolves_the_incidents_case_and_no_other(core, capsys):
    ids = await _seed_incident(core)
    await _seed_incident(core, snapshot_id="csn-other", breach_id="vrd-breach-2", minute=10)

    await tta.cmd_resolve_cases_for_snapshot(
        _args(snapshot_id=SNAPSHOT, resolution_id=ids[-1])
    )

    assert _kv(capsys) == {
        "CASES_RESOLVED": "1", "RESOLVED_CASE_IDS": f"case-{SNAPSHOT}",
    }
    mine = (await core.get_case(f"case-{SNAPSHOT}")).data
    other = (await core.get_case("case-csn-other")).data
    assert (mine["state"], mine["resolution_id"]) == ("resolved", ids[-1])
    assert other["state"] == "pending"
    # What learn asks core before closing on quiet: no open case is left
    # anchored on the incident's trigger.
    open_cases = [
        c for state in ("pending", "leased")
        for c in (await core.get_cases(state=state, service="fraud-detect")).data
    ]
    assert BREACH not in {c["underlying_verdict"] for c in open_cases}


async def test_two_incidents_on_one_breach_have_both_cases_resolved(core, capsys):
    """Respond opens a case per incident, each anchored on the breach, and
    either holds the retrospective back."""
    ids = await _seed_incident(core)
    await _seed_incident(core, snapshot_id="csn-second", minute=10)

    await tta.cmd_resolve_cases_for_snapshot(
        _args(snapshot_id=SNAPSHOT, resolution_id=ids[-1])
    )

    assert _kv(capsys)["CASES_RESOLVED"] == "2"
    assert (await core.get_cases(state="pending", service="fraud-detect")).data == []


async def test_a_case_an_operator_has_leased_is_resolved_too(core, capsys):
    """Core's other open state. learn holds the retrospective for it as it
    does for a pending case."""
    ids = await _seed_incident(core)
    await _post(core.acquire_lease(f"case-{SNAPSHOT}", "operator-1", "2099-01-01T00:00:00+00:00"))
    assert (await core.get_cases(state="pending", service="fraud-detect")).data == []

    await tta.cmd_resolve_cases_for_snapshot(
        _args(snapshot_id=SNAPSHOT, resolution_id=ids[-1])
    )

    assert _kv(capsys)["RESOLVED_CASE_IDS"] == f"case-{SNAPSHOT}"
    assert (await core.get_case(f"case-{SNAPSHOT}")).data["state"] == "resolved"


@pytest.mark.parametrize("already", [False, True])
async def test_resolving_fails_when_there_is_no_open_case_for_the_incident(core, capsys, already):
    ids = await _seed_incident(core, case=already)
    if already:
        await _post(core.resolve_case(f"case-{SNAPSHOT}", ids[-1]))

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_resolve_cases_for_snapshot(
            _args(snapshot_id=SNAPSHOT, resolution_id=ids[-1])
        )

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == ""


async def test_a_resolve_that_core_refuses_is_not_reported_as_resolved(core, capsys, monkeypatch):
    """The PUT does not go through: the harness must stop there, not go on
    to wait for a retrospective the open case still holds back."""
    class _RefusedResolve(_InProcessClient):
        async def resolve_case(self, case_id: str, resolution_id: str) -> APIResult:
            return APIResult(ok=False, status_code=503, error="unavailable")

    ids = await _seed_incident(core)
    monkeypatch.setattr(tta, "CoreAPIClient", _RefusedResolve)

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_resolve_cases_for_snapshot(
            _args(snapshot_id=SNAPSHOT, resolution_id=ids[-1])
        )

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == ""
    assert (await core.get_case(f"case-{SNAPSHOT}")).data["state"] == "pending"


async def test_resolving_fails_for_an_unknown_snapshot(core, capsys):
    await _seed_incident(core)

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_resolve_cases_for_snapshot(
            _args(snapshot_id="csn-nowhere", resolution_id="vrd-x")
        )

    assert exc_info.value.code == 1


# --- the retrospective -------------------------------------------------------


def _wait_args(ids, **overrides) -> argparse.Namespace:
    defaults = dict(snapshot_id=SNAPSHOT, closed_by="quiet", must_include=[ids[0], ids[-1]],
                    timeout=0.3, interval=0.05)
    return _args(**{**defaults, **overrides})


async def test_a_quiet_retrospective_with_responds_verdicts_passes(core, capsys):
    ids = await _seed_incident(core)
    await _retrospective(core, timeline_ids=[BREACH, *ids])

    await tta.cmd_wait_retrospective(_wait_args(ids))

    assert _kv(capsys) == {
        "RETRO_ID": f"retro-{SNAPSHOT}",
        "RETRO_CLOSED_BY": "quiet",
        "RETRO_VERDICT_COUNT": "4",
        "RETRO_RESPOND_VERDICTS": "3",
    }


async def test_wait_retrospective_waits_for_one_written_after_it_starts(core, capsys):
    """As in the harness: learn writes it a cycle or two after the case is
    resolved, not before the wait begins."""
    ids = await _seed_incident(core)

    async def learn_writes_it_later() -> None:
        await asyncio.sleep(0.2)
        await _retrospective(core, timeline_ids=[BREACH, *ids])

    writer = asyncio.create_task(learn_writes_it_later())
    await tta.cmd_wait_retrospective(_wait_args(ids, timeout=5.0, interval=0.05))
    await writer

    assert _kv(capsys)["RETRO_ID"] == f"retro-{SNAPSHOT}"


async def test_a_retrospective_closed_by_max_age_fails(core, capsys):
    ids = await _seed_incident(core)
    await _retrospective(core, closed_by="max_age", timeline_ids=[BREACH, *ids])

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_wait_retrospective(_wait_args(ids))

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("dropped", [0, 1, 2])
async def test_a_timeline_missing_one_of_responds_verdicts_fails(core, capsys, dropped):
    """The retrospective as it was before opensrm-91pa held the trigger and
    none of respond's verdicts; one missing is enough to fail."""
    ids = await _seed_incident(core)
    kept = [vid for n, vid in enumerate(ids) if n != dropped]
    await _retrospective(core, timeline_ids=[BREACH, *kept])

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_wait_retrospective(_wait_args(ids, must_include=[]))

    assert exc_info.value.code == 1


async def test_a_must_include_id_outside_the_timeline_fails(core, capsys):
    ids = await _seed_incident(core)
    await _retrospective(core, timeline_ids=ids)

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_wait_retrospective(_wait_args(ids, must_include=[BREACH]))

    assert exc_info.value.code == 1


async def test_a_retrospective_for_an_incident_respond_never_touched_fails(core, capsys):
    """Nothing descends from the snapshot: there is nothing of respond's to
    find, so the assertion would otherwise pass on an empty set."""
    await _seed_incident(core, steps=(), case=False)
    await _retrospective(core, timeline_ids=[BREACH])

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_wait_retrospective(_wait_args([BREACH], must_include=[]))

    assert exc_info.value.code == 1


async def test_no_retrospective_within_the_timeout_fails(core, capsys):
    ids = await _seed_incident(core)

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_wait_retrospective(_wait_args(ids))

    assert exc_info.value.code == 1


async def test_two_retrospectives_for_one_snapshot_fail(core, capsys):
    ids = await _seed_incident(core)
    await _retrospective(core, timeline_ids=ids)
    await _retrospective(core, timeline_ids=ids, retro_id="retro-fraud-detect-0a1b2c3d")

    with pytest.raises(SystemExit) as exc_info:
        await tta.cmd_wait_retrospective(_wait_args(ids))

    assert exc_info.value.code == 1


def test_the_new_commands_are_wired_into_main(core, capsys):
    """Through ``main``, as the harness calls them."""
    async def seed() -> list[str]:
        ids = await _seed_incident(core)
        await _retrospective(core, timeline_ids=ids)
        await core.close()
        return ids

    ids = asyncio.run(seed())

    for argv in (
        ["snapshot-of-verdict", ids[-1]],
        ["resolve-cases-for-snapshot", "--snapshot-id", SNAPSHOT, "--resolution-id", ids[-1]],
        ["wait-retrospective", "--snapshot-id", SNAPSHOT, "--closed-by", "quiet",
         "--must-include", ids[0], ids[-1], "--timeout", "1", "--interval", "0.05"],
        ["assert-no-retrospective", "--snapshot-id", "csn-other"],
    ):
        assert tta.main([*argv, "--core-url", CORE_URL]) == 0

    printed = _kv(capsys)
    assert printed["RETRO_CLOSED_BY"] == "quiet"
    assert printed["CASES_RESOLVED"] == "1"
    assert printed["NO_RETROSPECTIVE_OK"] == "true"
