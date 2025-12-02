#!/bin/bash
#
# NthLayer Roadmap Migration to Beads (v2 - Revised)
# 
# This script migrates roadmap items to beads with:
# - Historical Epic 0 (Foundation) - CLOSED
# - Removes duplicate features (PostgreSQL/Redis/Kubernetes templates already exist)
# - Links existing live demo issues
# - Only tracks future work as open issues
#
# Usage: ./migrate_roadmap_to_beads_v2.sh
#

set -e  # Exit on error

BD=~/go/bin/bd
cd /Users/robfox/trellis

echo "🚀 Starting NthLayer Roadmap Migration to Beads (v2)"
echo "==================================================="
echo ""
echo "Changes from v1:"
echo "  ✅ Added Epic 0 (Foundation) - closed"
echo "  ✅ Removed 7 duplicate features"
echo "  ✅ Links existing demo issues"
echo "  ✅ Accurate 40% completion from day 1"
echo ""

#
# PART 1: Create Historical Foundation Epic (CLOSED)
#
echo "📚 Part 1: Creating Foundation Epic (Historical Work)"
echo "======================================================="

$BD create "Foundation & MVP Development (Weeks 1-8)" --type epic --priority P0 \
  -d "Core NthLayer platform completed Nov 14 - Dec 26, 2025. Includes: CLI framework, alert generation, SLO management, technology templates (PostgreSQL/Redis/Kubernetes), dashboard generation (40 panels), recording rules (21+), unified workflow (plan/apply), live demo infrastructure. 84/84 tests passing. See FOUNDATION_COMPLETE.md and archive/*_COMPLETE.md"

FOUNDATION_ID=$($BD list --title "Foundation & MVP" --json | jq -r '.[0].id')
echo "Created: $FOUNDATION_ID - Foundation & MVP Development"

# Close it immediately
$BD close "$FOUNDATION_ID" --reason "Completed December 26, 2025. Foundation work done: 15,000 lines code, 84 tests passing, 4 templates, unified workflow, live demo. See FOUNDATION_COMPLETE.md"
echo "✅ Closed foundation epic"
echo ""

# Create summary child features (all closed)
echo "Creating foundation child features (summary)..."

$BD create "Core platform infrastructure" --type task --priority P0 --deps "$FOUNDATION_ID" \
  -d "CLI framework (demo.py 60KB), alerts module, SLOs module, PagerDuty integration, multi-env support, 84 tests passing"
CORE_ID=$($BD list --title "Core platform infrastructure" --json | jq -r '.[0].id')
$BD close "$CORE_ID" --reason "Complete: 5 modules, 84/84 tests, multi-env support"

$BD create "Technology templates (PostgreSQL, Redis, Kubernetes)" --type feature --priority P0 --deps "$FOUNDATION_ID" \
  -d "PostgreSQL: 14 alerts + 12 panels. Redis: 8 alerts + 6 panels. Kubernetes: 10 alerts + 8 panels. Total: 40 production-grade panels"
TEMPLATES_ID=$($BD list --title "Technology templates" --json | jq -r '.[0].id')
$BD close "$TEMPLATES_ID" --reason "Complete: 3 templates, 40 panels. See dashboards/templates/"

$BD create "Dashboard generation & recording rules" --type feature --priority P0 --deps "$FOUNDATION_ID" \
  -d "DashboardBuilder with full/overview modes. 21+ recording rules for performance. See PHASE3D_COMPLETE.md"
DASH_ID=$($BD list --title "Dashboard generation" --json | jq -r '.[0].id')
$BD close "$DASH_ID" --reason "Complete: dashboards/builder.py, recording_rules/builder.py, full/overview modes"

$BD create "Unified workflow (plan/apply)" --type feature --priority P0 --deps "$FOUNDATION_ID" \
  -d "ServiceOrchestrator, plan command, apply command. 86% command reduction (7→1). Terraform-style workflow"
UNIFIED_ID=$($BD list --title "Unified workflow" --json | jq -r '.[0].id')
$BD close "$UNIFIED_ID" --reason "Complete: orchestrator.py 450 lines, plan/apply commands. See UNIFIED_APPLY_COMPLETE.md"

