"""
CLI commands for alert evaluation and management.

Usage:
    nthlayer alerts evaluate <service-file>   # Full pipeline run
    nthlayer alerts show <service-file>       # Show effective rules
    nthlayer alerts explain <service-file>    # Budget explanations
    nthlayer alerts test <service-file>       # Dry-run simulation

Exit codes:
    0 = healthy
    1 = warnings triggered
    2 = critical alerts triggered
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from rich.table import Table

from nthlayer.cli.ux import console, header
from nthlayer.specs.alerting import AlertingConfig, resolve_effective_rules
from nthlayer.specs.loader import load_manifest

# -------------------------------------------------------------------------
# Subcommand implementations
# -------------------------------------------------------------------------


def alerts_evaluate_command(
    service_file: str,
    prometheus_url: str | None = None,
    dry_run: bool = False,
    no_notify: bool = False,
    output_format: str = "table",
    path: str | None = None,
) -> int:
    """
    Evaluate alert rules against live or simulated budget data.

    If ``--path`` is given, evaluates all manifests in the directory.
    """
    from nthlayer.slos.pipeline import AlertPipeline

    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")
    pipeline = AlertPipeline(
        prometheus_url=prom_url,
        dry_run=dry_run,
        notify=not no_notify,
    )

    if path:
        results = _evaluate_directory(pipeline, path)
    else:
        manifest = load_manifest(service_file, suppress_deprecation_warning=True)
        results = [pipeline.evaluate_service(manifest)]

    if output_format == "json":
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        _print_evaluate_table(results)

    return _exit_code(results)


def alerts_show_command(
    service_file: str,
    output_format: str = "table",
) -> int:
    """Show effective alert rules for a service (explicit + auto-generated)."""
    manifest = load_manifest(service_file, suppress_deprecation_warning=True)
    alerting = manifest.alerting or AlertingConfig()
    slo_names = [s.name for s in manifest.slos]
    effective = resolve_effective_rules(alerting, manifest.tier, slo_names)

    if output_format in ("json", "yaml"):
        data = [
            {
                "name": r.name,
                "type": r.type,
                "slo": r.slo,
                "threshold": r.threshold,
                "severity": r.severity,
                "enabled": r.enabled,
            }
            for r in effective
        ]
        if output_format == "json":
            print(json.dumps(data, indent=2))
        else:
            import yaml

            print(yaml.dump(data, default_flow_style=False))
    else:
        _print_rules_table(manifest.name, manifest.tier, effective)

    return 0


def alerts_explain_command(
    service_file: str,
    prometheus_url: str | None = None,
    output_format: str = "table",
    slo_filter: str | None = None,
) -> int:
    """Show budget explanations for a service."""
    from nthlayer.slos.pipeline import AlertPipeline

    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")
    pipeline = AlertPipeline(prometheus_url=prom_url, dry_run=True)
    manifest = load_manifest(service_file, suppress_deprecation_warning=True)
    result = pipeline.evaluate_service(manifest)

    explanations = result.explanations
    if slo_filter:
        # Filter budgets/explanations by SLO name
        budgets_for_slo = [b for b in result.budgets if slo_filter in b.slo_id]
        if not budgets_for_slo:
            console.print(f"[yellow]No SLO matching '{slo_filter}' found[/yellow]")
            return 1
        from nthlayer.slos.explanations import ExplanationEngine

        engine = ExplanationEngine()
        explanations = [
            engine.explain_budget(b, tier=manifest.tier, service_type=manifest.type)
            for b in budgets_for_slo
        ]

    if output_format == "json":
        print(json.dumps([e.to_dict() for e in explanations], indent=2))
    elif output_format == "markdown":
        for expl in explanations:
            print(expl.to_markdown())
            print()
    else:
        for expl in explanations:
            print(expl.to_text())
            print()

    return _exit_code([result])


def alerts_test_command(
    service_file: str,
    prometheus_url: str | None = None,
    simulate_burn: float = 80.0,
    no_notify: bool = False,
) -> int:
    """Simulate budget burn and show what would fire.

    By default, notifications are sent to configured channels (e.g. Slack).
    Pass ``no_notify=True`` to suppress them.
    """
    from nthlayer.slos.pipeline import AlertPipeline

    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")
    pipeline = AlertPipeline(prometheus_url=prom_url, dry_run=False, notify=not no_notify)
    manifest = load_manifest(service_file, suppress_deprecation_warning=True)
    result = pipeline.evaluate_service(manifest, simulate_burn_pct=simulate_burn)

    console.print()
    header(f"Alert Simulation: {manifest.name}")
    console.print(f"[dim]Simulated burn: {simulate_burn}%[/dim]")
    console.print()

    if result.notifications_sent:
        console.print(f"[bold]Notifications sent:[/bold] {result.notifications_sent}")
        console.print()

    if not result.events:
        console.print("[green]No alerts would fire at this burn level.[/green]")
        return 0

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Rule", style="bold")
    table.add_column("SLO")
    table.add_column("Severity")
    table.add_column("Message", max_width=50)

    for event in result.events:
        sev_style = {
            "warning": "yellow",
            "critical": "red bold",
            "info": "dim",
        }.get(event.severity.value, "")
        table.add_row(
            event.rule_id,
            event.slo_id,
            f"[{sev_style}]{event.severity.value.upper()}[/{sev_style}]",
            event.title,
        )

    console.print(table)
    console.print()

    if result.explanations:
        console.print("[bold]Explanations:[/bold]")
        for expl in result.explanations:
            console.print(f"  {expl.headline}")

    return _exit_code([result])


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _evaluate_directory(pipeline: object, dir_path: str) -> list:
    """Load all manifest files from a directory and evaluate them."""
    from nthlayer.slos.pipeline import AlertPipeline, PipelineResult
    from nthlayer.specs.loader import is_manifest_file

    assert isinstance(pipeline, AlertPipeline)
    results: list[PipelineResult] = []
    p = Path(dir_path)
    if not p.is_dir():
        console.print(f"[red]Not a directory: {dir_path}[/red]")
        return results

    for yaml_file in sorted(p.glob("*.yaml")) + sorted(p.glob("*.yml")):
        if not is_manifest_file(yaml_file):
            continue
        try:
            manifest = load_manifest(yaml_file, suppress_deprecation_warning=True)
            results.append(pipeline.evaluate_service(manifest))
        except Exception as exc:
            pr = PipelineResult(service=str(yaml_file))
            pr.errors.append(str(exc))
            results.append(pr)

    return results


def _print_evaluate_table(results: list) -> None:
    console.print()
    header("Alert Evaluation Results")
    console.print()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Service", style="bold")
    table.add_column("SLOs", justify="right")
    table.add_column("Rules", justify="right")
    table.add_column("Alerts", justify="right")
    table.add_column("Notifications", justify="right")
    table.add_column("Status")

    for r in results:
        status_style = {
            "healthy": "green",
            "warning": "yellow",
            "critical": "red bold",
        }.get(r.worst_severity, "dim")
        table.add_row(
            r.service,
            str(r.budgets_evaluated),
            str(r.rules_evaluated),
            str(r.alerts_triggered),
            str(r.notifications_sent),
            f"[{status_style}]{r.worst_severity.upper()}[/{status_style}]",
        )

    console.print(table)

    if any(r.errors for r in results):
        console.print()
        console.print("[red bold]Errors:[/red bold]")
        for r in results:
            for err in r.errors:
                console.print(f"  [red]{r.service}: {err}[/red]")

    console.print()


def _print_rules_table(service: str, tier: str, rules: list) -> None:
    console.print()
    header(f"Effective Alert Rules: {service}")
    console.print(f"[dim]Tier: {tier} | Rules: {len(rules)}[/dim]")
    console.print()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("SLO")
    table.add_column("Threshold", justify="right")
    table.add_column("Severity")
    table.add_column("Enabled")

    for r in rules:
        sev_style = {"warning": "yellow", "critical": "red"}.get(r.severity, "")
        table.add_row(
            r.name,
            r.type,
            r.slo,
            f"{r.threshold}",
            f"[{sev_style}]{r.severity}[/{sev_style}]",
            "yes" if r.enabled else "no",
        )

    console.print(table)
    console.print()


def _exit_code(results: list) -> int:
    """Determine exit code from pipeline results."""
    for r in results:
        if r.worst_severity == "critical":
            return 2
    for r in results:
        if r.worst_severity == "warning":
            return 1
    return 0


# -------------------------------------------------------------------------
# Parser registration (follows register_*_parser / handle_*_command pattern)
# -------------------------------------------------------------------------


def register_alerts_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``alerts`` subcommand group."""
    alerts_parser = subparsers.add_parser(
        "alerts",
        help="Evaluate, simulate, and explain alert rules",
        description=(
            "Run alert evaluation against service specs. "
            "Exit codes: 0=healthy, 1=warning, 2=critical."
        ),
    )

    alerts_sub = alerts_parser.add_subparsers(dest="alerts_command")

    # evaluate
    eval_p = alerts_sub.add_parser("evaluate", help="Full pipeline evaluation")
    eval_p.add_argument("service_file", nargs="?", help="Path to service YAML file")
    eval_p.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus URL (or set NTHLAYER_PROMETHEUS_URL)",
    )
    eval_p.add_argument("--dry-run", action="store_true", help="No notifications")
    eval_p.add_argument("--no-notify", action="store_true", help="Suppress notifications")
    eval_p.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    eval_p.add_argument(
        "--path",
        help="Evaluate all manifests in directory",
    )

    # show
    show_p = alerts_sub.add_parser("show", help="Show effective alert rules")
    show_p.add_argument("service_file", help="Path to service YAML file")
    show_p.add_argument(
        "--format",
        choices=["table", "json", "yaml"],
        default="table",
        help="Output format (default: table)",
    )

    # explain
    explain_p = alerts_sub.add_parser("explain", help="Show budget explanations")
    explain_p.add_argument("service_file", help="Path to service YAML file")
    explain_p.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus URL (or set NTHLAYER_PROMETHEUS_URL)",
    )
    explain_p.add_argument(
        "--format",
        choices=["table", "json", "markdown"],
        default="table",
        help="Output format (default: table)",
    )
    explain_p.add_argument("--slo", dest="slo_filter", help="Filter by SLO name")

    # test
    test_p = alerts_sub.add_parser("test", help="Simulate burn and show what would fire")
    test_p.add_argument("service_file", help="Path to service YAML file")
    test_p.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus URL (or set NTHLAYER_PROMETHEUS_URL)",
    )
    test_p.add_argument(
        "--simulate-burn",
        type=float,
        default=80.0,
        help="Percentage of budget consumed to simulate (default: 80)",
    )
    test_p.add_argument(
        "--no-notify",
        action="store_true",
        help="Suppress sending notifications to configured channels",
    )


