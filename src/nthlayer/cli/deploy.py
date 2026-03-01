"""
Deployment gate check command.

Queries Prometheus for SLO metrics, calculates error budget,
then evaluates deployment gate thresholds.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from nthlayer.cli.ux import console, error, header, info, success, warning
from nthlayer.drift import DriftAnalyzer, DriftResult, DriftSeverity, get_drift_defaults
from nthlayer.slos.collector import BudgetSummary, SLOMetricCollector, SLOResult
from nthlayer.slos.gates import DeploymentGate, GatePolicy, GateResult
from nthlayer.specs.parser import parse_service_file


def check_deploy_command(
    service_file: str,
    prometheus_url: str | None = None,
    environment: str | None = None,
    demo: bool = False,
    demo_blocked: bool = False,
    include_drift: bool = False,
    drift_window: str | None = None,
    include_correlation: bool = False,
) -> int:
    """
    Check if deployment should be allowed based on error budget.

    Exit codes: 0 = Approved, 1 = Warning, 2 = Blocked

    Args:
        include_drift: If True, also check for reliability drift trends
        drift_window: Override drift analysis window (e.g., "30d")
    """
    if demo:
        return _run_demo_mode(service_file, environment, blocked=False)
    if demo_blocked:
        return _run_demo_mode(service_file, environment, blocked=True)

    # Parse service file
    try:
        service_context, resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        return 2

    prom_url = prometheus_url or os.environ.get("PROMETHEUS_URL")
    slo_resources = [r for r in resources if r.kind == "SLO"]
    downstream_services = _extract_downstream_services(resources)

    # Display header
    _display_header(service_context, prom_url, environment)

    # Validate SLOs exist
    if not slo_resources:
        _display_no_slos_warning()
        return 0

    # Show examples if no Prometheus
    if not prom_url:
        _display_no_prometheus_info(service_context, slo_resources, downstream_services)
        return 0

    # Collect metrics from Prometheus
    console.print("[bold]Querying Prometheus for SLO metrics...[/bold]")
    console.print()

    try:
        collector = SLOMetricCollector(prom_url)
        slo_results = asyncio.run(collector.collect(slo_resources, service_context.name))
        budget = collector.calculate_aggregate_budget(slo_results)
    except Exception as e:
        error(f"Failed to query Prometheus: {e}")
        console.print(f"[muted]Check Prometheus is reachable at: {prom_url}[/muted]")
        return 2

    # Display results and run gate
    _display_slo_table(slo_results)

    if budget.valid_slo_count == 0:
        warning("No SLO data available from Prometheus")
        console.print("[muted]Ensure metrics are being collected[/muted]")
        return 0

    _display_budget_summary(budget)

    # Extract gate policy from service resources
    gate_resources = [r for r in resources if r.kind == "DeploymentGate"]
    policy = GatePolicy.from_spec(gate_resources[0].spec) if gate_resources else None

    env = environment or "prod"

    # Run correlation check if requested
    correlation_results = None
    db_url = os.environ.get("NTHLAYER_DATABASE_URL")
    if include_correlation and db_url:
        correlation_results = _run_correlation_check(
            db_url=db_url,
            service_name=service_context.name,
        )

    # Wire audit recorder when database is configured
    if db_url:
        result = _run_gate_with_audit(
            policy=policy,
            db_url=db_url,
            service=service_context.name,
            tier=service_context.tier,
            budget_total_minutes=int(budget.total_budget_minutes),
            budget_consumed_minutes=int(budget.burned_budget_minutes),
            downstream_services=downstream_services,
            environment=env,
            team=service_context.team,
            correlation_results=correlation_results,
        )
    else:
        gate = DeploymentGate(policy=policy)
        result = gate.check_deployment(
            service=service_context.name,
            tier=service_context.tier,
            budget_total_minutes=int(budget.total_budget_minutes),
            budget_consumed_minutes=int(budget.burned_budget_minutes),
            downstream_services=downstream_services,
            environment=env,
            team=service_context.team,
        )

    # Check drift if requested and not already blocked
    drift_result = None
    if include_drift and result.result != GateResult.BLOCKED:
        drift_result = _check_drift(
            service_name=service_context.name,
            tier=service_context.tier,
            prometheus_url=prom_url,
            window=drift_window,
        )

    return _display_gate_result(
        result,
        service_context.tier,
        budget.remaining_percent,
        drift_result,
        correlation_results=correlation_results,
    )


def _extract_downstream_services(resources: list[Any]) -> list[dict[str, Any]]:
    """Extract downstream services from Dependencies resource."""
    dep_resources = [r for r in resources if r.kind == "Dependencies"]
    downstream_services = []

    if dep_resources:
        deps_spec = dep_resources[0].spec
        for svc in deps_spec.get("services", []):
            downstream_services.append(
                {
                    "name": svc["name"],
                    "criticality": svc.get("criticality", "medium"),
                }
            )

    return downstream_services


def _run_gate_with_audit(
    policy: GatePolicy | None,
    db_url: str,
    service: str,
    tier: str,
    budget_total_minutes: int,
    budget_consumed_minutes: int,
    downstream_services: list[dict[str, Any]],
    environment: str,
    team: str | None,
    correlation_results: list[Any] | None = None,
) -> Any:
    """Run gate check with audit recording and override checking.

    Creates async DB session, audit recorder, and calls
    check_deployment_with_audit(). Fail-open: falls back to sync
    check_deployment() if DB setup fails.
    """
    import structlog

    logger = structlog.get_logger()

    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from nthlayer.policies.recorder import PolicyAuditRecorder
        from nthlayer.policies.repository import PolicyAuditRepository

        async def _run() -> Any:
            engine = create_async_engine(db_url)
            async with AsyncSession(engine) as session:
                repo = PolicyAuditRepository(session)
                recorder = PolicyAuditRecorder(repo)
                gate = DeploymentGate(
                    policy=policy,
                    audit_recorder=recorder,
                    override_repository=repo,
                )
                result = await gate.check_deployment_with_audit(
                    service=service,
                    tier=tier,
                    budget_total_minutes=budget_total_minutes,
                    budget_consumed_minutes=budget_consumed_minutes,
                    downstream_services=downstream_services,
                    environment=environment,
                    team=team,
                    correlation_results=correlation_results,
                )
                await session.commit()
                return result

        return asyncio.run(_run())
    except Exception:
        logger.warning("audit_setup_failed", exc_info=True)
        # Fail open: fall back to sync gate without audit
        gate = DeploymentGate(policy=policy)
        return gate.check_deployment(
            service=service,
            tier=tier,
            budget_total_minutes=budget_total_minutes,
            budget_consumed_minutes=budget_consumed_minutes,
            downstream_services=downstream_services,
            environment=environment,
            team=team,
        )


def _run_correlation_check(
    db_url: str,
    service_name: str,
) -> list[Any]:
    """Run correlation check against recent deployments.

    Fail-open: returns empty list on any failure.

    Args:
        db_url: Database URL for SLO repository
        service_name: Service to check

    Returns:
        List of CorrelationResult, or empty on failure
    """
    import structlog as _structlog

    _logger = _structlog.get_logger()

    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from nthlayer.slos.correlator import DeploymentCorrelator
        from nthlayer.slos.storage import SLORepository

        async def _run() -> list[Any]:
            engine = create_async_engine(db_url)
            async with AsyncSession(engine) as session:
                repo = SLORepository(session)
                correlator = DeploymentCorrelator(repo)
                return await correlator.correlate_service(service_name)

        return asyncio.run(_run())
    except Exception:
        _logger.warning("correlation_check_failed", service=service_name, exc_info=True)
        return []


def _display_header(service_context: Any, prom_url: str | None, environment: str | None) -> None:
    """Display command header with service info."""
    header(f"Deployment Gate Check: {service_context.name}")
    console.print()

    if prom_url:
        console.print(f"[cyan]Prometheus:[/cyan] {prom_url}")
    console.print(f"[cyan]Service:[/cyan] {service_context.name}")
    console.print(f"[cyan]Team:[/cyan] {service_context.team}")
    console.print(f"[cyan]Tier:[/cyan] {service_context.tier}")
    if environment:
        console.print(f"[cyan]Environment:[/cyan] {environment}")
    console.print()


def _display_no_slos_warning() -> None:
    """Display warning when no SLOs are defined."""
    warning("No SLOs defined in service.yaml")
    console.print("[muted]Cannot check error budget without SLO definitions[/muted]")
    console.print()
    console.print("[muted]Add SLOs to enable deployment gating:[/muted]")
    console.print("  resources:")
    console.print("    - kind: SLO")
    console.print("      name: availability")
    console.print("      spec:")
    console.print("        objective: 99.95")
    console.print("        window: 30d")


def _display_no_prometheus_info(
    service_context: Any,
    slo_resources: list[Any],
    downstream_services: list[dict[str, Any]],
) -> None:
    """Display info when no Prometheus URL is provided."""
    info("No Prometheus URL provided")
    console.print("[muted]Provide via --prometheus-url or PROMETHEUS_URL env var[/muted]")
    console.print()
    _show_example_scenarios(service_context, slo_resources, downstream_services)


def _display_slo_table(results: list[SLOResult]) -> None:
    """Display SLO status as a table."""
    console.print("[bold]SLO Budget Status:[/bold]")

    status_icons = {
        "HEALTHY": "[success]✓[/success]",
        "WARNING": "[warning]⚠[/warning]",
        "CRITICAL": "[error]!![/error]",
        "EXHAUSTED": "[error]✗[/error]",
        "NO_DATA": "[muted]?[/muted]",
        "ERROR": "[error]E[/error]",
    }

    for result in results:
        icon = status_icons.get(result.status, "[muted]?[/muted]")

        if result.current_sli is not None:
            sli = f"{result.current_sli:.2f}%"
            budget_str = f"{result.percent_consumed:.0f}% burned"
        else:
            sli = "N/A"
            budget_str = result.error or "No data"

        console.print(
            f"  {icon} {result.name:<20} "
            f"[muted]target:[/muted] {result.objective}% "
            f"[muted]current:[/muted] {sli:<8} "
            f"[muted]budget:[/muted] {budget_str}"
        )

    console.print()


def _display_budget_summary(budget: BudgetSummary) -> None:
    """Display aggregate budget summary."""
    console.print(
        f"[bold]Aggregate Budget:[/bold] {budget.burned_budget_minutes:.1f}/"
        f"{budget.total_budget_minutes:.1f} minutes consumed ({budget.consumed_percent:.1f}%)"
    )
    console.print()


def _check_drift(
    service_name: str,
    tier: str,
    prometheus_url: str,
    window: str | None = None,
) -> DriftResult | None:
    """Check for reliability drift.

    Args:
        service_name: Name of the service
        tier: Service tier
        prometheus_url: Prometheus URL
        window: Override drift window

    Returns:
        DriftResult or None if drift check fails
    """
    drift_config = get_drift_defaults(tier)

    if not drift_config.get("enabled", True):
        return None

    username = os.environ.get("NTHLAYER_METRICS_USER")
    password = os.environ.get("NTHLAYER_METRICS_PASSWORD")

    analyzer = DriftAnalyzer(
        prometheus_url=prometheus_url,
        username=username,
        password=password,
    )

    try:
        result = asyncio.run(
            analyzer.analyze(
                service_name=service_name,
                tier=tier,
                slo="availability",
                window=window,
                drift_config=drift_config,
            )
        )
        return result
    except Exception as e:
        console.print(f"[muted]Drift check skipped: {e}[/muted]")
        return None


def _display_gate_result(
    result: Any,
    tier: str,
    remaining_pct: float,
    drift_result: DriftResult | None = None,
    correlation_results: list[Any] | None = None,
) -> int:
    """Display gate result and return exit code."""
    # Display thresholds
    console.print(f"[bold]Thresholds ({tier} tier):[/bold]")
    console.print(f"  [muted]Warning:[/muted] <{result.warning_threshold}% remaining")
    if result.blocking_threshold:
        console.print(f"  [muted]Blocking:[/muted] <{result.blocking_threshold}% remaining")
    else:
        console.print("  [muted]Blocking:[/muted] None (advisory only)")
    console.print()

    # Blast radius
    if result.high_criticality_downstream:
        console.print("[bold]Blast Radius:[/bold]")
        console.print(
            f"  [warning]⚡[/warning] {len(result.high_criticality_downstream)} "
            "high-criticality downstream service(s)"
        )
        for svc in result.high_criticality_downstream:
            console.print(f"    [muted]•[/muted] {svc}")
        console.print()

    # Display correlation analysis if available
    if correlation_results:
        from nthlayer.slos.correlator import HIGH_CONFIDENCE

        top_results = [r for r in correlation_results if r.confidence >= HIGH_CONFIDENCE]
        if top_results:
            top = max(top_results, key=lambda r: r.confidence)
            console.print("[bold]Correlation Analysis:[/bold]")
            console.print(
                f"  {top.confidence_emoji} Deploy {top.deployment_id}: "
                f"{top.confidence:.0%} confidence "
                f"[muted]({top.burn_minutes:.1f} min burned)[/muted]"
            )
            console.print()

    # Display drift analysis if available
    if drift_result is not None:
        _display_drift_summary(drift_result)

    # Check if drift should block deployment
    if drift_result is not None and drift_result.severity == DriftSeverity.CRITICAL:
        error("Deployment BLOCKED")
        console.print("[muted]Critical reliability drift detected[/muted]")
        console.print()
        console.print("[bold]Drift Details:[/bold]")
        console.print(f"  [muted]•[/muted] {drift_result.summary}")
        console.print(f"  [muted]•[/muted] {drift_result.recommendation}")
        console.print()
        return 2

    # Final verdict
    if result.result == GateResult.BLOCKED:
        error("Deployment BLOCKED")
        console.print(
            f"[muted]Error budget critically low ({remaining_pct:.1f}% remaining)[/muted]"
        )
        console.print()
        console.print("[bold]Recommendations:[/bold]")
        for rec in result.recommendations[:3]:
            console.print(f"  [muted]•[/muted] {rec}")
        console.print()
        return 2

    if result.result == GateResult.WARNING:
        warning("Deployment allowed with WARNING")
        console.print(f"[muted]Error budget low ({remaining_pct:.1f}% remaining)[/muted]")
        # Add drift warning if applicable
        if drift_result is not None and drift_result.severity == DriftSeverity.WARN:
            console.print(f"[muted]Drift warning: {drift_result.summary}[/muted]")
        console.print()
        console.print("[bold]Recommendations:[/bold]")
        for rec in result.recommendations[:3]:
            console.print(f"  [muted]•[/muted] {rec}")
        console.print()
        return 1

    # Check for drift warning even if budget is OK
    if drift_result is not None and drift_result.severity == DriftSeverity.WARN:
        warning("Deployment allowed with WARNING")
        console.print(f"[muted]Error budget healthy ({remaining_pct:.1f}% remaining)[/muted]")
        console.print(f"[muted]Drift warning: {drift_result.summary}[/muted]")
        console.print()
        return 1

    success("Deployment APPROVED")
    console.print(f"[muted]Error budget healthy ({remaining_pct:.1f}% remaining)[/muted]")
    if drift_result is not None:
        console.print(f"[muted]Drift: {drift_result.pattern.value.replace('_', ' ')}[/muted]")
    console.print()
    return 0


def _display_drift_summary(drift_result: DriftResult) -> None:
    """Display drift analysis summary."""
    severity_icons = {
        DriftSeverity.NONE: "[success]✓[/success]",
        DriftSeverity.INFO: "[blue]ℹ[/blue]",
        DriftSeverity.WARN: "[warning]⚠[/warning]",
        DriftSeverity.CRITICAL: "[error]✗[/error]",
    }

    console.print("[bold]Drift Analysis:[/bold]")
    icon = severity_icons.get(drift_result.severity, "[muted]?[/muted]")
    trend_str = f"{drift_result.metrics.slope_per_week * 100:+.2f}%/week"

    console.print(
        f"  {icon} Trend: {trend_str} "
        f"[muted]| Pattern:[/muted] {drift_result.pattern.value.replace('_', ' ')} "
        f"[muted]| Confidence:[/muted] {drift_result.metrics.r_squared:.0%}"
    )

    if drift_result.projection.days_until_exhaustion is not None:
        days = drift_result.projection.days_until_exhaustion
        color = "red" if days < 14 else "yellow" if days < 30 else "muted"
        console.print(f"  [muted]Projected exhaustion:[/muted] [{color}]{days} days[/]")

    console.print()


def _show_example_scenarios(
    service_context: Any,
    slo_resources: list[Any],
    downstream_services: list[dict[str, Any]],
) -> None:
    """Show example scenarios when no Prometheus URL provided."""
    console.print(f"[bold]Example scenarios for {service_context.tier} tier:[/bold]")
    console.print()

    gate = DeploymentGate()  # Demo mode uses default thresholds

    # Calculate example budget from first SLO
    collector = SLOMetricCollector()
    if slo_resources:
        spec = slo_resources[0].spec or {}
        window = spec.get("window", "30d")
        objective = spec.get("objective", 99.9)
        window_minutes = collector._parse_window_minutes(window)
        total_budget = window_minutes * ((100 - objective) / 100)
    else:
        total_budget = 43.2  # Default: 30 days at 99.9%

    scenarios = [
        ("Healthy (5% consumed)", int(total_budget * 0.05)),
        ("Warning (85% consumed)", int(total_budget * 0.85)),
        ("Blocked (95% consumed)", int(total_budget * 0.95)),
    ]

    for scenario_name, consumed in scenarios:
        result = gate.check_deployment(
            service_context.name,
            service_context.tier,
            int(total_budget),
            consumed,
            downstream_services,
        )

        status_icon = {
            GateResult.APPROVED: "[success]✓[/success]",
            GateResult.WARNING: "[warning]⚠[/warning]",
            GateResult.BLOCKED: "[error]✗[/error]",
        }[result.result]

        console.print(f"  {status_icon} {scenario_name} → Exit code: {result.result}")

    console.print()
    console.print("[muted]To check with real data:[/muted]")
    console.print(
        f"  [cyan]nthlayer deploy check {Path(service_context.name).name}.yaml "
        "--prometheus-url http://prometheus:9090[/cyan]"
    )
    console.print()


def _run_demo_mode(service_file: str, environment: str | None = None, blocked: bool = False) -> int:
    """Run demo mode with sample data for VHS recordings.

    Args:
        service_file: Path to service YAML file
        environment: Optional environment name
        blocked: If True, show BLOCKED scenario; if False, show WARNING scenario
    """
    from nthlayer.specs.parser import parse_service_file

    # Parse service file to get real names
    try:
        service_context, resources = parse_service_file(service_file, environment=environment)
        service_name = service_context.name
        tier = service_context.tier
        team = service_context.team
    except Exception:
        service_name = "payment-api"
        tier = "critical"
        team = "payments"

    # Print header
    header(f"Deployment Gate Check: {service_name}")
    console.print()

    console.print("[cyan]Prometheus:[/cyan] https://prometheus.internal:9090")
    console.print(f"[cyan]Service:[/cyan] {service_name}")
    console.print(f"[cyan]Team:[/cyan] {team}")
    console.print(f"[cyan]Tier:[/cyan] {tier}")
    console.print()

    console.print("[bold]Querying Prometheus for SLO metrics...[/bold]")
    console.print()

    if blocked:
        # Demo SLO data - shows a BLOCKED scenario (error budget exhausted)
        console.print("[bold]SLO Budget Status:[/bold]")
        console.print(
            "  [error]!![/error] availability          "
            "[muted]target:[/muted] 99.95% "
            "[muted]current:[/muted] 99.68%   "
            "[muted]budget:[/muted] 93% burned"
        )
        console.print(
            "  [warning]⚠[/warning] latency_p99           "
            "[muted]target:[/muted] 200ms  "
            "[muted]current:[/muted] 312ms    "
            "[muted]budget:[/muted] 78% burned"
        )
        console.print()

        console.print("[bold]Aggregate Budget:[/bold] 39.8/43.2 minutes consumed (92.1%)")
        console.print()

        console.print(f"[bold]Thresholds ({tier} tier):[/bold]")
        console.print("  [muted]Warning:[/muted] <50% remaining")
        console.print("  [muted]Blocking:[/muted] <10% remaining")
        console.print()

        # Show blocked result
        error("Deployment BLOCKED")
        console.print("[muted]Error budget critically low (7.9% remaining)[/muted]")
        console.print()

        console.print("[bold]Recommendations:[/bold]")
        console.print("  [muted]•[/muted] Investigate current reliability issues before deploying")
        console.print("  [muted]•[/muted] Consider rolling back recent changes")
        console.print("  [muted]•[/muted] Wait for error budget to recover (estimated: 4 hours)")
        console.print()
        return 2
    else:
        # Demo SLO data - shows a warning scenario
        console.print("[bold]SLO Budget Status:[/bold]")
        console.print(
            "  [warning]⚠[/warning] availability          "
            "[muted]target:[/muted] 99.95% "
            "[muted]current:[/muted] 99.87%   "
            "[muted]budget:[/muted] 58% burned"
        )
        console.print(
            "  [success]✓[/success] latency_p99           "
            "[muted]target:[/muted] 200ms  "
            "[muted]current:[/muted] 187ms    "
            "[muted]budget:[/muted] 22% burned"
        )
        console.print()

        console.print("[bold]Aggregate Budget:[/bold] 18.7/43.2 minutes consumed (43.3%)")
        console.print()

        console.print(f"[bold]Thresholds ({tier} tier):[/bold]")
        console.print("  [muted]Warning:[/muted] <50% remaining")
        console.print("  [muted]Blocking:[/muted] <10% remaining")
        console.print()

        # Show warning result
        warning("Deployment allowed with WARNING")
        console.print("[muted]Error budget low (56.7% remaining)[/muted]")
        console.print()

        console.print("[bold]Recommendations:[/bold]")
        console.print("  [muted]•[/muted] Review recent changes for reliability impact")
        console.print("  [muted]•[/muted] Consider smaller deployment batch size")
        console.print("  [muted]•[/muted] Ensure rollback plan is ready")
        console.print()
        return 1
