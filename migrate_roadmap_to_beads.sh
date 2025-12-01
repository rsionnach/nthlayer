#!/bin/bash
#
# NthLayer Roadmap Migration to Beads
# 
# This script migrates all roadmap items from markdown files to beads
# for dependency-aware project tracking.
#
# Usage: ./migrate_roadmap_to_beads.sh
#

set -e  # Exit on error

BD=~/go/bin/bd
cd /Users/robfox/trellis

echo "🚀 Starting NthLayer Roadmap Migration to Beads"
echo "================================================"
echo ""

#
# EPIC 1: Observability Suite Expansion
#
echo "📊 Creating Epic 1: Observability Suite Expansion"
$BD create "Observability Suite Expansion" --type epic --priority P1 \
  -d "Expand monitoring capabilities: SLOs, technology templates, advanced alerting, APM, synthetic monitoring, log aggregation"

EPIC1_ID=$($ BD list --title "Observability Suite Expansion" --json | jq -r '.[0].id')

$BD create "Implement SLO/SLI generation and tracking" --type feature --priority P1 \
  -d "Auto-generate SLOs based on service tier. Tier-1: 99.95% availability, p99<200ms. Integrate with Datadog SLOs and Grafana." \
  --deps "$EPIC1_ID"

$BD create "Add Kafka technology template" --type feature --priority P2 \
  -d "Monitoring, alerts, and dashboard panels for Kafka. Consumer lag, partition health, broker metrics, replication status." \
  --deps "$EPIC1_ID"

$BD create "Add Elasticsearch technology template" --type feature --priority P2 \
  -d "Cluster health, search performance, indexing rates, JVM metrics, disk usage alerts." \
  --deps "$EPIC1_ID"

$BD create "Add MongoDB technology template" --type feature --priority P2 \
  -d "Connection pool, replication lag, query performance, lock percentage, WiredTiger cache." \
  --deps "$EPIC1_ID"

$BD create "Add RabbitMQ technology template" --type feature --priority P3 \
  -d "Queue depth, consumer count, message rates, connection health, memory alarms." \
  --deps "$EPIC1_ID"

$BD create "Implement anomaly detection alerts" --type feature --priority P2 \
  -d "ML-based anomaly detection for latency, error rates, traffic patterns. Auto-tune thresholds based on historical data." \
  --deps "$EPIC1_ID"

$BD create "Add APM/tracing configuration" --type feature --priority P2 \
  -d "Generate Datadog APM configs, OpenTelemetry collector setups, sampling rates based on tier." \
  --deps "$EPIC1_ID"

$BD create "Implement synthetic monitoring setup" --type feature --priority P2 \
  -d "Datadog Synthetics, Pingdom uptime checks. Geographic probes, check frequency based on tier." \
  --deps "$EPIC1_ID"

$BD create "Add log aggregation configuration" --type feature --priority P2 \
  -d "Datadog log pipelines, CloudWatch log groups, retention policies. Tier-based retention (tier-1=1yr, tier-3=30d)." \
  --deps "$EPIC1_ID"

$BD create "Implement continuous profiling setup" --type feature --priority P3 \
  -d "Datadog profiling, Pyroscope configs. Sampling rates based on traffic volume." \
  --deps "$EPIC1_ID"

echo "✅ Epic 1 complete: Observability Suite Expansion (10 features)"
echo ""

#
# EPIC 2: Error Budget Foundation
#
echo "💰 Creating Epic 2: Error Budget Foundation"
$BD create "Error Budget Foundation" --type epic --priority P1 \
  -d "Core error budget tracking, calculation, deployment correlation. Prove value: 'This deploy burned 8h of error budget.'"

EPIC2_ID=$($BD list --title "Error Budget Foundation" --json | jq -r '.[0].id')

$BD create "Implement OpenSLO parser and validator" --type task --priority P0 \
  -d "Load SLO definitions from YAML files, validate against OpenSLO spec, store in database." \
  --deps "$EPIC2_ID"

SLO_PARSER_ID=$($BD list --title "OpenSLO parser" --json | jq -r '.[0].id')

$BD create "Build Prometheus integration for SLI metrics" --type task --priority P0 \
  -d "Query SLI metrics (latency, errors, availability), calculate compliance vs target, detect SLO breaches." \
  --deps "$EPIC2_ID,$SLO_PARSER_ID"

