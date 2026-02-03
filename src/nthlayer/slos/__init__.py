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
from nthlayer.slos.ceiling import (
    CeilingValidationResult,
    DependencySLA,
    calculate_slo_ceiling,
    extract_dependencies_from_spec,
    extract_dependencies_with_slas,
    validate_slo_ceiling,
)
from nthlayer.slos.collector import SLOCollector, collect_and_store_budget, collect_service_budgets
from nthlayer.slos.correlator import CorrelationResult, CorrelationWindow, DeploymentCorrelator
from nthlayer.slos.deployment import Deployment, DeploymentRecorder
from nthlayer.slos.explanations import BudgetExplanation, ExplanationEngine
from nthlayer.slos.models import SLO, ErrorBudget, SLOStatus, TimeWindow, TimeWindowType
from nthlayer.slos.notifiers import AlertNotifier, SlackNotifier
from nthlayer.slos.parser import OpenSLOParserError, parse_slo_dict, parse_slo_file
from nthlayer.slos.pipeline import AlertPipeline, PipelineResult
from nthlayer.slos.storage import SLORepository

__all__ = [
    "AlertEvaluator",
    "AlertEvent",
    "AlertNotifier",
    "AlertPipeline",
    "AlertRule",
    "AlertSeverity",
    "AlertType",
    "BudgetExplanation",
    "CeilingValidationResult",
    "CorrelationResult",
    "CorrelationWindow",
    "Deployment",
    "DeploymentCorrelator",
    "DeploymentRecorder",
    "DependencySLA",
    "ErrorBudget",
    "ErrorBudgetCalculator",
    "ExplanationEngine",
    "OpenSLOParserError",
    "PipelineResult",
    "SLO",
    "SLOCollector",
    "SLORepository",
    "SLOStatus",
    "SlackNotifier",
    "TimeWindow",
    "TimeWindowType",
    "calculate_slo_ceiling",
    "collect_and_store_budget",
    "collect_service_budgets",
    "extract_dependencies_from_spec",
    "extract_dependencies_with_slas",
    "get_alert_storage",
    "parse_slo_dict",
    "parse_slo_file",
    "validate_slo_ceiling",
]