$BD create "Live demo infrastructure" --type feature --priority P0 --deps "$FOUNDATION_ID" \
  -d "Fly.io app (374 lines), GitHub Pages site, zero-cost guide (664 lines), low-cost guide (836 lines)"
DEMO_ID=$($BD list --title "Live demo infrastructure" --json | jq -r '.[0].id')
$BD close "$DEMO_ID" --reason "Complete: 12 files, app.py, docs site. See demo/DEMO_COMPLETE.md"

echo "✅ Created and closed 5 foundation features"
echo ""

#
# PART 2: Link Existing Live Demo Issues
#
echo "🔗 Part 2: Linking Existing Live Demo Issues"
echo "=============================================="
echo "Note: Existing issues use 'trellis-' prefix (created before config update)"
echo "      New issues will use 'nthlayer-' prefix"
echo ""

# These issues already exist from earlier beads work
# We'll link them to Epic 10 after it's created
echo "Existing issues to link:"
echo "  - trellis-948: Configure Grafana Cloud (in progress)"
echo "  - trellis-oh2: Import dashboard (blocked)"
echo "  - trellis-tl4: Enable GitHub Pages (blocked)"
echo "  - trellis-4f7: Update URLs (blocked)"
echo "(Will be linked to Epic 10 after creation)"
echo ""

#
# PART 3: Create Future Work Epics (1-10)
#
echo "📋 Part 3: Creating Future Work Epics"
echo "======================================"

#
# EPIC 1: Observability Suite Expansion (REVISED - 10 features, 3 removed)
#
echo ""
echo "📊 Creating Epic 1: Observability Suite Expansion (10 features)"
$BD create "Observability Suite Expansion" --type epic --priority P1 \
  -d "Expand monitoring beyond existing PostgreSQL/Redis/Kubernetes templates. Add: SLO/SLI tracking, Kafka, Elasticsearch, MongoDB, RabbitMQ, APM/tracing, synthetic monitoring, log aggregation, anomaly detection, continuous profiling. Note: PostgreSQL/Redis/Kubernetes templates already implemented."

EPIC1_ID=$($BD list --title "Observability Suite Expansion" --json | jq -r '.[0].id')

$BD create "Implement SLO/SLI generation and tracking" --type feature --priority P1 --deps "$EPIC1_ID" \
  -d "Auto-generate SLOs based on service tier. Tier-1: 99.95% availability, p99<200ms. Integration with Datadog SLOs, Grafana SLOs. Error budget tracking UI. Real-time burn rate calculation."

$BD create "Add Kafka technology template" --type feature --priority P2 --deps "$EPIC1_ID" \
  -d "Consumer lag, partition health, broker metrics, replication status, under-replicated partitions. Alerts + dashboard panels."

$BD create "Add Elasticsearch technology template" --type feature --priority P2 --deps "$EPIC1_ID" \
  -d "Cluster health (red/yellow/green), search performance, indexing rates, JVM heap, disk usage. Alerts + dashboard panels."

$BD create "Add MongoDB technology template" --type feature --priority P2 --deps "$EPIC1_ID" \
  -d "Connection pool utilization, replication lag, query performance, lock percentage, WiredTiger cache. Alerts + dashboard panels."

$BD create "Add RabbitMQ technology template" --type feature --priority P3 --deps "$EPIC1_ID" \
  -d "Queue depth, consumer count, message rates, connection health, memory alarms, disk space. Alerts + dashboard panels."

$BD create "Implement anomaly detection alerts" --type feature --priority P2 --deps "$EPIC1_ID" \
  -d "ML-based anomaly detection for latency, error rates, traffic patterns. Auto-tune thresholds based on historical data. Integration with Datadog AI."

$BD create "Add APM/tracing configuration" --type feature --priority P2 --deps "$EPIC1_ID" \
  -d "Generate Datadog APM service configs, New Relic setup, OpenTelemetry collector configs. Sampling rates based on tier (tier-1: 100%, tier-2: 50%, tier-3: 10%)."

$BD create "Implement synthetic monitoring setup" --type feature --priority P2 --deps "$EPIC1_ID" \
  -d "Datadog Synthetics, Pingdom uptime checks, geographic probe distribution. Check frequency based on tier (tier-1: 1min, tier-2: 5min, tier-3: 15min)."