PROM_ID=$($BD list --title "Prometheus integration" --json | jq -r '.[0].id')

$BD create "Implement error budget calculator" --type task --priority P0 \
  -d "Time-based 30d rolling windows, calculate burn rate (current vs baseline), track remaining budget." \
  --deps "$EPIC2_ID,$PROM_ID"

CALC_ID=$($BD list --title "error budget calculator" --json | jq -r '.[0].id')

$BD create "Create time-series storage for budget tracking" --type task --priority P0 \
  -d "Postgres tables for budget tracking, time-series queries (trend analysis), retention policies." \
  --deps "$EPIC2_ID,$CALC_ID"

$BD create "Implement deployment detection via ArgoCD" --type task --priority P1 \
  -d "ArgoCD webhook listener, capture deploy metadata (commit, author, timestamp), store deployment events." \
  --deps "$EPIC2_ID"

DEPLOY_DETECT_ID=$($BD list --title "deployment detection" --json | jq -r '.[0].id')

$BD create "Build deploy → burn correlation engine" --type task --priority P1 \
  -d "Time-window matching (deploy → SLO breach), confidence scoring (likelihood), root cause suggestions." \
  --deps "$EPIC2_ID,$CALC_ID,$DEPLOY_DETECT_ID"

$BD create "Implement PagerDuty incident attribution" --type task --priority P1 \
  -d "Link incidents to services, calculate incident duration → budget burn, track MTTR impact." \
  --deps "$EPIC2_ID,$CALC_ID"

$BD create "Add CLI commands for error budget" --type task --priority P1 \
  -d "nthlayer show error-budget <service>, nthlayer correlate deployments, nthlayer list incidents --budget-impact" \
  --deps "$EPIC2_ID,$CALC_ID"

echo "✅ Epic 2 complete: Error Budget Foundation (8 features)"
echo ""

#
# EPIC 3: Intelligent Alerts & Scorecard
#
echo "🚨 Creating Epic 3: Intelligent Alerts & Scorecard"
$BD create "Intelligent Alerts & Scorecard" --type epic --priority P1 \
  -d "Proactive alerting based on error budget consumption. Reliability scorecard. 'You're at 75% budget, consider freeze.'"

EPIC3_ID=$($BD list --title "Intelligent Alerts" --json | jq -r '.[0].id')

$BD create "Build alert engine with threshold-based rules" --type task --priority P1 \
  -d "Budget thresholds (75%, 85%, 95%), burn rate anomalies (2x baseline), incident frequency triggers." \
  --deps "$EPIC3_ID,$CALC_ID"

$BD create "Implement Slack rich notifications" --type task --priority P1 \
  -d "Rich formatting (cards, colors), @mention service owners, threaded context." \
  --deps "$EPIC3_ID"

$BD create "Add PagerDuty incident creation from alerts" --type task --priority P1 \
  -d "Auto-create incidents for critical burns, link to error budget details, assign to on-call." \
  --deps "$EPIC3_ID"

$BD create "Implement template-based explanations" --type task --priority P1 \
  -d "'Burned because: [incident/deploy/SLO breach]', top 3 causes with percentages, recommended actions." \
  --deps "$EPIC3_ID,$CALC_ID"

$BD create "Build reliability scorecard calculator" --type task --priority P1 \
  -d "Per-service scores (0-100), SLO compliance + incidents + deploys, team aggregation, trend calculations." \
  --deps "$EPIC3_ID,$CALC_ID"

SCORECARD_ID=$($BD list --title "reliability scorecard" --json | jq -r '.[0].id')

$BD create "Implement email summary automation" --type task --priority P2 \
  -d "Weekly digest per service owner, monthly executive summary, trend charts (text-based)." \
  --deps "$EPIC3_ID,$SCORECARD_ID"

echo "✅ Epic 3 complete: Intelligent Alerts & Scorecard (6 features)"
echo ""

#
# EPIC 4: Deployment Policies & Gates
#
echo "🚪 Creating Epic 4: Deployment Policies & Gates"
$BD create "Deployment Policies & Gates" --type epic --priority P2 \
  -d "Automated deployment guardrails, policy enforcement, CI/CD generation. 'Deploy blocked, 90% budget consumed.'"

EPIC4_ID=$($BD list --title "Deployment Policies" --json | jq -r '.[0].id')