def handle_alerts_command(args: argparse.Namespace) -> int:
    """Route ``nthlayer alerts <sub>`` to the correct handler."""
    sub = getattr(args, "alerts_command", None)

    if sub == "evaluate":
        return alerts_evaluate_command(
            service_file=getattr(args, "service_file", None) or "",
            prometheus_url=getattr(args, "prometheus_url", None),
            dry_run=getattr(args, "dry_run", False),
            no_notify=getattr(args, "no_notify", False),
            output_format=getattr(args, "format", "table"),
            path=getattr(args, "path", None),
        )

    if sub == "show":
        return alerts_show_command(
            service_file=args.service_file,
            output_format=getattr(args, "format", "table"),
        )

    if sub == "explain":
        return alerts_explain_command(
            service_file=args.service_file,
            prometheus_url=getattr(args, "prometheus_url", None),
            output_format=getattr(args, "format", "table"),
            slo_filter=getattr(args, "slo_filter", None),
        )

    if sub == "test":
        return alerts_test_command(
            service_file=args.service_file,
            prometheus_url=getattr(args, "prometheus_url", None),
            simulate_burn=getattr(args, "simulate_burn", 80.0),
            no_notify=getattr(args, "no_notify", False),
        )

    console.print("Usage: nthlayer alerts {evaluate|show|explain|test}")
    return 1