$BD create "Add log aggregation configuration" --type feature --priority P2 --deps "$EPIC1_ID" \
  -d "Datadog log pipelines (parsing rules, indexes), CloudWatch log groups, retention policies. Tier-based retention (tier-1: 1yr, tier-3: 30d)."

$BD create "Implement continuous profiling setup" --type feature --priority P3 --deps "$EPIC1_ID" \
  -d "Datadog continuous profiling, Pyroscope configs. Sampling rates based on traffic volume. CPU/memory flame graphs."

echo "✅ Epic 1 complete: Observability Suite Expansion (10 features, PostgreSQL/Redis/Kubernetes skipped - already done)"

#
# EPIC 2: Error Budget Foundation (8 features - unchanged)
#
echo ""
echo "💰 Creating Epic 2: Error Budget Foundation (8 features)"
$BD create "Error Budget Foundation" --type epic --priority P1 \
  -d "Core error budget tracking, calculation, deployment correlation. Prove value: 'This deploy burned 8h of error budget.' OpenSLO integration, Prometheus metrics, ArgoCD webhooks."

EPIC2_ID=$($BD list --title "Error Budget Foundation" --json | jq -r '.[0].id')

$BD create "Implement OpenSLO parser and validator" --type task --priority P0 --deps "$EPIC2_ID" \
  -d "Load SLO definitions from YAML files, validate against OpenSLO spec (v1alpha), store in database. Support time-slicing and occurrence-based SLOs."

SLO_PARSER_ID=$($BD list --title "OpenSLO parser" --json | jq -r '.[0].id')

$BD create "Build Prometheus integration for SLI metrics" --type task --priority P0 --deps "$EPIC2_ID,$SLO_PARSER_ID" \
  -d "Query SLI metrics (latency histograms, error counters, availability), calculate compliance vs target, detect SLO breaches. Support PromQL for custom queries."

PROM_ID=$($BD list --title "Prometheus integration for SLI" --json | jq -r '.[0].id')

$BD create "Implement error budget calculator" --type task --priority P0 --deps "$EPIC2_ID,$PROM_ID" \
  -d "Time-based 30d rolling windows, calculate burn rate (current vs baseline), track remaining budget as percentage. Support multiple SLO types (availability, latency, error rate)."

CALC_ID=$($BD list --title "error budget calculator" --json | jq -r '.[0].id')

$BD create "Create time-series storage for budget tracking" --type task --priority P0 --deps "$EPIC2_ID,$CALC_ID" \
  -d "Postgres tables for error budget history, time-series queries (trend analysis), retention policies. Support querying by service, SLO type, time range."

$BD create "Implement deployment detection via ArgoCD" --type task --priority P1 --deps "$EPIC2_ID" \
  -d "ArgoCD webhook listener, capture deploy metadata (commit SHA, author, timestamp, diff), store deployment events. Support GitHub Actions/GitLab CI detection."

DEPLOY_DETECT_ID=$($BD list --title "deployment detection" --json | jq -r '.[0].id')

$BD create "Build deploy → burn correlation engine" --type task --priority P1 --deps "$EPIC2_ID,$CALC_ID,$DEPLOY_DETECT_ID" \
  -d "Time-window matching (deploy timestamp → SLO breach within 15min), confidence scoring (likelihood 0-100%), root cause suggestions based on patterns."

$BD create "Implement PagerDuty incident attribution" --type task --priority P1 --deps "$EPIC2_ID,$CALC_ID" \
  -d "Link PagerDuty incidents to services, calculate incident duration → budget burn (minutes lost), track MTTR impact on error budget."

$BD create "Add CLI commands for error budget" --type task --priority P1 --deps "$EPIC2_ID,$CALC_ID" \
  -d "nthlayer show error-budget <service>, nthlayer correlate deployments <service> --last 7d, nthlayer list incidents --budget-impact"

echo "✅ Epic 2 complete: Error Budget Foundation (8 features)"

