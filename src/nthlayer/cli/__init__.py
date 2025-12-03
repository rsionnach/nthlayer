"""
CLI commands for NthLayer.
"""

from nthlayer.cli.dashboard import generate_dashboard_command
from nthlayer.cli.dashboard_validate import (
    list_intents_command,
    validate_dashboard_command,
)
from nthlayer.cli.deploy import check_deploy_command
from nthlayer.cli.environments import (
    diff_envs_command,
    list_environments_command,
    validate_env_command,
)
from nthlayer.cli.generate import generate_slo_command
from nthlayer.cli.init import init_command
from nthlayer.cli.pagerduty import setup_pagerduty_command
from nthlayer.cli.recording_rules import generate_recording_rules_command
from nthlayer.cli.templates import list_templates_command
from nthlayer.cli.validate import validate_command

__all__ = [
    "generate_slo_command",
    "validate_command",
    "setup_pagerduty_command",
    "check_deploy_command",
    "list_templates_command",
    "init_command",
    "list_environments_command",
    "diff_envs_command",
    "validate_env_command",
    "generate_dashboard_command",
    "generate_recording_rules_command",
    # Hybrid model validation
    "validate_dashboard_command",
    "list_intents_command",
]
