"""Tests for PolicyHandler orchestration handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from nthlayer.orchestration.handlers import PolicyHandler
from nthlayer.orchestration.registry import OrchestratorContext


def _make_context(
    tmp_path: Path,
    service_data: dict | None = None,
    resources: list | None = None,
) -> OrchestratorContext:
    """Create a minimal OrchestratorContext for testing."""
    if service_data is None:
        service_data = {
            "name": "test-service",
            "team": "test-team",
            "tier": "standard",
            "type": "api",
        }
    if resources is None:
        resources = []

    service_def = {"service": service_data, "resources": resources}

    service_yaml = tmp_path / "service.yaml"
    service_yaml.write_text(yaml.dump(service_def))

    detector = MagicMock()
    detector.get_resources_by_kind.return_value = [
        r for r in resources if r.get("kind") == "PolicyRules"
    ]

    return OrchestratorContext(
        service_yaml=service_yaml,
        service_def=service_def,
        service_name=service_data["name"],
        output_dir=tmp_path / "output",
        env=None,
        detector=detector,
    )


class TestPolicyHandlerProperties:
    def test_name(self):
        handler = PolicyHandler()
        assert handler.name == "policy"

    def test_display_name(self):
        handler = PolicyHandler()
        assert handler.display_name == "Policy Rules"


class TestPolicyHandlerPlan:
    def test_plan_no_policy_resources(self, tmp_path: Path):
        ctx = _make_context(tmp_path)
        handler = PolicyHandler()
        plan = handler.plan(ctx)
        assert plan == []

    def test_plan_with_policy_resources(self, tmp_path: Path):
        resources = [
            {
                "kind": "PolicyRules",
                "name": "org-policies",
                "spec": {
                    "rules": [
                        {
                            "name": "require-ownership",
                            "type": "required_fields",
                            "params": {"fields": ["ownership.team"]},
                        },
                    ]
                },
            },
        ]
        ctx = _make_context(tmp_path, resources=resources)
        handler = PolicyHandler()
        plan = handler.plan(ctx)
        assert len(plan) == 1
        assert plan[0]["type"] == "policy"
        assert plan[0]["action"] == "evaluate"
        assert plan[0]["count"] == 1


class TestPolicyHandlerGenerate:
    def test_generate_no_policy_resources(self, tmp_path: Path):
        ctx = _make_context(tmp_path)
        handler = PolicyHandler()
        count = handler.generate(ctx)
        assert count == 0

    def test_generate_with_passing_rules(self, tmp_path: Path):
        service_data = {
            "name": "test-service",
            "team": "test-team",
            "tier": "standard",
            "type": "api",
            "description": "A test service",
        }
        resources = [
            {
                "kind": "PolicyRules",
                "name": "org-policies",
                "spec": {
                    "rules": [
                        {
                            "name": "require-name",
                            "type": "required_fields",
                            "params": {"fields": ["name"]},
                        },
                    ]
                },
            },
        ]
        ctx = _make_context(tmp_path, service_data=service_data, resources=resources)
        handler = PolicyHandler()
        count = handler.generate(ctx)
        assert count == 1

    def test_generate_with_violations(self, tmp_path: Path, capsys):
        resources = [
            {
                "kind": "PolicyRules",
                "name": "org-policies",
                "spec": {
                    "rules": [
                        {
                            "name": "require-description",
                            "type": "required_fields",
                            "params": {"fields": ["description"]},
                        },
                    ]
                },
            },
        ]
        ctx = _make_context(tmp_path, resources=resources)
        handler = PolicyHandler()
        count = handler.generate(ctx)
        assert count == 1
        captured = capsys.readouterr()
        assert "require-description" in captured.out

    def test_generate_multiple_policy_resources(self, tmp_path: Path):
        resources = [
            {
                "kind": "PolicyRules",
                "name": "org-policies",
                "spec": {
                    "rules": [
                        {
                            "name": "rule1",
                            "type": "required_fields",
                            "params": {"fields": ["name"]},
                        },
                    ]
                },
            },
            {
                "kind": "PolicyRules",
                "name": "team-policies",
                "spec": {
                    "rules": [
                        {
                            "name": "rule2",
                            "type": "required_fields",
                            "params": {"fields": ["team"]},
                        },
                    ]
                },
            },
        ]
        ctx = _make_context(tmp_path, resources=resources)
        # Update the mock to return both resources
        ctx.detector.get_resources_by_kind.return_value = resources
        handler = PolicyHandler()
        count = handler.generate(ctx)
        assert count == 2