#
# EPIC 3: Intelligent Alerts & Scorecard (6 features - unchanged)
#
echo ""
echo "🚨 Creating Epic 3: Intelligent Alerts & Scorecard (6 features)"
$BD create "Intelligent Alerts & Scorecard" --type epic --priority P1 \
  -d "Proactive alerting based on error budget consumption. Reliability scorecard (0-100 score). 'You're at 75% budget, consider freeze.' Template-based explanations."

EPIC3_ID=$($BD list --title "Intelligent Alerts" --json | jq -r '.[0].id')

$BD create "Build alert engine with threshold-based rules" --type task --priority P1 --deps "$EPIC3_ID,$CALC_ID" \
  -d "Budget thresholds (75%, 85%, 95%), burn rate anomalies (2x baseline), incident frequency triggers. Support custom thresholds per tier."

$BD create "Implement Slack rich notifications" --type task --priority P1 --deps "$EPIC3_ID" \
  -d "Rich formatting (cards, colors, graphs), @mention service owners, threaded context with error budget details, charts."

$BD create "Add PagerDuty incident creation from alerts" --type task --priority P1 --deps "$EPIC3_ID" \
  -d "Auto-create PagerDuty incidents for critical burns (>95%), link to error budget dashboard, assign to on-call, escalate if not acked."

$BD create "Implement template-based explanations" --type task --priority P1 --deps "$EPIC3_ID,$CALC_ID" \
  -d "'Burned because: [incident X: 8h, deploy Y: 2h, SLO breach Z: 3h]', top 3 causes with percentages, recommended actions (rollback, freeze, scale)."

$BD create "Build reliability scorecard calculator" --type task --priority P1 --deps "$EPIC3_ID,$CALC_ID" \
  -d "Per-service scores (0-100): SLO compliance (40%), incident count (30%), deploy success rate (20%), error budget remaining (10%). Team aggregation, 30d/90d trends."

SCORECARD_ID=$($BD list --title "reliability scorecard" --json | jq -r '.[0].id')

$BD create "Implement email summary automation" --type task --priority P2 --deps "$EPIC3_ID,$SCORECARD_ID" \
  -d "Weekly digest per service owner (scorecard, budget status, incidents), monthly executive summary (team aggregation, trends), HTML email templates."

echo "✅ Epic 3 complete: Intelligent Alerts & Scorecard (6 features)"

#
# EPIC 4: Deployment Policies & Gates (7 features, 1 removed)
#
echo ""
echo "🚪 Creating Epic 4: Deployment Policies & Gates (7 features)"
echo "Note: Unified apply command already exists (orchestrator.py), skipping duplicate"

$BD create "Deployment Policies & Gates" --type epic --priority P2 \
  -d "Automated deployment guardrails, policy enforcement, CI/CD generation. 'Deploy blocked, 90% budget consumed.' Policy YAML DSL, ArgoCD integration, progressive delivery."

EPIC4_ID=$($BD list --title "Deployment Policies" --json | jq -r '.[0].id')

$BD create "Design and implement Policy YAML DSL" --type task --priority P1 --deps "$EPIC4_ID" \
  -d "Simple DSL for conditions (budget < X%, tier = Y, time_window = business_hours), tier-based selectors, action types (block, notify, create_incident, require_approval)."

POLICY_DSL_ID=$($BD list --title "Policy YAML DSL" --json | jq -r '.[0].id')

$BD create "Build condition evaluator engine" --type task --priority P1 --deps "$EPIC4_ID,$POLICY_DSL_ID,$CALC_ID" \
  -d "Budget percentage checks, tier matching, time window evaluations (business_hours, weekends), dependency health checks. Boolean logic (AND/OR)."

$BD create "Implement ArgoCD deployment blocking" --type task --priority P1 --deps "$EPIC4_ID,$CALC_ID" \
  -d "Pause auto-sync API (kubectl patch), resume on approval (manual or automated), override mechanism (emergency deploys), audit logging of all actions."

$BD create "Generate GitHub Actions workflows" --type feature --priority P2 --deps "$EPIC4_ID,$POLICY_DSL_ID" \
  -d "Auto-generate CI/CD pipelines with tier-appropriate testing (tier-1: security scans, load tests, canary), approval gates, nthlayer policy check integration."