$BD create "Design and implement Policy YAML DSL" --type task --priority P1 \
  -d "Simple DSL for conditions, tier-based selectors, action types (block, notify, create_incident)." \
  --deps "$EPIC4_ID"

POLICY_DSL_ID=$($BD list --title "Policy YAML DSL" --json | jq -r '.[0].id')

$BD create "Build condition evaluator engine" --type task --priority P1 \
  -d "Budget percentage checks, tier matching, time window evaluations." \
  --deps "$EPIC4_ID,$POLICY_DSL_ID,$CALC_ID"

$BD create "Implement ArgoCD deployment blocking" --type task --priority P1 \
  -d "Pause auto-sync API, resume on approval, override mechanism (manual)." \
  --deps "$EPIC4_ID,$CALC_ID"

$BD create "Generate GitHub Actions workflows" --type feature --priority P2 \
  -d "Auto-generate CI/CD pipelines with tier-appropriate testing, security scans, approval gates." \
  --deps "$EPIC4_ID,$POLICY_DSL_ID"

$BD create "Generate GitLab CI pipelines" --type feature --priority P3 \
  -d "GitLab CI/CD pipeline generation with testing, deployment stages, policy checks." \
  --deps "$EPIC4_ID,$POLICY_DSL_ID"

$BD create "Implement progressive delivery configs" --type feature --priority P2 \
  -d "Canary rollout percentages, blue/green strategies, traffic splitting rules (Istio, Linkerd)." \
  --deps "$EPIC4_ID"

$BD create "Add deployment notification system" --type task --priority P2 \
  -d "Slack announcements, status page updates (Statuspage.io), internal changelog generation." \
  --deps "$EPIC4_ID"

$BD create "Build audit logging for policies" --type task --priority P2 \
  -d "Who did what when, policy violations, overrides and approvals tracking." \
  --deps "$EPIC4_ID,$POLICY_DSL_ID"

echo "✅ Epic 4 complete: Deployment Policies & Gates (8 features)"
echo ""

#
# EPIC 5: Incident Management Expansion
#
echo "🔥 Creating Epic 5: Incident Management Expansion"
$BD create "Incident Management Expansion" --type epic --priority P2 \
  -d "Complete incident lifecycle: on-call schedules, war rooms, postmortems, runbooks."

EPIC5_ID=$($BD list --title "Incident Management Expansion" --json | jq -r '.[0].id')

$BD create "Generate PagerDuty on-call schedules" --type feature --priority P1 \
  -d "Auto-generate from team membership, respect time zones, follow-the-sun patterns, weekend/holiday coverage." \
  --deps "$EPIC5_ID"

$BD create "Implement incident response role assignment" --type feature --priority P2 \
  -d "Define per-tier (tier-1 = dedicated Commander), map to team members with training badges." \
  --deps "$EPIC5_ID"

$BD create "Build war room automation" --type feature --priority P2 \
  -d "Slack incident channels (auto-create on page), Zoom/MS Teams bridge creation, Confluence incident page template." \
  --deps "$EPIC5_ID"

$BD create "Implement post-incident automation" --type feature --priority P2 \
  -d "Auto-create Jira/Linear incident tickets, postmortem template generation, action item tracking." \
  --deps "$EPIC5_ID"

$BD create "Generate runbook content from service metadata" --type feature --priority P1 \
  -d "Auto-generate runbooks, common troubleshooting steps per tier, dependency diagrams, emergency contacts." \
  --deps "$EPIC5_ID"

echo "✅ Epic 5 complete: Incident Management Expansion (5 features)"
echo ""

#
# EPIC 6: Access Control & Security
#
echo "🔒 Creating Epic 6: Access Control & Security"
$BD create "Access Control & Security" --type epic --priority P2 \
  -d "Automated RBAC, secrets management, network policies, audit logging."

EPIC6_ID=$($BD list --title "Access Control" --json | jq -r '.[0].id')

$BD create "Generate AWS IAM roles for services" --type feature --priority P1 \
  -d "Auto-provision least-privilege IAM roles for service accounts, policy templates based on dependencies." \
  --deps "$EPIC6_ID"

$BD create "Generate Kubernetes RBAC policies" --type feature --priority P1 \
  -d "ServiceAccount, Role, RoleBinding generation. Minimal access patterns based on tier." \
  --deps "$EPIC6_ID"

