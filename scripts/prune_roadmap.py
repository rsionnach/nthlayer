#!/usr/bin/env python3
"""Prune roadmap beads based on focused core strategy."""

import json
from datetime import datetime
from pathlib import Path

BEADS_FILE = Path(__file__).parent.parent / ".beads" / "issues.jsonl"

# Beads to mark as wontfix (cut from roadmap)
CUT_BEADS = {
    # Compliance & Governance epic (trellis-gmi) - different customer segment
    "trellis-gmi": "Out of scope: Compliance is different customer segment",
    "trellis-1ne": "Out of scope: SOC2 compliance not core reliability",
    "trellis-zeb": "Out of scope: GDPR not core reliability",
    "trellis-e3n": "Out of scope: OPA/Sentinel policies not core",
    "trellis-1tr": "Out of scope: Data retention not core reliability",
    "trellis-115": "Out of scope: Backup/DR not core reliability",
    
    # Cost Management epic (trellis-3um) - FinOps is its own discipline
    "trellis-3um": "Out of scope: FinOps is separate discipline (use OpenCost)",
    "trellis-836": "Out of scope: Cost tagging is FinOps",
    "trellis-9k6": "Out of scope: Budget alerts is FinOps",
    "trellis-nw3": "Out of scope: Auto-scaling is infra, not observability",
    "trellis-65h": "Out of scope: Resource quotas is infra",
    
    # Access Control & Security epic (trellis-yv6) - IAM/RBAC is infrastructure
    "trellis-yv6": "Out of scope: IAM/RBAC is infrastructure, not observability",
    "trellis-oi0": "Out of scope: AWS IAM is infrastructure",
    "trellis-102": "Out of scope: K8s RBAC is infrastructure",
    "trellis-xy3": "Out of scope: Vault integration covered by secrets config",
    "trellis-bpn": "Out of scope: Network policies is infrastructure",
    "trellis-kxt": "Out of scope: API gateway is infrastructure",
    "trellis-9mo": "Out of scope: Database permissions is infrastructure",
    "trellis-nm3": "Out of scope: Audit logging is infrastructure",
    
    # Incident Management (trellis-411) - PagerDuty already does this
    "trellis-dr5": "Out of scope: Slack war rooms - use incident.io/PagerDuty",
    "trellis-yw3": "Out of scope: Incident roles - PagerDuty handles this",
    "trellis-7jw": "Out of scope: Post-incident automation - use incident.io",
    
    # Observability Expansion - cut non-template items
    "trellis-6h9": "Out of scope: APM/tracing config - use OTel directly",
    "trellis-1kc": "Out of scope: Synthetic monitoring - use Datadog/Pingdom",
    "trellis-c5v": "Out of scope: Log aggregation - use Datadog/Loki",
    "trellis-mwq": "Out of scope: Continuous profiling - use Pyroscope",
    "trellis-6ue": "Out of scope: ML anomaly detection adds complexity",
    
    # Deployment Gates - trim
    "trellis-t2h": "Out of scope: GitLab CI - focus on GitHub Actions",
    "trellis-9ug": "Out of scope: Progressive delivery - Argo Rollouts does this",
    
    # Documentation - trim
    "trellis-9nc": "Out of scope: Confluence/Notion integration adds complexity",
    "trellis-0a7": "Out of scope: Onboarding guides not core",
    
    # Recent integrations - cut
    "trellis-opsgenie": "Out of scope: Opsgenie EOL 2027, not worth investing",
    "trellis-cardinality": "Deferred: Nice-to-have, not core",
    "trellis-backstage": "Deferred: Distribution channel, not core product",
}

# Beads to defer (lower priority)
DEFER_BEADS = {
    "trellis-5ay": "Deferred: Slack notifications nice-to-have",
    "trellis-0gr": "Deferred: Reliability scorecard nice-to-have",
    "trellis-3ap": "Deferred: Audit logging can be simplified",
    "trellis-ca5": "Deferred: GitHub Actions generation nice-to-have",
    "trellis-cok": "Deferred: Service docs templates nice-to-have",
    "trellis-t95": "Deferred: Dependency visualization nice-to-have",
    "trellis-ys8": "Deferred: RabbitMQ template lower priority",
    "trellis-4dw": "Deferred: PagerDuty schedules from Backstage",
    "trellis-incidentio": "Deferred: One incident platform (PagerDuty) is enough for now",
}