$BD create "Generate GitLab CI pipelines" --type feature --priority P3 --deps "$EPIC4_ID,$POLICY_DSL_ID" \
  -d "GitLab CI/CD pipeline generation (.gitlab-ci.yml) with testing, deployment stages, policy checks as manual jobs."

$BD create "Implement progressive delivery configs" --type feature --priority P2 --deps "$EPIC4_ID" \
  -d "Canary rollout percentages (10%, 50%, 100%), blue/green strategies, traffic splitting rules (Istio VirtualService, Linkerd), automatic rollback on errors."

$BD create "Add deployment notification system" --type task --priority P2 --deps "$EPIC4_ID" \
  -d "Slack deployment announcements (#deployments channel), Statuspage.io updates (scheduled maintenance), internal changelog generation (CHANGELOG.md auto-update)."

$BD create "Build audit logging for policies" --type task --priority P2 --deps "$EPIC4_ID,$POLICY_DSL_ID" \
  -d "Who did what when (user, action, timestamp), policy violations (which policy, reason), overrides and approvals, immutable audit trail."

echo "✅ Epic 4 complete: Deployment Policies & Gates (7 features, unified apply skipped)"

#
# EPIC 5-9: Unchanged (all features, no duplicates)
#
echo ""
echo "🔥 Creating Epic 5: Incident Management Expansion (5 features)"
$BD create "Incident Management Expansion" --type epic --priority P2 \
  -d "Complete incident lifecycle: on-call schedules, war rooms, postmortems, runbooks. PagerDuty schedule generation, Slack war room automation, Jira postmortem creation."

EPIC5_ID=$($BD list --title "Incident Management Expansion" --json | jq -r '.[0].id')

$BD create "Generate PagerDuty on-call schedules" --type feature --priority P1 --deps "$EPIC5_ID" \
  -d "Auto-generate from team membership (Backstage/Cortex), respect time zones, follow-the-sun patterns (rotate by region), weekend/holiday coverage rules."

$BD create "Implement incident response role assignment" --type feature --priority P2 --deps "$EPIC5_ID" \
  -d "Define roles per-tier (tier-1: Commander + Comms Lead, tier-2: single responder), map to team members with training badges, automatic assignment on page."

$BD create "Build war room automation" --type feature --priority P2 --deps "$EPIC5_ID" \
  -d "Slack incident channels (#incident-YYYY-MM-DD-service, auto-create on page), Zoom/MS Teams bridge creation, Confluence incident page template, invite relevant people."

$BD create "Implement post-incident automation" --type feature --priority P2 --deps "$EPIC5_ID" \
  -d "Auto-create Jira/Linear incident tickets (P0 label), postmortem template generation (5 Whys, timeline, action items), action item tracking (Jira/Linear issues)."

$BD create "Generate runbook content from service metadata" --type feature --priority P1 --deps "$EPIC5_ID" \
  -d "Auto-generate runbooks (Markdown/Confluence), common troubleshooting steps per tier, dependency diagrams (service mesh topology), emergency contacts (on-call schedule link)."

echo "✅ Epic 5 complete: Incident Management Expansion (5 features)"

echo ""
echo "🔒 Creating Epic 6: Access Control & Security (7 features)"
$BD create "Access Control & Security" --type epic --priority P2 \
  -d "Automated RBAC, secrets management, network policies, audit logging. Least-privilege IAM roles, Vault integration, Kubernetes network policies."

EPIC6_ID=$($BD list --title "Access Control" --json | jq -r '.[0].id')

$BD create "Generate AWS IAM roles for services" --type feature --priority P1 --deps "$EPIC6_ID" \
  -d "Auto-provision least-privilege IAM roles (based on dependencies: S3, DynamoDB, SQS), policy templates, service account mapping (EKS IRSA)."

$BD create "Generate Kubernetes RBAC policies" --type feature --priority P1 --deps "$EPIC6_ID" \
  -d "ServiceAccount, Role, RoleBinding generation. Minimal access patterns based on tier (tier-1: read-only ConfigMaps, tier-2: read-write own namespace)."

$BD create "Implement database permission management" --type feature --priority P2 --deps "$EPIC6_ID" \
  -d "Auto-create database users (read-only for dashboards, read-write for app), grant appropriate permissions (PostgreSQL GRANT, MySQL GRANT), rotation policies (90 days)."