$BD create "Implement database permission management" --type feature --priority P2 \
  -d "Auto-create database users (read-only, read-write), grant appropriate permissions, rotation policies." \
  --deps "$EPIC6_ID"

$BD create "Integrate Vault secrets management" --type feature --priority P2 \
  -d "Vault path setup, policy generation, secret rotation automation (90 days)." \
  --deps "$EPIC6_ID"

$BD create "Generate API gateway configurations" --type feature --priority P2 \
  -d "Rate limiting per tier, authentication requirements, CORS policies, IP allowlists/denylists." \
  --deps "$EPIC6_ID"

$BD create "Implement network policy generation" --type feature --priority P2 \
  -d "Kubernetes NetworkPolicies, AWS Security Groups, service mesh authorization (Istio)." \
  --deps "$EPIC6_ID"

$BD create "Configure audit logging" --type task --priority P2 \
  -d "CloudTrail rules, Kubernetes audit policies, database audit logging configs." \
  --deps "$EPIC6_ID"

echo "✅ Epic 6 complete: Access Control & Security (7 features)"
echo ""

#
# EPIC 7: Cost Management
#
echo "💵 Creating Epic 7: Cost Management"
$BD create "Cost Management" --type epic --priority P3 \
  -d "Cost tracking, budgets, auto-scaling, resource quotas."

EPIC7_ID=$($BD list --title "Cost Management" --json | jq -r '.[0].id')

$BD create "Implement cost allocation tagging" --type feature --priority P2 \
  -d "AWS resource tagging (Team, Service, Environment, Tier), GCP labels, Azure tags, consistent taxonomy." \
  --deps "$EPIC7_ID"

TAG_ID=$($BD list --title "cost allocation tagging" --json | jq -r '.[0].id')

$BD create "Generate budget alerts and tracking" --type feature --priority P2 \
  -d "AWS Budgets per service/team, alert thresholds based on historical spend, cost anomaly detection." \
  --deps "$EPIC7_ID,$TAG_ID"

$BD create "Implement auto-scaling policies" --type feature --priority P2 \
  -d "Kubernetes HPA, AWS Auto Scaling Groups, min/max replicas based on tier, target CPU/memory utilization." \
  --deps "$EPIC7_ID"

$BD create "Configure resource quotas" --type feature --priority P3 \
  -d "Kubernetes ResourceQuota per namespace, CPU/memory limits, storage quotas." \
  --deps "$EPIC7_ID"

echo "✅ Epic 7 complete: Cost Management (4 features)"
echo ""

#
# EPIC 8: Documentation & Knowledge
#
echo "📚 Creating Epic 8: Documentation & Knowledge"
$BD create "Documentation & Knowledge" --type epic --priority P2 \
  -d "Auto-generated runbooks, service docs, onboarding guides, dependency graphs."

EPIC8_ID=$($BD list --title "Documentation" --json | jq -r '.[0].id')

$BD create "Implement runbook auto-generation" --type feature --priority P1 \
  -d "Generate from service metadata, common troubleshooting, dependency diagrams, emergency contacts." \
  --deps "$EPIC8_ID"

$BD create "Generate service documentation templates" --type feature --priority P2 \
  -d "README templates (architecture, APIs, deployment), ADR scaffolding, API documentation (OpenAPI/Swagger)." \
  --deps "$EPIC8_ID"

$BD create "Create onboarding guide generation" --type feature --priority P2 \
  -d "New team member checklists, service ownership handoff docs, access request procedures." \
  --deps "$EPIC8_ID"

$BD create "Build dependency graph visualization" --type feature --priority P2 \
  -d "Service mesh topology, database dependency maps, external API dependencies, blast radius visualization." \
  --deps "$EPIC8_ID"

$BD create "Integrate with Confluence/Notion" --type feature --priority P2 \
  -d "Auto-publish documentation to Confluence or Notion, keep in sync with Git sources." \
  --deps "$EPIC8_ID"

echo "✅ Epic 8 complete: Documentation & Knowledge (5 features)"
echo ""

#
# EPIC 9: Compliance & Governance
#
echo "📋 Creating Epic 9: Compliance & Governance"
$BD create "Compliance & Governance" --type epic --priority P3 \
  -d "Policy-as-code for SOC2/GDPR/HIPAA, backup/DR, data retention."

