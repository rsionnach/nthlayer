"""
Interactive setup wizard for NthLayer.

Provides a simplified first-time setup experience with connection testing
and guided service creation.

Commands:
    nthlayer setup              # Interactive first-time setup
    nthlayer setup --quick      # Skip advanced options (default)
    nthlayer setup --advanced   # Full configuration wizard
    nthlayer setup --test       # Test connections only
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from nthlayer.cli.ux import (
    confirm,
    console,
    error,
    header,
    info,
    password_input,
    select,
    success,
    text_input,
    warning,
)
from nthlayer.config.integrations import (
    GrafanaProfile,
    GrafanaType,
    IntegrationConfig,
    PrometheusProfile,
    PrometheusType,
)
from nthlayer.config.loader import (
    get_config_path,
    load_config,
    save_config,
)
from nthlayer.config.secrets import get_secret_resolver


def setup_command(
    quick: bool = True,
    test_only: bool = False,
    skip_service: bool = False,
) -> int:
    """
    Interactive first-time setup wizard.

    Args:
        quick: Use simplified setup (default True)
        test_only: Only test connections, don't configure
        skip_service: Skip first service creation prompt

    Returns:
        Exit code (0 for success)
    """
    if test_only:
        return _test_connections()

    _print_welcome_banner()

    # Check if already configured
    config_path = get_config_path()
    if config_path and config_path.exists():
        warning(f"Existing configuration found at: {config_path}")
        if not _confirm("Overwrite existing configuration?", default=False):
            info("Setup cancelled. Use 'nthlayer config show' to view current config.")
            return 0

    if quick:
        result = _quick_setup()
    else:
        # Import and use existing advanced wizard
        from nthlayer.config.cli import config_init_command

        result = config_init_command()

    if result != 0:
        return result

    # Test connections after setup
    print()
    _test_connections()

    # Offer to create first service
    if not skip_service:
        print()
        if _confirm("Create your first service?", default=True):
            _create_first_service()

    _print_next_steps()
    return 0


def _print_welcome_banner() -> None:
    """Print welcome banner."""
    console.print()
    header("Welcome to NthLayer!")
    console.print(
        "[muted]The missing layer of reliability - 20 hours of SRE work in 5 minutes[/muted]"
    )
    console.print()


def _quick_setup() -> int:
    """
    Simplified setup for most users.

    Configures:
    1. Prometheus URL
    2. Grafana URL + API key (optional)
    3. PagerDuty API key (optional)
    """
    config = IntegrationConfig.default()
    resolver = get_secret_resolver()

    console.print("[bold]Quick Setup[/bold]")
    console.print("[muted]─[/muted]" * 40)
    console.print("We'll configure the essentials to get you started.")
    console.print("You can always run 'nthlayer config init' for advanced options.\n")

    # 1. Prometheus
    console.print("[bold cyan]1. Prometheus Configuration[/bold cyan]")
    console.print("   NthLayer queries Prometheus for SLO metrics and metric discovery.\n")

    prom_url = _prompt("   Prometheus URL", default="http://localhost:9090")

    prom_profile = PrometheusProfile(
        name="default",
        type=PrometheusType.PROMETHEUS,
        url=prom_url,
    )

    # Check if auth needed
    if _confirm("   Does Prometheus require authentication?", default=False):
        prom_profile.username = _prompt("   Username")
        prom_password = _prompt_secret("   Password")
        resolver.set_secret("prometheus/password", prom_password)
        prom_profile.password_secret = "prometheus/password"

    config.prometheus.profiles["default"] = prom_profile
    config.prometheus.default = "default"
    console.print()

    # 2. Grafana (optional)
    console.print("[bold cyan]2. Grafana Configuration[/bold cyan] [muted](optional)[/muted]")
    console.print("   NthLayer can push dashboards directly to Grafana.\n")

    if _confirm("   Configure Grafana?", default=True):
        grafana_url = _prompt("   Grafana URL", default="http://localhost:3000")

        grafana_profile = GrafanaProfile(
            name="default",
            type=GrafanaType.GRAFANA,
            url=grafana_url,
        )

        grafana_key = _prompt_secret("   API Key (press Enter to skip)")
        if grafana_key:
            resolver.set_secret("grafana/api_key", grafana_key)
            grafana_profile.api_key_secret = "grafana/api_key"

        config.grafana.profiles["default"] = grafana_profile
        config.grafana.default = "default"
    console.print()

    # 3. PagerDuty (optional)
    console.print("[bold cyan]3. PagerDuty Configuration[/bold cyan] [muted](optional)[/muted]")
    console.print("   NthLayer can create teams, schedules, and escalation policies.\n")

    if _confirm("   Configure PagerDuty?", default=False):
        config.alerting.pagerduty.enabled = True

        pd_key = _prompt_secret("   API Key (with full access)")
        if pd_key:
            resolver.set_secret("pagerduty/api_key", pd_key)
            config.alerting.pagerduty.api_key_secret = "pagerduty/api_key"

        policy = _prompt("   Default escalation policy (optional)", default="")
        if policy:
            config.alerting.pagerduty.default_escalation_policy = policy
    console.print()

    # Save configuration
    config_dir = Path.home() / ".nthlayer"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config.yaml"

    save_config(config, config_path)
    success(f"Configuration saved to: {config_path}")

    return 0


def _test_connections() -> int:
    """Test all configured connections."""
    console.print("[bold]Testing Connections[/bold]")
    console.print("[muted]─[/muted]" * 40)

    config = load_config()
    all_ok = True

    # Test Prometheus
    prom_profile = config.prometheus.profiles.get(config.prometheus.default)
    if prom_profile:
        console.print(f"\n  [cyan]Prometheus[/cyan] ({prom_profile.url})")
        prom_ok, prom_msg = _test_prometheus(prom_profile)
        if prom_ok:
            console.print(f"    [success]✓[/success] {prom_msg}")
        else:
            console.print(f"    [error]✗[/error] {prom_msg}")
            all_ok = False
    else:
        console.print("\n  [cyan]Prometheus:[/cyan] [muted]Not configured[/muted]")

    # Test Grafana
    grafana_profile = config.grafana.profiles.get(config.grafana.default)
    if grafana_profile:
        console.print(f"\n  [cyan]Grafana[/cyan] ({grafana_profile.url})")
        grafana_ok, grafana_msg = _test_grafana(grafana_profile)
        if grafana_ok:
            console.print(f"    [success]✓[/success] {grafana_msg}")
        else:
            console.print(f"    [error]✗[/error] {grafana_msg}")
            all_ok = False
    else:
        console.print("\n  [cyan]Grafana:[/cyan] [muted]Not configured[/muted]")

    # Test PagerDuty
    if config.alerting.pagerduty.enabled:
        console.print("\n  [cyan]PagerDuty[/cyan]")
        pd_ok, pd_msg = _test_pagerduty(config)
        if pd_ok:
            console.print(f"    [success]✓[/success] {pd_msg}")
        else:
            console.print(f"    [error]✗[/error] {pd_msg}")
            all_ok = False
    else:
        console.print("\n  [cyan]PagerDuty:[/cyan] [muted]Not configured[/muted]")

    console.print()
    if all_ok:
        success("All configured services are operational!")
    else:
        error("Some connections failed. Check your configuration.")

    return 0 if all_ok else 1


def _test_prometheus(profile: PrometheusProfile) -> tuple[bool, str]:
    """Test Prometheus connection."""
    try:
        import httpx

        # Build auth if needed
        auth = None
        if profile.username:
            password = profile.get_password() or ""
            auth = (profile.username, password)

        with httpx.Client(timeout=10.0) as client:
            # Try to get build info
            response = client.get(
                f"{profile.url}/api/v1/status/buildinfo",
                auth=auth,
            )

            if response.status_code == 200:
                data = response.json()
                version = data.get("data", {}).get("version", "unknown")
                return True, f"Connected (Prometheus {version})"
            elif response.status_code == 401:
                return False, "Authentication required"
            else:
                return False, f"HTTP {response.status_code}"

    except httpx.ConnectError:
        return False, "Connection refused - is Prometheus running?"
    except httpx.TimeoutException:
        return False, "Connection timed out"
    except Exception as e:
        return False, str(e)


def _test_grafana(profile: GrafanaProfile) -> tuple[bool, str]:
    """Test Grafana connection."""
    try:
        import httpx

        headers = {}
        api_key = profile.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        with httpx.Client(timeout=10.0) as client:
            # Try to get health
            response = client.get(
                f"{profile.url}/api/health",
                headers=headers,
            )

            if response.status_code == 200:
                # Try to get org info if we have an API key
                if api_key:
                    org_response = client.get(
                        f"{profile.url}/api/org",
                        headers=headers,
                    )
                    if org_response.status_code == 200:
                        org_name = org_response.json().get("name", "Unknown")
                        return True, f"Connected - Org: {org_name}"
                return True, "Connected (no API key - limited access)"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"HTTP {response.status_code}"

    except httpx.ConnectError:
        return False, "Connection refused - is Grafana running?"
    except httpx.TimeoutException:
        return False, "Connection timed out"
    except Exception as e:
        return False, str(e)


def _test_pagerduty(config: IntegrationConfig) -> tuple[bool, str]:
    """Test PagerDuty connection."""
    try:
        resolver = get_secret_resolver()
        api_key = resolver.resolve(config.alerting.pagerduty.api_key_secret or "pagerduty/api_key")

        if not api_key:
            # Try environment variable
            api_key = os.environ.get("PAGERDUTY_API_KEY")

        if not api_key:
            return False, "No API key configured"

        import httpx

        headers = {
            "Authorization": f"Token token={api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                "https://api.pagerduty.com/abilities",
                headers=headers,
            )

            if response.status_code == 200:
                # Get escalation policy count
                policies_response = client.get(
                    "https://api.pagerduty.com/escalation_policies",
                    headers=headers,
                    params={"limit": 1},
                )
                if policies_response.status_code == 200:
                    total = policies_response.json().get("total", 0)
                    return True, f"Connected - {total} escalation policies"
                return True, "Connected"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"HTTP {response.status_code}"

    except Exception as e:
        return False, str(e)


def _create_first_service() -> None:
    """Guide user through creating their first service."""
    console.print()
    console.print("[bold]Create Your First Service[/bold]")
    console.print("[muted]─[/muted]" * 40)

    # Get service details
    service_name = _prompt("Service name (e.g., payment-api)")
    if not service_name:
        info("Skipping service creation.")
        return

    # Validate name
    if not _is_valid_service_name(service_name):
        error(f"Invalid service name: {service_name}")
        console.print("Use lowercase letters, numbers, and hyphens only.")
        return

    team = _prompt("Team name", default="platform")

    # Service type selection using interactive menu
    type_choices = [
        "api - HTTP/REST API service",
        "worker - Background job processor",
        "stream - Stream/event processor",
    ]
    selected_type = select("Service type", type_choices, default=type_choices[0])
    service_type = selected_type.split(" - ")[0]

    # Service tier selection using interactive menu
    tier_choices = [
        "critical - 99.95% availability, 5min escalation",
        "standard - 99.9% availability, 15min escalation",
        "low - 99.5% availability, 30min escalation",
    ]
    selected_tier = select("Service tier", tier_choices, default=tier_choices[1])
    tier_name = selected_tier.split(" - ")[0]
    tier_map = {"critical": 1, "standard": 2, "low": 3}
    tier = tier_map.get(tier_name, 2)

    # Create services directory
    services_dir = Path("services")
    services_dir.mkdir(exist_ok=True)

    # Generate service YAML
    service_content = _generate_service_yaml(service_name, team, service_type, tier)

    service_file = services_dir / f"{service_name}.yaml"
    if service_file.exists():
        if not _confirm(f"{service_file} exists. Overwrite?", default=False):
            info("Skipping service creation.")
            return

    service_file.write_text(service_content)
    console.print()
    success(f"Created {service_file}")


def _generate_service_yaml(
    name: str,
    team: str,
    service_type: str,
    tier: int,
) -> str:
    """Generate service YAML content."""
    # Tier-based defaults
    tier_configs = {
        1: {"availability": 99.95, "latency_ms": 200, "tier_name": "critical"},
        2: {"availability": 99.9, "latency_ms": 500, "tier_name": "standard"},
        3: {"availability": 99.5, "latency_ms": 1000, "tier_name": "low"},
    }
    config = tier_configs.get(tier, tier_configs[2])

    return f"""# {name} Service Definition