$BD create "Integrate Vault secrets management" --type feature --priority P2 --deps "$EPIC6_ID" \
  -d "Vault path setup (/platform/<service>), policy generation (read-only for service, read-write for CI/CD), secret rotation automation (90 days), dynamic secrets."

$BD create "Generate API gateway configurations" --type feature --priority P2 --deps "$EPIC6_ID" \
  -d "Rate limiting per tier (tier-1: 10000 req/min, tier-3: 100 req/min), authentication requirements (JWT, API key), CORS policies, IP allowlists/denylists."

$BD create "Implement network policy generation" --type feature --priority P2 --deps "$EPIC6_ID" \
  -d "Kubernetes NetworkPolicies (default deny, allow by label), AWS Security Groups (ingress/egress rules), service mesh authorization (Istio AuthorizationPolicy)."

$BD create "Configure audit logging" --type task --priority P2 --deps "$EPIC6_ID" \
  -d "CloudTrail rules for service API calls, Kubernetes audit policies (metadata level), database audit logging (pg_audit, MySQL audit plugin)."

echo "✅ Epic 6 complete: Access Control & Security (7 features)"

echo ""
echo "💵 Creating Epic 7: Cost Management (4 features)"
$BD create "Cost Management" --type epic --priority P3 \
  -d "Cost tracking, budgets, auto-scaling, resource quotas. AWS resource tagging, budget alerts, Kubernetes HPA, cost anomaly detection."

EPIC7_ID=$($BD list --title "Cost Management" --json | jq -r '.[0].id')

$BD create "Implement cost allocation tagging" --type feature --priority P2 --deps "$EPIC7_ID" \
  -d "AWS resource tagging (Team, Service, Environment, Tier, Owner), GCP labels, Azure tags. Consistent taxonomy enforcement. Terraform tag propagation."

TAG_ID=$($BD list --title "cost allocation tagging" --json | jq -r '.[0].id')

$BD create "Generate budget alerts and tracking" --type feature --priority P2 --deps "$EPIC7_ID,$TAG_ID" \
  -d "AWS Budgets per service/team (based on tags), alert thresholds based on historical spend (80%, 100%, 120%), cost anomaly detection (>20% change)."

$BD create "Implement auto-scaling policies" --type feature --priority P2 --deps "$EPIC7_ID" \
  -d "Kubernetes HPA (target CPU 70%, memory 80%), AWS Auto Scaling Groups, min/max replicas based on tier (tier-1: min 3, tier-3: min 1), schedule-based scaling."

$BD create "Configure resource quotas" --type feature --priority P3 --deps "$EPIC7_ID" \
  -d "Kubernetes ResourceQuota per namespace (CPU limits, memory limits, pod count), LimitRange (default/max per container), storage quotas (PVC size limits)."

echo "✅ Epic 7 complete: Cost Management (4 features)"

echo ""
echo "📚 Creating Epic 8: Documentation & Knowledge (5 features)"
$BD create "Documentation & Knowledge" --type epic --priority P2 \
  -d "Auto-generated runbooks, service docs, onboarding guides, dependency graphs. Confluence/Notion integration, README templates, architecture diagrams."

EPIC8_ID=$($BD list --title "Documentation" --json | jq -r '.[0].id')

$BD create "Implement runbook auto-generation" --type feature --priority P1 --deps "$EPIC8_ID" \
  -d "Generate from service metadata (Backstage/Cortex), common troubleshooting (restart pods, check logs, scale up), dependency diagrams (Mermaid.js), emergency contacts (PagerDuty link)."

$BD create "Generate service documentation templates" --type feature --priority P2 --deps "$EPIC8_ID" \
  -d "README templates (## Architecture, ## APIs, ## Deployment), ADR (Architecture Decision Record) scaffolding, API documentation (OpenAPI/Swagger from code)."

$BD create "Create onboarding guide generation" --type feature --priority P2 --deps "$EPIC8_ID" \
  -d "New team member checklists (setup dev env, run tests, deploy to staging), service ownership handoff docs, access request procedures (AWS, databases, Vault)."

