"""Rich terminal output for simulation results."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from nthlayer.cli.ux import console
from nthlayer.simulate.models import SimulationResult


def print_simulation_table(result: SimulationResult) -> None:
    """Print simulation results as a formatted Rich table."""
    # Header panel
    console.print()
    p_pct = result.p_meeting_sla * 100
    sla_pct = result.target_sla * 100

    if p_pct >= 80:
        p_color = "green"
    elif p_pct >= 50:
        p_color = "yellow"
    else:
        p_color = "red"

    header_text = (
        f"[bold]SLA Simulation: {result.target_service}[/bold]\n"
        f"[muted]{result.num_runs:,} runs, {result.horizon_days}-day horizon[/muted]"
    )
    console.print(Panel(header_text, border_style="cyan"))
    console.print()

    # Headline numbers
    console.print(f"  [cyan]Target SLA:[/cyan]     {sla_pct:.1f}% availability")
    console.print(f"  [cyan]P(meeting SLA):[/cyan] [{p_color} bold]{p_pct:.1f}%[/]")
    console.print()

    # Weakest link
    wl = result.weakest_link
    wl_pct = result.weakest_link_contribution * 100
    console.print(
        f"  [cyan]Weakest link:[/cyan]   {wl} "
        f"([muted]contributes {wl_pct:.0f}% of downtime[/muted])"
    )
    console.print()

    # Error budget forecast
    forecast = result.error_budget_forecast
    if forecast.p50 is not None:
        console.print("  [bold]Error budget forecast:[/bold]")
        console.print(
            f"    Median exhaustion:      day {forecast.p50:.0f} of {result.horizon_days}"
        )
        if forecast.p95 is not None:
            console.print(
                f"    Worst case (p95):       day {forecast.p95:.0f} of {result.horizon_days}"
            )
        console.print()

    # Per-service table
    table = Table(title="Per-Service Results", show_header=True, header_style="bold")
    table.add_column("Service", style="cyan")
    table.add_column("Target", justify="right")
    table.add_column("P(SLA)", justify="right")
    table.add_column("Avail p50", justify="right")
    table.add_column("Avail p99", justify="right")
    table.add_column("Downtime %", justify="right")

    for name, svc in sorted(result.services.items()):
        target_str = f"{svc.target * 100:.2f}%" if svc.target else "—"
        p_sla_str = f"{svc.p_meeting_sla * 100:.1f}%" if svc.p_meeting_sla is not None else "—"
        p50_str = f"{svc.availability_p50 * 100:.3f}%"
        p99_str = f"{svc.availability_p99 * 100:.3f}%"
        dt_str = f"{svc.downtime_contribution * 100:.1f}%"

        display_name = f"[bold red]{name}[/bold red]" if svc.is_weakest_link else name
        table.add_row(display_name, target_str, p_sla_str, p50_str, p99_str, dt_str)

    console.print(table)
    console.print()

    # What-if results
    if result.what_if_results:
        console.print("[bold]What-if scenarios:[/bold]")
        for wif in result.what_if_results:
            delta_pct = wif.delta * 100
            if delta_pct > 0:
                delta_str = f"[green]+{delta_pct:.1f}%[/green]"
            else:
                delta_str = f"[red]{delta_pct:.1f}%[/red]  [warning]← reduces reliability[/warning]"

            base_pct = wif.base_p_meeting_sla * 100
            mod_pct = wif.modified_p_meeting_sla * 100
            console.print(
                f"  {wif.scenario:<35s}  " f"P(SLA) {base_pct:.1f}% → {mod_pct:.1f}%  ({delta_str})"
            )
        console.print()
