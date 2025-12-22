#!/usr/bin/env python3
"""Update beads issues to reflect actual completion status."""

import json
from datetime import datetime
from pathlib import Path

BEADS_FILE = Path(__file__).parent.parent / ".beads" / "issues.jsonl"

# Issues that are COMPLETE
COMPLETED = {
    "trellis-0cp": "Prometheus integration for SLI metrics - SLOMetricCollector implemented",
    "trellis-3ca": "Foundation & MVP Development - 470 tests passing",
    "trellis-3e6": "Deployment Policies & Gates - check-deploy command complete",
    "trellis-3h6": "Error Budget Foundation - slo show/list/collect done",
    "trellis-5up": "CLI commands for error budget - nthlayer slo commands complete",
    "trellis-7pw": "Observability Suite Expansion - 16 technology templates complete",
    "trellis-a4d": "Condition evaluator engine - ConditionEvaluator in policies/evaluator.py",
    "trellis-ygb": "Error budget calculator - ErrorBudgetCalculator in slos/calculator.py",
    "trellis-z6x": "OpenSLO parser - SLO parsing in specs/parser.py",
    "trellis-gzx": "SLO/SLI generation and tracking - complete",
    "trellis-rpv": "Live Demo Infrastructure - Fly.io app + GitHub Pages",
    "trellis-uum": "Elasticsearch technology template - elasticsearch_intent.py complete",
    "trellis-e8w": "MongoDB technology template - mongodb_intent.py complete",
    "trellis-portfolio-export": "Portfolio Export - json/csv/markdown formats in portfolio command",
    "trellis-portfolio-insights": "Portfolio Insights - insights generation in aggregator.py",
    "trellis-0fl": "ArgoCD deployment blocking - examples/cicd/argocd/ complete",
    "trellis-tnr": "Policy YAML DSL - DeploymentGate resource spec implemented",
}