$BD create "Build dependency graph visualization" --type feature --priority P2 --deps "$EPIC8_ID" \
  -d "Service mesh topology (Kiali/Jaeger integration), database dependency maps (ER diagrams), external API dependencies, blast radius visualization (if X fails, Y and Z affected)."

$BD create "Integrate with Confluence/Notion" --type feature --priority P2 --deps "$EPIC8_ID" \
  -d "Auto-publish documentation to Confluence or Notion (API integration), keep in sync with Git sources (CI/CD job), organize by service hierarchy."

echo "✅ Epic 8 complete: Documentation & Knowledge (5 features)"

echo ""
echo "📋 Creating Epic 9: Compliance & Governance (5 features)"
$BD create "Compliance & Governance" --type epic --priority P3 \
  -d "Policy-as-code for SOC2/GDPR/HIPAA, backup/DR, data retention. OPA policies, AWS Config rules, compliance evidence generation."

EPIC9_ID=$($BD list --title "Compliance" --json | jq -r '.[0].id')

$BD create "Implement SOC2 control mappings" --type feature --priority P3 --deps "$EPIC9_ID" \
  -d "Map NthLayer configs to SOC2 controls (CC6.1 = logical access, CC7.2 = change management), auto-generate compliance evidence (audit logs, RBAC configs), annual audit reports."

$BD create "Add GDPR data handling configurations" --type feature --priority P3 --deps "$EPIC9_ID" \
  -d "Data retention policies (PII deletion after 30 days inactive), encryption requirements (at-rest AES-256, in-transit TLS 1.3), data subject access procedures (export user data API)."

$BD create "Configure backup and DR policies" --type feature --priority P2 --deps "$EPIC9_ID" \
  -d "Backup schedules based on tier (tier-1: hourly, tier-3: daily), RTO/RPO enforcement (tier-1: RTO=1hr/RPO=15min), multi-region failover (Route53 health checks), disaster recovery runbooks."

$BD create "Implement data retention policy automation" --type feature --priority P3 --deps "$EPIC9_ID" \
  -d "Log retention tier-based (tier-1: 1yr, tier-3: 30d), database backup retention (tier-1: 90d, tier-3: 7d), S3 lifecycle policies (archive to Glacier after 90d)."

$BD create "Generate OPA/Sentinel policies" --type feature --priority P3 --deps "$EPIC9_ID" \
  -d "Open Policy Agent policies (Rego), AWS Config rules (CloudFormation), Terraform Sentinel policies (deny if no tags), Kubernetes admission controllers (Gatekeeper)."

echo "✅ Epic 9 complete: Compliance & Governance (5 features)"

#
# EPIC 10: Strategic Positioning & Launch (6 features, 3 removed + link existing)
#
echo ""
echo "🚀 Creating Epic 10: Strategic Positioning & Launch (6 features + 4 existing)"
echo "Note: Live demo already complete (trellis-02u closed, trellis-948 in progress)"
echo "      Linking existing demo issues to this epic"

$BD create "Strategic Positioning & Launch" --type epic --priority P1 \
  -d "Demo infrastructure complete (see trellis-rpv, nthlayer-foundation epics). Focus: case studies, sales materials, pilot program, paid conversions, $10k-20k MRR target."

EPIC10_ID=$($BD list --title "Strategic Positioning" --json | jq -r '.[0].id')

# Link existing live demo issues (use trellis- prefix as they were created before config update)
echo "Linking existing demo issues to Epic 10..."
$BD dep add trellis-948 "$EPIC10_ID"  # Grafana Cloud config (in progress)
$BD dep add trellis-oh2 "$EPIC10_ID"  # Import dashboard (blocked)
$BD dep add trellis-tl4 "$EPIC10_ID"  # GitHub Pages (blocked)
$BD dep add trellis-4f7 "$EPIC10_ID"  # Update URLs (blocked)
echo "✅ Linked 4 existing demo issues"

# Create new features (no demo deployment duplicates)
$BD create "Develop 3-5 customer case studies" --type task --priority P1 --deps "$EPIC10_ID" \
  -d "Document pilot customer results: time/cost savings, ROI calculations ($X saved/month), before/after metrics, testimonials. Publish on website and blog."

