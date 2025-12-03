"""
SLO (Service Level Objective) management.

This module handles OpenSLO parsing, error budget calculation,
and SLO compliance tracking.
"""

from nthlayer.slos.alerts import (
    AlertEvaluator,
    AlertEvent,
    AlertRule,
    AlertSeverity,
    AlertType,
    get_alert_storage,
)
from nthlayer.slos.calculator import ErrorBudgetCalculator
from nthlayer.slos.collector import SLOCollector, collect_and_store_budget, collect_service_budgets
from nthlayer.slos.correlator import CorrelationResult, CorrelationWindow, DeploymentCorrelator
from nthlayer.slos.deployment import Deployment, DeploymentRecorder
from nthlayer.slos.models import SLO, ErrorBudget, SLOStatus, TimeWindow, TimeWindowType
from nthlayer.slos.notifiers import AlertNotifier, SlackNotifier
from nthlayer.slos.parser import OpenSLOParserError, parse_slo_dict, parse_slo_file
from nthlayer.slos.storage import SLORepository

__all__ = [
    "AlertEvaluator",
    "AlertEvent",
    "AlertNotifier",
    "AlertRule",
    "AlertSeverity",
    "AlertType",
    "CorrelationResult",
    "CorrelationWindow",
    "Deployment",
    "DeploymentCorrelator",
    "DeploymentRecorder",
    "ErrorBudget",
    "ErrorBudgetCalculator",
    "OpenSLOParserError",
    "SLO",
    "SLOCollector",
    "SLORepository",
    "SLOStatus",
    "SlackNotifier",
    "TimeWindow",
    "TimeWindowType",
    "collect_and_store_budget",
    "collect_service_budgets",
    "get_alert_storage",
    "parse_slo_dict",
    "parse_slo_file",
]