# Issues that should be DEFERRED (not core to current roadmap)
DEFERRED = {
    # Phase 7 - Intelligent Reliability (deferred)
    "trellis-tt3": "Deferred: Phase 7 - Intelligent Alerts (requires ML infrastructure)",
    "trellis-6ue": "Deferred: Phase 7 - Anomaly detection (ML-based, different product)",
    "trellis-0gr": "Deferred: Reliability scorecard (nice-to-have after core complete)",
    "trellis-4tu": "Deferred: Threshold-based alert engine (Phase 7)",
    "trellis-5ay": "Deferred: Slack rich notifications (Phase 7)",
    "trellis-7uq": "Deferred: PagerDuty incident creation (Phase 7)",
    "trellis-9ri": "Deferred: Template-based explanations (Phase 7)",
    "trellis-32m": "Deferred: Email summary automation (Phase 7)",
    # Phase 8 - Reliability Testing (deferred)
    "trellis-1kc": "Deferred: Phase 8 - Synthetic monitoring (dedicated tools exist)",
    # Out of scope - Different products
    "trellis-3um": "Out of scope: Cost Management (different product)",
    "trellis-gmi": "Out of scope: Compliance & Governance (different product)",
    "trellis-yv6": "Out of scope: Access Control & Security (K8s RBAC native)",
    "trellis-102": "Out of scope: K8s RBAC policies (K8s native)",
    "trellis-115": "Out of scope: Backup/DR policies (infrastructure concern)",
    "trellis-1ne": "Out of scope: SOC2 control mappings (compliance tool)",
    "trellis-1tr": "Out of scope: Data retention automation (ops concern)",
    "trellis-65h": "Out of scope: K8s resource quotas (K8s native)",
    "trellis-836": "Out of scope: Cost allocation tagging (AWS native)",
    "trellis-9k6": "Out of scope: AWS budget alerts (AWS native)",
    "trellis-9mo": "Out of scope: Database permission management",
    "trellis-bpn": "Out of scope: Network policy generation (K8s native)",
    "trellis-nw3": "Out of scope: Auto-scaling policies (K8s HPA native)",
    "trellis-oi0": "Out of scope: AWS IAM roles (Terraform/CDK domain)",
    "trellis-zeb": "Out of scope: GDPR data handling (compliance tool)",
    "trellis-nm3": "Out of scope: Audit logging (ops concern)",
    # Phase 5+ - AI features (deferred/optional)
    "trellis-ai-epic": "Deferred: Phase 5 - AI-Powered NthLayer (optional)",
    "trellis-ai-deps": "Deferred: Phase 5 - Dependency inference (AI)",
    "trellis-ai-explain": "Deferred: Phase 5 - Anomaly explanation (AI)",
    "trellis-ai-query": "Deferred: Phase 5 - Natural language queries (AI)",
    "trellis-ai-runbooks": "Deferred: Phase 5 - AI-enhanced runbooks (AI)",
    "trellis-ai-services": "Deferred: AI/ML service type support",
    "trellis-ai-slo": "Deferred: Phase 5 - SLO recommendations (AI)",
    "trellis-ai-spec-gen": "Deferred: Phase 5 - Conversational spec generation (AI)",
    "trellis-ai-suggestions": "Deferred: Phase 5 - Intelligent suggestions (AI)",
    "trellis-mcp-server": "Deferred: Phase 5 - NthLayer MCP Server (AI)",
    # Integrations - not core
    "trellis-backstage-epic": "Deferred: Backstage integration (distribution channel)",
    "trellis-backstage-plugin": "Deferred: Backstage plugin (distribution channel)",
    "trellis-backstage-read": "Deferred: Backstage catalog reader (integration)",
    "trellis-cortex-read": "Deferred: Cortex catalog reader (integration)",
    "trellis-catalog": "Deferred: Service Catalog Integration (optional)",
    "trellis-hybrid-mode": "Deferred: Hybrid catalog mode (optional)",
    "trellis-datadog": "Deferred: Datadog Integration (Prometheus/Grafana first)",
    "trellis-datadog-dashboards": "Deferred: Datadog dashboard generation",
    "trellis-datadog-monitors": "Deferred: Datadog monitor generation",
    "trellis-incidentio": "Deferred: incident.io Integration",
    # Incident Management - PagerDuty core done, rest deferred
    "trellis-411": "Deferred: Incident Management Expansion (PagerDuty core done)",
    "trellis-4dw": "Deferred: PagerDuty on-call schedules (needs Backstage)",
    "trellis-5ha": "Deferred: PagerDuty incident attribution (Phase 7)",
    "trellis-7jw": "Deferred: Post-incident automation (Jira/Linear)",
    "trellis-dr5": "Deferred: War room automation (Slack)",
    "trellis-yw3": "Deferred: Incident response role assignment",
    # Documentation & Misc - nice to have
    "trellis-l40": "Deferred: Documentation & Knowledge (ongoing)",
    "trellis-0a7": "Deferred: Onboarding guide generation",
    "trellis-9nc": "Deferred: Confluence/Notion integration",
    "trellis-cok": "Deferred: Service documentation templates",
    # Deployment extras - core gate done
    "trellis-44v": "Deferred: Deployment notification system",
    "trellis-9ug": "Deferred: Progressive delivery configs",
    "trellis-3ap": "Deferred: Audit logging for policies",
    "trellis-yb5": "Deferred: Deployment detection via ArgoCD",
    "trellis-z2b": "Deferred: Deploy → burn correlation engine",
    "trellis-deploy-correlation": "Deferred: Enhanced deploy correlation",
    # GitHub Actions Marketplace - distribution
    "trellis-gh-actions": "Deferred: GitHub Actions Marketplace (distribution)",
    "trellis-gh-actions-deploy": "Deferred: check-deploy-action (distribution)",
    "trellis-gh-actions-lint": "Deferred: lint-action (distribution)",
    "trellis-gh-actions-verify": "Deferred: verify-action (distribution)",
    # Other deferred features
    "trellis-ca5": "Deferred: GitHub Actions workflow generation",
    "trellis-t2h": "Deferred: GitLab CI pipeline generation",
    "trellis-cpx": "Deferred: Runbook content generation",
    "trellis-meh": "Deferred: Runbook auto-generation",
    "trellis-t95": "Deferred: Dependency graph visualization",
    "trellis-docs1": "Deferred: Mermaid diagram refactor",
    "trellis-c5v": "Deferred: Log aggregation configuration",
    "trellis-6h9": "Deferred: APM/tracing configuration",
    "trellis-mwq": "Deferred: Continuous profiling setup",
    "trellis-kxt": "Deferred: API gateway configurations",
    "trellis-xy3": "Deferred: Vault secrets management",
    "trellis-e3n": "Deferred: OPA/Sentinel policies",
    "trellis-govlayer": "Deferred: GovLayer Policy Enforcement",
    "trellis-policy-engine": "Deferred: Policy engine core (basic gates done)",
    "trellis-resource-limits": "Deferred: Resource limit policies",
    "trellis-approval-workflows": "Deferred: Approval workflows",
    "trellis-mesh-discovery": "Deferred: Service mesh discovery",
    "trellis-discovery-enhance": "Deferred: OpenMetrics parser enhancement",
    "trellis-vhs-action": "Deferred: VHS GitHub Action",
    "trellis-pd2": "Deferred: PagerDuty team membership",
    "trellis-pd3": "Deferred: PagerDuty demo site",
    "trellis-portfolio-trends": "Deferred: Local trend storage (requires database)",
    "trellis-portfolio-web": "Deferred: Local web dashboard",
    "trellis-b54": "Deferred: Time-series storage (requires database)",
}