$BD create "Create sales materials and pitch deck" --type task --priority P1 --deps "$EPIC10_ID" \
  -d "Value proposition slides (99.6% time savings), competitive analysis (vs manual, vs Nobl9), pricing justification (ROI 22x), demo script (15min walkthrough)."

$BD create "Execute pilot program (5-8 customers)" --type task --priority P0 --deps "$EPIC10_ID" \
  -d "Recruit 5-8 pilot customers, free for 3 months, weekly feedback sessions (30min/week), gather requirements, iterate based on feedback. Target: 3-5 letters of intent by end."

PILOT_ID=$($BD list --title "Execute pilot program" --json | jq -r '.[0].id')

$BD create "Convert pilots to paid customers" --type task --priority P0 --deps "$EPIC10_ID,$PILOT_ID" \
  -d "Convert 2-3 pilots to paid contracts ($2k-5k/month each). Pricing tiers: Starter $2k, Professional $5k. Target: $6k-15k MRR. Close by end of 3-month pilot."

$BD create "Launch pricing page and public site" --type task --priority P1 --deps "$EPIC10_ID" \
  -d "Productize onboarding (self-service signup), create pricing page (3 tiers with feature comparison), payment integration (Stripe), customer portal."

$BD create "Scale to $10k-20k MRR" --type task --priority P0 --deps "$EPIC10_ID" \
  -d "Outbound sales (20-30 outreach/week), content marketing (blog posts, case studies), demos (3-5/week), close 5-8 customers total. Target: $10k-20k MRR by month 12."

$BD create "Conduct customer validation interviews" --type task --priority P0 --deps "$EPIC10_ID" \
  -d "Interview 20 SRE teams about error budget pain, validate willingness to pay ($5k/month for automation), secure 3-5 letters of intent BEFORE building Phase 4 (error budgets)."

$BD create "Define product roadmap priorities" --type task --priority P1 --deps "$EPIC10_ID,$PILOT_ID" \
  -d "Based on pilot feedback, prioritize Epic 2-9 features. Document decisions in beads (update priorities). Monthly roadmap reviews with paying customers."

echo "✅ Epic 10 complete: Strategic Positioning & Launch (6 new + 4 linked = 10 total)"

#
# Summary
#
echo ""
echo "=================================================="
echo "✅ Migration Complete!"
echo "=================================================="
echo ""
echo "Summary:"
echo "  - 1 Historical Epic (Foundation) [CLOSED]"
echo "    └─ 5 child features [CLOSED]"
echo "  - 10 Future Work Epics [OPEN]"
echo "    ├─ Epic 1: Observability (10 features)"
echo "    ├─ Epic 2: Error Budgets (8 features)"
echo "    ├─ Epic 3: Alerts/Scorecard (6 features)"
echo "    ├─ Epic 4: Deployment Policies (7 features)"
echo "    ├─ Epic 5: Incident Mgmt (5 features)"
echo "    ├─ Epic 6: Access Control (7 features)"
echo "    ├─ Epic 7: Cost Mgmt (4 features)"
echo "    ├─ Epic 8: Documentation (5 features)"
echo "    ├─ Epic 9: Compliance (5 features)"
echo "    └─ Epic 10: Launch (6 new + 4 linked = 10 features)"
echo ""
echo "Total issues: ~77"
echo "  - 6 closed (foundation)"
echo "  - 71 open (60 new + 11 epics)"
echo ""
echo "Removed duplicates (already implemented):"
echo "  ❌ PostgreSQL template"
echo "  ❌ Redis template"
echo "  ❌ Kubernetes template"
echo "  ❌ Dashboard generation"
echo "  ❌ Recording rules"
echo "  ❌ Unified apply"
echo "  ❌ Live demo deployment"
echo ""
echo "Platform completion: 40% (foundation complete)"
echo ""
echo "Next steps:"
echo "  1. Review: bd list --type epic"
echo "  2. Check stats: bd stats"
echo "  3. See ready work: bd ready"
echo "  4. See blocked: bd blocked"
echo "  5. Validate: bd list --status closed (should show 6)"
echo ""
echo "Happy tracking with accurate roadmap! 🎉"
