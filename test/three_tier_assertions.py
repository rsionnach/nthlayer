"""Three-tier integration test assertion helpers.

Used by ``test/integration-three-tier.sh``, ``test/e2e-test.sh`` and
``test/integration-thresholds.sh`` (the ``*-threshold-*`` and
``assert-no-verdict`` subcommands, opensrm-x0r9). Each subcommand performs one
poll, fetch, or assertion against a running nthlayer-core HTTP API. Output
is shell-parseable (``KEY=value`` lines on stdout) so the bash harness can
``eval`` it; errors exit non-zero with a message on stderr.

The bench-via-API path uses ``nthlayer_bench.sre.case_bench.fetch_case_bench``
directly. This proves bench's logic layer reads cases through the API; it
does NOT exercise the Textual widget rendering (covered by bench unit
tests).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import inspect
import sys
from typing import Any, NoReturn

from nthlayer_common.api_client import APIResult, CoreAPIClient

# --- helpers ----------------------------------------------------------------

def _now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _parse_iso(ts: str) -> dt.datetime:
    """Parse an ISO 8601 timestamp; tolerate trailing 'Z'."""
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


async def _poll(
    client: CoreAPIClient,
    *,
    description: str,
    fetch,
    predicate,
    timeout_seconds: float,
    interval_seconds: float,
):
    """Poll ``fetch`` until ``predicate(result)`` is truthy or timeout.

    Returns the predicate's truthy result, or raises TimeoutError. ``fetch``
    is an async callable taking the client; ``predicate`` takes the
    APIResult-derived value and returns either falsy or the value to return.
    """
    deadline = _now_utc() + dt.timedelta(seconds=timeout_seconds)
    last_status: Any = None
    attempts = 0
    while _now_utc() < deadline:
        attempts += 1
        result = await fetch(client)
        last_status = getattr(result, "status_code", None)
        if getattr(result, "ok", False):
            hit = predicate(result)
            if hit:
                return hit
        await asyncio.sleep(interval_seconds)
    raise TimeoutError(
        f"{description}: timed out after {timeout_seconds:.0f}s "
        f"({attempts} attempts; last status={last_status})"
    )


def _print_kv(**pairs: Any) -> None:
    """Print KEY=value lines suitable for ``eval`` or ``source`` in bash."""
    for key, value in pairs.items():
        print(f"{key}={value}")


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(1)


# --- commands ---------------------------------------------------------------

async def cmd_wait_heartbeat(args: argparse.Namespace) -> None:
    """Poll /heartbeats until at least one entry exists for the named component."""
    async with CoreAPIClient(base_url=args.core_url) as client:
        async def fetch(c):
            return await c.get_heartbeats()

        def predicate(result: APIResult):
            rows = result.data or []
            for row in rows:
                if args.component is None or row.get("component") == args.component:
                    return row
            return None

        row = await _poll(
            client,
            description=f"heartbeat for component={args.component or '*'}",
            fetch=fetch,
            predicate=predicate,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        )
    _print_kv(
        HEARTBEAT_COMPONENT=row.get("component", ""),
        HEARTBEAT_HEALTH=row.get("health", ""),
    )


async def cmd_wait_verdict_type(args: argparse.Namespace) -> None:
    """Poll /verdicts?type=X until at least one verdict matches."""
    async with CoreAPIClient(base_url=args.core_url) as client:
        async def fetch(c):
            return await c.get_verdicts(verdict_type=args.verdict_type, service=args.service, limit=50)

        def predicate(result: APIResult):
            rows = result.data or []
            return rows[0] if rows else None

        verdict = await _poll(
            client,
            description=f"verdict type={args.verdict_type} service={args.service or '*'}",
            fetch=fetch,
            predicate=predicate,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        )
    _print_kv(
        VERDICT_ID=verdict.get("id", ""),
        VERDICT_CREATED_AT=verdict.get("created_at", ""),
        VERDICT_SERVICE=verdict.get("service", "") or "",
    )


async def cmd_wait_assessment_kind(args: argparse.Namespace) -> None:
    async with CoreAPIClient(base_url=args.core_url) as client:
        async def fetch(c):
            return await c.get_assessments(kind=args.kind, service=args.service, limit=50)

        def predicate(result: APIResult):
            rows = result.data or []
            return rows[0] if rows else None

        assessment = await _poll(
            client,
            description=f"assessment kind={args.kind} service={args.service or '*'}",
            fetch=fetch,
            predicate=predicate,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        )
    _print_kv(
        ASSESSMENT_ID=assessment.get("id", ""),
        ASSESSMENT_CREATED_AT=assessment.get("created_at", ""),
        ASSESSMENT_SERVICE=assessment.get("service", "") or "",
    )


async def cmd_wait_case(args: argparse.Namespace) -> None:
    async with CoreAPIClient(base_url=args.core_url) as client:
        async def fetch(c):
            return await c.get_cases(service=args.service, limit=50)

        def predicate(result: APIResult):
            rows = result.data or []
            return rows[0] if rows else None

        case = await _poll(
            client,
            description=f"case service={args.service or '*'}",
            fetch=fetch,
            predicate=predicate,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        )
    _print_kv(
        CASE_ID=case.get("id", ""),
        CASE_PRIORITY=case.get("priority", ""),
        CASE_CREATED_AT=case.get("created_at", ""),
        CASE_UNDERLYING_VERDICT=case.get("underlying_verdict", ""),
    )


def _close(a: Any, b: float) -> bool:
    """A JSON number equal to *b* (to 1e-9); bools are not numbers here."""
    return isinstance(a, (int, float)) and not isinstance(a, bool) and abs(a - b) <= 1e-9


def _threshold_row(assessment: dict, args: argparse.Namespace) -> dict | None:
    """The outcome row for args.bound in a judgment_threshold_evaluation of
    args.threshold_type, when its status (and measured value, if given)
    match; else None. Shape: workers' measure/thresholds/phase.py, data =
    {"threshold_key", "outcome": ThresholdOutcome.to_dict()}."""
    data = assessment.get("data") or {}
    outcome = data.get("outcome") if isinstance(data, dict) else None
    if not isinstance(outcome, dict) or outcome.get("type") != args.threshold_type:
        return None
    for row in outcome.get("bounds") or []:
        if not isinstance(row, dict) or row.get("bound") != args.bound:
            continue
        if row.get("status") != args.status:
            continue
        if args.measured is not None and not _close(row.get("measured"), args.measured):
            continue
        return row
    return None


async def cmd_wait_threshold_evaluation(args: argparse.Namespace) -> None:
    """Poll until a judgment_threshold_evaluation for --service reports
    --bound with --status (and --measured, if given)."""
    async with CoreAPIClient(base_url=args.core_url) as client:
        async def fetch(c):
            return await c.get_assessments(
                kind="judgment_threshold_evaluation", service=args.service, limit=100,
            )

        def predicate(result: APIResult):
            for a in result.data or []:
                row = _threshold_row(a, args)
                if row is not None:
                    return a, row
            return None

        assessment, row = await _poll(
            client,
            description=(f"judgment_threshold_evaluation service={args.service} "
                         f"bound={args.bound} status={args.status} measured={args.measured}"),
            fetch=fetch,
            predicate=predicate,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        )
    _print_kv(
        THRESHOLD_ASSESSMENT_ID=assessment.get("id", ""),
        THRESHOLD_KEY=(assessment.get("data") or {}).get("threshold_key", ""),
        THRESHOLD_OVERALL_STATUS=(assessment.get("data") or {}).get("outcome", {}).get("status", ""),
        THRESHOLD_MEASURED=row.get("measured"),
        THRESHOLD_LIMIT=row.get("limit"),
    )


async def cmd_wait_threshold_breach(args: argparse.Namespace) -> None:
    """Poll until a threshold quality_breach for --service names --bound with
    --measured, at --severity; then check its parent is a breaching
    judgment_threshold_evaluation of the same threshold_key.

    Only a threshold breach matches (data.threshold_type is set): an SLO
    quality_breach of the same service carries slo_name instead."""
    async with CoreAPIClient(base_url=args.core_url) as client:
        async def fetch(c):
            return await c.get_verdicts(
                verdict_type="quality_breach", service=args.service, limit=100,
            )

        def predicate(result: APIResult):
            for v in result.data or []:
                data = v.get("data") or {}
                if not isinstance(data, dict) or data.get("threshold_type") != args.threshold_type:
                    continue
                for row in data.get("breaching_bounds") or []:
                    if (isinstance(row, dict) and row.get("bound") == args.bound
                            and _close(row.get("measured"), args.measured)):
                        return v, row
            return None

        verdict, row = await _poll(
            client,
            description=(f"threshold quality_breach service={args.service} "
                         f"bound={args.bound} measured={args.measured}"),
            fetch=fetch,
            predicate=predicate,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        )
        data = verdict["data"]
        if data.get("severity") != args.severity:
            _fail(f"threshold quality_breach {verdict.get('id')!r}: severity "
                  f"{data.get('severity')!r}, expected {args.severity!r}")
        names = sorted(r.get("bound") for r in data.get("breaching_bounds") or []
                       if isinstance(r, dict))
        if names != sorted(args.expect_breaching):
            _fail(f"threshold quality_breach {verdict.get('id')!r}: breaching_bounds "
                  f"{names!r}, expected {sorted(args.expect_breaching)!r}")
        if args.bound not in str(data.get("summary", "")):
            _fail(f"threshold quality_breach {verdict.get('id')!r}: summary "
                  f"{data.get('summary')!r} does not name {args.bound!r}")
        parents = verdict.get("parent_ids") or []
        assessments = await client.get_assessments(
            kind="judgment_threshold_evaluation", service=args.service, limit=100,
        )
        if not assessments.ok:
            _fail(f"GET /assessments failed: status={assessments.status_code}")
        status_args = argparse.Namespace(**{**vars(args), "status": "breach"})
        parent = next((a for a in assessments.data or []
                       if a.get("id") in parents and _threshold_row(a, status_args)), None)
        if parent is None:
            _fail(f"threshold quality_breach {verdict.get('id')!r}: parent_ids {parents!r} "
                  f"name no breaching judgment_threshold_evaluation of {args.service!r}")
        if (parent.get("data") or {}).get("threshold_key") != data.get("threshold_key"):
            _fail(f"threshold quality_breach {verdict.get('id')!r}: threshold_key "
                  f"{data.get('threshold_key')!r} differs from its parent's")
    _print_kv(
        THRESHOLD_BREACH_ID=verdict.get("id", ""),
        THRESHOLD_BREACH_SEVERITY=data.get("severity"),
        THRESHOLD_BREACH_PARENT=parent.get("id", ""),
        THRESHOLD_BREACH_LIMIT=row.get("limit"),
    )


async def cmd_assert_no_verdict(args: argparse.Namespace) -> None:
    """Fail if core holds any verdict of --type for --service (one fetch)."""
    async with CoreAPIClient(base_url=args.core_url) as client:
        result = await client.get_verdicts(
            verdict_type=args.verdict_type, service=args.service, limit=100,
        )
    if not result.ok:
        _fail(f"GET /verdicts failed: status={result.status_code} error={result.error!r}")
    if result.data:
        _fail(f"expected no {args.verdict_type} verdict for {args.service!r}, got "
              f"{[v.get('id') for v in result.data]!r}")
    _print_kv(NO_VERDICT_OK="true")


async def cmd_assert_lineage(args: argparse.Namespace) -> None:
    """Assert that ``parent_id`` appears in ``child_id``'s ancestry chain.

    Strong form of the lineage check: walks GET /verdicts/{child}/ancestors
    and asserts ``parent_id`` is in the returned list. This catches the
    regression class where lineage has the right verdict types but wrong IDs.
    """
    async with CoreAPIClient(base_url=args.core_url) as client:
        result = await client.get_ancestors(args.child_id, max_hops=args.max_hops)
        if not result.ok:
            _fail(
                f"GET /verdicts/{args.child_id}/ancestors failed: "
                f"status={result.status_code} error={result.error!r}"
            )
        ancestors = result.data or []
        ancestor_ids = {a.get("id") for a in ancestors}
        if args.parent_id not in ancestor_ids:
            _fail(
                f"Lineage assertion failed: {args.parent_id!r} not found in "
                f"ancestors of {args.child_id!r}. Got {sorted(ancestor_ids)!r}"
            )
    _print_kv(LINEAGE_OK="true", ANCESTOR_COUNT=str(len(ancestors)))


async def cmd_fetch_case_via_bench(args: argparse.Namespace) -> None:
    """Call ``nthlayer_bench.sre.case_bench.fetch_case_bench`` and assert ≥1 case.

    This proves that bench's logic layer reads through the core API (not via
    direct DB access). The widget rendering layer is unit-tested separately
    in ``nthlayer-bench/tests/`` and is intentionally out of scope here.
    """
    from nthlayer_bench.sre.case_bench import fetch_case_bench

    async with CoreAPIClient(base_url=args.core_url) as client:
        view = await fetch_case_bench(client, state=args.state, limit=args.limit)
    if not view.flat:
        _fail(
            f"bench fetch_case_bench returned no cases (state={args.state!r}). "
            f"This proves bench's read path is connecting to core but the case "
            f"queue is empty — likely a respond/case-creation regression."
        )
    first = view.flat[0]
    _print_kv(
        BENCH_CASE_COUNT=str(len(view.flat)),
        BENCH_CASE_ID=first.case_id,
        BENCH_CASE_PRIORITY=first.priority,
    )


async def cmd_render_portfolio(args: argparse.Namespace) -> None:
    """Render the canonical portfolio table for demo Step 1 / Step 8.

    Joins the most-recent portfolio_status assessment (per-service overall
    status + slo_count) with recent slo_status assessments (per-SLO
    percent_consumed). The per-service "budget remaining" cell is computed
    as ``100 - max(percent_consumed across that service's SLOs)`` — the
    worst-SLO view, which matches how operators read the table during an
    incident (one breached SLO defines the budget you have left).

    Pattern (b) per opensrm-42y.16 audit: poll worker-emitted assessments
    rather than invoking observe CLI on demand. The renderer is read-only
    against core's HTTP API.
    """
    try:
        async with CoreAPIClient(base_url=args.core_url) as client:
            port_result = await client.get_assessments(
                kind="portfolio_status", limit=1,
            )
            if not port_result.ok:
                print(
                    f"  (portfolio_status fetch failed: {port_result.error})",
                    file=sys.stderr,
                )
                return
            if not port_result.data:
                print("  (no portfolio_status assessment available yet)")
                return
            portfolio = port_result.data[0]
            data = portfolio.get("data", {}) or {}
            services = data.get("services", []) or []

            # Per-service slo_status fetches. Avoids the truncation risk of
            # a single bulk limit=N query when one noisy service's SLOs
            # could evict another service's latest reading past the page
            # boundary. For demo-scale portfolios (≤ tens of services), the
            # extra HTTP calls cost milliseconds.
            per_svc_worst: dict[str, float] = {}
            for s in services:
                svc = s.get("service") or ""
                if not svc:
                    continue
                slo_result = await client.get_assessments(
                    service=svc, kind="slo_status", limit=50,
                )
                if not slo_result.ok:
                    # Partial failure: surface to stderr so the empty row
                    # is distinguishable from "no slo_status yet." The
                    # render itself continues — one bad service does not
                    # collapse the whole table.
                    print(
                        f"  (slo_status fetch failed for {svc}: {slo_result.error})",
                        file=sys.stderr,
                    )
                    continue
                # Assessments are ordered created_at DESC, so the first
                # occurrence of each slo_name in the response is its latest.
                seen: set[str] = set()
                for a in (slo_result.data or []):
                    d = a.get("data", {}) or {}
                    slo_name = d.get("slo_name", "?")
                    if slo_name in seen:
                        continue
                    seen.add(slo_name)
                    pc = d.get("percent_consumed")
                    # Type-guard before max(): a malformed worker emit
                    # (string "n/a", bool, etc.) would otherwise TypeError
                    # mid-loop and collapse the whole render.
                    if not isinstance(pc, (int, float)) or isinstance(pc, bool):
                        continue
                    current = per_svc_worst.get(svc)
                    per_svc_worst[svc] = pc if current is None else max(current, pc)

            for s in sorted(services, key=lambda x: x.get("service", "")):
                svc = s.get("service", "?")
                status = s.get("overall_status", "?")
                slos = s.get("slo_count", 0)
                pc = per_svc_worst.get(svc)
                if pc is None:
                    budget_cell = "budget=  N/A"
                else:
                    remaining = max(0.0, 100.0 - pc)
                    budget_cell = f"budget={remaining:>5.1f}%"
                slo_label = "SLO" if slos == 1 else "SLOs"
                print(f"  {svc:<16} {status:<10}  {budget_cell}  ({slos} {slo_label})")

            print(
                f"  total: {data.get('total_services', 0)} services "
                f"({data.get('healthy_count', 0)} healthy / "
                f"{data.get('warning_count', 0)} warning / "
                f"{data.get('critical_count', 0)} critical / "
                f"{data.get('exhausted_count', 0)} exhausted)"
            )
    except Exception as exc:
        # Demo helper: a connection error or unexpected payload must
        # not bubble a Python traceback into the demo terminal. Single
        # diagnostic line on stderr; exit 0 so the scenario continues.
        print(
            f"  (portfolio render failed: {exc.__class__.__name__}: {exc})",
            file=sys.stderr,
        )


def cmd_assert_latency(args: argparse.Namespace) -> None:
    """Assert (end - start) ≤ ``max_seconds``.

    The integration test defines end-to-end pipeline latency as
    ``case.created_at - quality_breach.created_at``. That spans
    measure → correlate → respond → case creation, the path the bead's
    "<30s p99" budget targets.
    """
    start = _parse_iso(args.start)
    end = _parse_iso(args.end)
    delta = (end - start).total_seconds()
    if delta < 0:
        _fail(f"Latency assertion failed: end ({args.end}) precedes start ({args.start})")
    if delta > args.max_seconds:
        _fail(
            f"Latency assertion failed: {delta:.1f}s > {args.max_seconds:.1f}s "
            f"(start={args.start} end={args.end})"
        )
    _print_kv(LATENCY_SECONDS=f"{delta:.1f}", LATENCY_OK="true")


# --- argparse wiring --------------------------------------------------------

def _add_common(parser: argparse.ArgumentParser, *, with_poll: bool = True) -> None:
    parser.add_argument("--core-url", default="http://localhost:8000")
    if with_poll:
        parser.add_argument("--timeout", type=float, default=30.0,
                            help="poll timeout in seconds")
        parser.add_argument("--interval", type=float, default=1.0,
                            help="poll interval in seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="three_tier_assertions")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("wait-heartbeat")
    _add_common(p)
    p.add_argument("--component", default=None,
                   help="filter by component name (e.g. observe.collect, measure)")

    p = sub.add_parser("wait-verdict-type")
    _add_common(p)
    p.add_argument("verdict_type")
    p.add_argument("--service", default=None)

    p = sub.add_parser("wait-assessment-kind")
    _add_common(p)
    p.add_argument("kind")
    p.add_argument("--service", default=None)

    p = sub.add_parser("wait-case")
    _add_common(p)
    p.add_argument("--service", default=None)

    p = sub.add_parser("wait-threshold-evaluation")
    _add_common(p)
    p.add_argument("--service", required=True)
    p.add_argument("--threshold-type", default="calibration")
    p.add_argument("--bound", required=True)
    p.add_argument("--status", required=True, choices=["within", "breach", "not_evaluable"])
    p.add_argument("--measured", type=float, default=None)

    p = sub.add_parser("wait-threshold-breach")
    _add_common(p)
    p.add_argument("--service", required=True)
    p.add_argument("--threshold-type", default="calibration")
    p.add_argument("--bound", required=True)
    p.add_argument("--measured", type=float, required=True)
    p.add_argument("--severity", default="high")
    p.add_argument("--expect-breaching", nargs="+", required=True,
                   help="every bound the breach's breaching_bounds must name, no more")

    p = sub.add_parser("assert-no-verdict")
    _add_common(p, with_poll=False)
    p.add_argument("verdict_type")
    p.add_argument("--service", required=True)

    p = sub.add_parser("assert-lineage")
    _add_common(p, with_poll=False)
    p.add_argument("child_id")
    p.add_argument("parent_id")
    p.add_argument("--max-hops", type=int, default=None)

    p = sub.add_parser("fetch-case-via-bench")
    _add_common(p, with_poll=False)
    # Default state matches fetch_case_bench's own default — newly-emitted
    # cases land in "pending" before any operator picks them up.
    p.add_argument("--state", default="pending")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("render-portfolio")
    _add_common(p, with_poll=False)

    p = sub.add_parser("assert-latency")
    p.add_argument("start", help="ISO 8601 timestamp")
    p.add_argument("end", help="ISO 8601 timestamp")
    p.add_argument("max_seconds", type=float)

    args = parser.parse_args(argv)

    handler = {
        "wait-heartbeat": cmd_wait_heartbeat,
        "wait-verdict-type": cmd_wait_verdict_type,
        "wait-assessment-kind": cmd_wait_assessment_kind,
        "wait-case": cmd_wait_case,
        "wait-threshold-evaluation": cmd_wait_threshold_evaluation,
        "wait-threshold-breach": cmd_wait_threshold_breach,
        "assert-no-verdict": cmd_assert_no_verdict,
        "assert-lineage": cmd_assert_lineage,
        "fetch-case-via-bench": cmd_fetch_case_via_bench,
        "render-portfolio": cmd_render_portfolio,
        "assert-latency": cmd_assert_latency,
    }[args.cmd]

    try:
        if inspect.iscoroutinefunction(handler):
            asyncio.run(handler(args))
        else:
            handler(args)
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