# Generated by NthLayer setup wizard

service:
  name: {name}
  team: {team}
  tier: {tier}
  type: {service_type}

resources:
  # SLO: Availability
  - kind: SLO
    name: availability
    spec:
      objective: {config['availability']}
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{{service="{name}",status!~"5.."}}[5m])) /
          sum(rate(http_requests_total{{service="{name}"}}[5m]))

  # SLO: Latency (p99)
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      threshold_ms: {config['latency_ms']}
      indicator:
        type: latency
        percentile: 99
        query: |
          histogram_quantile(0.99,
            sum by (le) (rate(http_request_duration_seconds_bucket{{service="{name}"}}[5m]))
          )

  # PagerDuty integration
  - kind: PagerDuty
    name: alerting
    spec:
      urgency: {"high" if tier == 1 else "low"}
      auto_create: true

  # Dependencies (customize as needed)
  # - kind: Dependencies
  #   name: deps
  #   spec:
  #     databases:
  #       - type: postgresql
  #       - type: redis
"""


def _is_valid_service_name(name: str) -> bool:
    """Validate service name format."""
    if not name:
        return False
    if name[0] == "-" or name[-1] == "-":
        return False
    for char in name:
        if not (char.islower() or char.isdigit() or char == "-"):
            return False
    return True


def _print_next_steps() -> None:
    """Print next steps after setup."""
    console.print()
    header("Setup Complete!")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  [cyan]1.[/cyan] nthlayer plan services/<service>.yaml")
    console.print("  [cyan]2.[/cyan] nthlayer apply services/<service>.yaml")
    console.print("  [cyan]3.[/cyan] nthlayer portfolio")
    console.print()
    console.print("[bold]Useful commands:[/bold]")
    console.print("  nthlayer config show    [muted]# View current configuration[/muted]")
    console.print("  nthlayer setup --test   [muted]# Re-test connections[/muted]")
    console.print("  nthlayer --help         [muted]# See all commands[/muted]")
    console.print()


def _prompt(message: str, default: str | None = None) -> str:
    """Prompt user for input with optional default."""
    return text_input(message, default=default or "")


def _prompt_secret(message: str) -> str:
    """Prompt user for secret input (hidden)."""
    return password_input(message)


def _confirm(message: str, default: bool = True) -> bool:
    """Prompt user for yes/no confirmation."""
    return confirm(message, default=default)


def config_exists() -> bool:
    """Check if NthLayer configuration exists."""
    config_path = get_config_path()
    return config_path is not None and config_path.exists()


def register_setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register setup subcommand parser."""
    parser = subparsers.add_parser(
        "setup",
        help="Interactive first-time setup wizard",
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        default=True,
        help="Use simplified setup (default)",
    )

    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Use advanced setup with all options",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Test connections only",
    )

    parser.add_argument(
        "--skip-service",
        action="store_true",
        help="Skip first service creation prompt",
    )


def handle_setup_command(args: argparse.Namespace) -> int:
    """Handle setup subcommand."""
    return setup_command(
        quick=not getattr(args, "advanced", False),
        test_only=getattr(args, "test", False),
        skip_service=getattr(args, "skip_service", False),
    )