EPIC9_ID=$($BD list --title "Compliance" --json | jq -r '.[0].id')

$BD create "Implement SOC2 control mappings" --type feature --priority P3 \
  -d "Map NthLayer configs to SOC2 controls, auto-generate compliance evidence, audit reports." \
  --deps "$EPIC9_ID"

$BD create "Add GDPR data handling configurations" --type feature --priority P3 \
  -d "Data retention policies, encryption requirements, data subject access procedures." \
  --deps "$EPIC9_ID"

$BD create "Configure backup and DR policies" --type feature --priority P2 \
  -d "Backup schedules based on tier, RTO/RPO enforcement, multi-region failover, disaster recovery runbooks." \
  --deps "$EPIC9_ID"

$BD create "Implement data retention policy automation" --type feature --priority P3 \
  -d "Log retention (tier-based), database backup retention, S3 lifecycle policies." \
  --deps "$EPIC9_ID"

$BD create "Generate OPA/Sentinel policies" --type feature --priority P3 \
  -d "Open Policy Agent policies, AWS Config rules, Terraform Sentinel policies, Kubernetes admission controllers." \
  --deps "$EPIC9_ID"

echo "✅ Epic 9 complete: Compliance & Governance (5 features)"
echo ""

#
# EPIC 10: Strategic Positioning & Launch
#
echo "🚀 Creating Epic 10: Strategic Positioning & Launch"
$BD create "Strategic Positioning & Launch" --type epic --priority P1 \
  -d "Demo deployment, case studies, sales materials, pilot program, customer acquisition."

EPIC10_ID=$($BD list --title "Strategic Positioning" --json | jq -r '.[0].id')

# Link to existing live demo epic
LIVE_DEMO_ID=$($BD list --title "Live Demo Infrastructure" --json | jq -r '.[0].id')
$BD dep add "$LIVE_DEMO_ID" "$EPIC10_ID"

$BD create "Develop 3-5 customer case studies" --type task --priority P1 \
  -d "Document pilot customer results, time/cost savings, ROI calculations, testimonials." \
  --deps "$EPIC10_ID"

$BD create "Create sales materials and pitch deck" --type task --priority P1 \
  -d "Value proposition slides, competitive analysis, pricing justification, demo script." \
  --deps "$EPIC10_ID"

$BD create "Execute pilot program (5-8 customers)" --type task --priority P0 \
  -d "Recruit pilots, free for 3 months, weekly feedback sessions, letters of intent." \
  --deps "$EPIC10_ID"

PILOT_ID=$($BD list --title "Execute pilot program" --json | jq -r '.[0].id')

$BD create "Convert pilots to paid customers" --type task --priority P0 \
  -d "Convert 2-3 pilots to $2k-5k/month contracts. Target: $6k-15k MRR." \
  --deps "$EPIC10_ID,$PILOT_ID"

$BD create "Launch pricing page and public site" --type task --priority P1 \
  -d "Productize onboarding, self-service signup, pricing tiers (Starter/Professional/Enterprise)." \
  --deps "$EPIC10_ID"

$BD create "Scale to $10k-20k MRR" --type task --priority P0 \
  -d "Outbound sales (20-30/week), content marketing, 5-8 customers total." \
  --deps "$EPIC10_ID"

$BD create "Conduct customer validation interviews" --type task --priority P0 \
  -d "Interview 20 SRE teams, validate problem, secure 3-5 letters of intent before building error budgets." \
  --deps "$EPIC10_ID"

$BD create "Define product roadmap priorities" --type task --priority P1 \
  -d "Based on pilot feedback, prioritize feature development. Document in beads." \
  --deps "$EPIC10_ID,$PILOT_ID"

echo "✅ Epic 10 complete: Strategic Positioning & Launch (9 features)"
echo ""

echo "================================================"
echo "✅ Migration Complete!"
echo ""
echo "Summary:"
echo "  - 10 Epics created"
echo "  - ~67 Features/Tasks created"
echo "  - All with proper dependencies"
echo ""
echo "Next steps:"
echo "  1. Review: bd list --long"
echo "  2. Check dependencies: bd dep tree <epic-id>"
echo "  3. See ready work: bd ready"
echo "  4. Update current task: bd update trellis-948 --status in_progress"
echo ""
echo "Happy tracking! 🎉"