# Core beads - ensure priority 0
CORE_BEADS = [
    # Phase 4: Error Budget Foundation
    "trellis-3h6",  # Epic
    "trellis-z6x",  # OpenSLO parser
    "trellis-ygb",  # Error budget calculator
    "trellis-b54",  # Time-series storage
    "trellis-z2b",  # Deploy correlation
    "trellis-yb5",  # ArgoCD detection
    "trellis-0cp",  # Prometheus SLI integration
    
    # Phase 5: Intelligent Alerts (core only)
    "trellis-tt3",  # Epic
    "trellis-4tu",  # Threshold alerts
    "trellis-9ri",  # Template explanations
    
    # Phase 6: Deployment Gates (core only)
    "trellis-3e6",  # Epic
    "trellis-tnr",  # Policy YAML DSL
    "trellis-a4d",  # Condition evaluator
    "trellis-0fl",  # ArgoCD blocking
    
    # Phase 7: Runbooks (core only)
    "trellis-l40",  # Epic
    "trellis-cpx",  # Runbook from metadata
    "trellis-meh",  # Auto-generation
]

# Templates to keep
KEEP_TEMPLATES = [
    "trellis-0cd",  # Kafka
    "trellis-e8w",  # MongoDB
    "trellis-uum",  # Elasticsearch
]


def load_beads():
    """Load all beads from JSONL file."""
    beads = []
    with open(BEADS_FILE) as f:
        for line in f:
            if line.strip():
                beads.append(json.loads(line))
    return beads


def save_beads(beads):
    """Save beads back to JSONL file."""
    with open(BEADS_FILE, "w") as f:
        for bead in beads:
            f.write(json.dumps(bead) + "\n")


def update_beads():
    """Update beads based on pruned roadmap."""
    beads = load_beads()
    now = datetime.utcnow().isoformat() + "Z"
    
    stats = {"cut": 0, "deferred": 0, "prioritized": 0}
    
    for bead in beads:
        bead_id = bead["id"]
        
        # Skip already closed beads
        if bead.get("status") == "closed":
            continue
        
        # Mark cut beads as wontfix
        if bead_id in CUT_BEADS:
            bead["status"] = "closed"
            bead["closed_at"] = now
            bead["close_reason"] = CUT_BEADS[bead_id]
            stats["cut"] += 1
            print(f"CUT: {bead_id} - {bead['title'][:50]}")
        
        # Mark deferred beads
        elif bead_id in DEFER_BEADS:
            bead["priority"] = 3  # Low priority
            bead["status"] = "open"
            if "comments" not in bead:
                bead["comments"] = []
            bead["comments"].append({
                "id": len(bead.get("comments", [])) + 1,
                "issue_id": bead_id,
                "author": "roadmap-prune",
                "text": DEFER_BEADS[bead_id],
                "created_at": now,
            })
            stats["deferred"] += 1
            print(f"DEFER: {bead_id} - {bead['title'][:50]}")
        
        # Prioritize core beads
        elif bead_id in CORE_BEADS:
            bead["priority"] = 0  # Highest priority
            stats["prioritized"] += 1
            print(f"CORE: {bead_id} - {bead['title'][:50]}")
        
        # Keep templates at medium priority
        elif bead_id in KEEP_TEMPLATES:
            bead["priority"] = 2
            print(f"KEEP: {bead_id} - {bead['title'][:50]}")
    
    save_beads(beads)
    
    print(f"\n=== Summary ===")
    print(f"Cut (wontfix): {stats['cut']}")
    print(f"Deferred: {stats['deferred']}")
    print(f"Core (prioritized): {stats['prioritized']}")
    print(f"Total beads: {len(beads)}")


if __name__ == "__main__":
    update_beads()