def update_beads():
    """Update beads file with completion/deferral status."""
    now = datetime.utcnow().isoformat() + "Z"

    # Read all issues
    issues = []
    with open(BEADS_FILE, "r") as f:
        for line in f:
            if line.strip():
                issues.append(json.loads(line))

    # Track changes
    completed_count = 0
    deferred_count = 0

    # Update issues
    for issue in issues:
        issue_id = issue["id"]

        if issue_id in COMPLETED and issue["status"] != "closed":
            issue["status"] = "closed"
            issue["updated_at"] = now
            issue["closed_at"] = now
            issue["close_reason"] = f"Complete: {COMPLETED[issue_id]}"
            completed_count += 1
            print(f"CLOSED: {issue_id} - {issue['title']}")

        elif issue_id in DEFERRED and issue["status"] == "open":
            # Add deferred comment instead of closing
            if "comments" not in issue:
                issue["comments"] = []

            # Check if already has deferred comment
            has_deferred = any(
                "deferred" in c.get("text", "").lower()
                or "out of scope" in c.get("text", "").lower()
                for c in issue.get("comments", [])
            )

            if not has_deferred:
                issue["comments"].append(
                    {
                        "id": len(issue.get("comments", [])) + 100,
                        "issue_id": issue_id,
                        "author": "scope-review",
                        "text": DEFERRED[issue_id],
                        "created_at": now,
                    }
                )
                issue["updated_at"] = now
                # Set to lower priority
                issue["priority"] = 3
                deferred_count += 1
                print(f"DEFERRED: {issue_id} - {issue['title']}")

    # Write back
    with open(BEADS_FILE, "w") as f:
        for issue in issues:
            f.write(json.dumps(issue, separators=(",", ":")) + "\n")

    print("\n=== Summary ===")
    print(f"Completed: {completed_count}")
    print(f"Deferred: {deferred_count}")

    # Count remaining open
    open_count = sum(1 for i in issues if i["status"] == "open")
    print(f"Remaining open: {open_count}")


if __name__ == "__main__":
    update_beads()
