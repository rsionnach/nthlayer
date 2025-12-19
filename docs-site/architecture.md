# Architecture

This page provides visual documentation of NthLayer's architecture, workflows, and integrations.

## Platform Architecture

The NthLayer platform sits between your service definitions and your observability stack, generating the complete reliability infrastructure.

```mermaid
architecture-beta
   group git(logos:git-icon) [Git Repository]
   group nthlayer(mdi:cog) [NthLayer Platform]
   group observability(mdi:cloud) [Observability Stack]

   service specs(mdi:file-code) [Service Definitions] in git

   service reslayer(mdi:target) [ResLayer SLOs] in nthlayer
   service govlayer(mdi:shield-check) [GovLayer Policies] in nthlayer
   service obslayer(mdi:eye) [ObserveLayer Monitoring] in nthlayer

   service prometheus(logos:prometheus) [Prometheus] in observability
   service grafana(logos:grafana) [Grafana] in observability
   service pagerduty(logos:pagerduty) [PagerDuty] in observability
   service loki(logos:loki) [Loki] in observability

   specs:R --> L:reslayer
   specs:R --> L:govlayer
   specs:R --> L:obslayer

   reslayer:R --> L:prometheus
   obslayer:R --> L:grafana
   obslayer:R --> L:pagerduty
   obslayer:R --> L:loki
```

## Apply Workflow

When you run `nthlayer apply`, the following artifacts are generated from your service specification:

```mermaid
architecture-beta
   group input(mdi:file-document) [Input]
   group processing(mdi:cog) [NthLayer Processing]
   group output(mdi:package-variant) [Generated Artifacts]

   service yamlfile(mdi:file-code) [Service Spec] in input

   service parser(mdi:file-search) [Spec Parser] in processing
   service slogen(mdi:target) [SLO Generator] in processing
   service alertgen(mdi:bell-alert) [Alert Generator] in processing
   service dashgen(mdi:view-dashboard) [Dashboard Builder] in processing
   service pdgen(logos:pagerduty) [PagerDuty Setup] in processing

   service slofile(mdi:file-check) [SLO File] in output
   service alertfile(mdi:file-alert) [Alert File] in output
   service dashfile(mdi:file-chart) [Dashboard File] in output
   service recfile(mdi:file-clock) [Recording Rules] in output
   service pdfile(mdi:file-cog) [PagerDuty Config] in output

   yamlfile:R --> L:parser
   parser:R --> L:slogen
   parser:R --> L:alertgen
   parser:R --> L:dashgen
   parser:R --> L:pdgen

   slogen:R --> L:slofile
   slogen:R --> L:recfile
   alertgen:R --> L:alertfile
   dashgen:R --> L:dashfile
   pdgen:R --> L:pdfile
```

## Integration Architecture

NthLayer integrates with your existing observability stack without requiring changes to your infrastructure:

```mermaid
architecture-beta
   group userenv(mdi:account-group) [User Environment]
   group cli(mdi:console) [NthLayer CLI]
   group metrics(mdi:chart-line) [Metrics Stack]
   group incidents(mdi:alert) [Incident Management]

   service developer(mdi:account) [Developer] in userenv
   service cicd(mdi:pipe) [CICD Pipeline] in userenv
   service k8s(logos:kubernetes) [Kubernetes] in userenv

   service ntlapply(mdi:play) [nthlayer apply] in cli
   service ntlportfolio(mdi:chart-box) [nthlayer portfolio] in cli
   service ntlsetup(mdi:cog) [nthlayer setup] in cli

   service prom(logos:prometheus) [Prometheus] in metrics
   service grafana(logos:grafana) [Grafana Cloud] in metrics
   service loki(logos:loki) [Loki] in metrics

   service pagerduty(logos:pagerduty) [PagerDuty] in incidents
   service slack(logos:slack-icon) [Slack] in incidents

   developer:R --> L:ntlapply
   cicd:R --> L:ntlapply

   ntlapply:R --> L:prom
   ntlapply:R --> L:grafana
   ntlapply:R --> L:pagerduty

   ntlportfolio:R --> L:prom
   ntlsetup:R --> L:grafana
   ntlsetup:R --> L:pagerduty

   pagerduty:R --> L:slack
   prom:R --> L:grafana
```

## SLO Portfolio Flow

The portfolio command aggregates SLO health across all services:

```mermaid
architecture-beta
   group services(mdi:folder) [Service Definitions]
   group collection(mdi:cog) [Portfolio Collection]
   group outputgrp(mdi:export) [Output]

   service svc1(mdi:file-code) [Payment API] in services
   service svc2(mdi:file-code) [Checkout Service] in services
   service svc3(mdi:file-code) [Notification Worker] in services

   service scanner(mdi:file-search) [Service Scanner] in collection
   service aggregator(mdi:chart-timeline-variant) [SLO Aggregator] in collection
   service health(mdi:calculator) [Health Calculator] in collection

   service termout(mdi:console) [Terminal Output] in outputgrp
   service jsonout(mdi:code-json) [JSON Export] in outputgrp
   service csvout(mdi:file-delimited) [CSV Export] in outputgrp

   svc1:R --> L:scanner
   svc2:R --> L:scanner
   svc3:R --> L:scanner

   scanner:R --> L:aggregator
   aggregator:R --> L:health

   health:R --> L:termout
   health:R --> L:jsonout
   health:R --> L:csvout
```

## Technology Support

NthLayer generates technology-specific monitoring for 18+ technologies:

```mermaid
architecture-beta
   group databases(mdi:database) [Databases]
   group caches(mdi:lightning-bolt) [Caches and Queues]
   group infra(mdi:server-network) [Infrastructure]

   service postgres(logos:postgresql) [PostgreSQL] in databases
   service mysql(logos:mysql) [MySQL] in databases
   service mongodb(logos:mongodb-icon) [MongoDB] in databases
   service elasticsearch(logos:elasticsearch) [Elasticsearch] in databases

   service redis(logos:redis) [Redis] in caches
   service kafka(logos:kafka-icon) [Kafka] in caches
   service rabbitmq(logos:rabbitmq-icon) [RabbitMQ] in caches
   service nats(logos:nats-icon) [NATS] in caches

   service nginx(logos:nginx) [Nginx] in infra
   service haproxy(mdi:arrow-decision) [HAProxy] in infra
   service traefik(logos:traefik) [Traefik] in infra
   service k8s(logos:kubernetes) [Kubernetes] in infra
```

## Data Flow Summary

```mermaid
architecture-beta
   group applyflow(mdi:arrow-right) [Apply Flow]
   group portfolioflow(mdi:arrow-right) [Portfolio Flow]

   service specfile(mdi:file-code) [Service Spec] in applyflow
   service applyrun(mdi:play) [NthLayer Apply] in applyflow
   service promalerts(logos:prometheus) [Prometheus Alerts] in applyflow
   service grafdash(logos:grafana) [Grafana Dashboard] in applyflow
   service pdsetup(logos:pagerduty) [PagerDuty Setup] in applyflow
   service recrules(mdi:file-clock) [Recording Rules] in applyflow
   service slodefs(mdi:target) [SLO Definitions] in applyflow

   service portrun(mdi:chart-box) [NthLayer Portfolio] in portfolioflow
   service scansvcs(mdi:file-search) [Scan Services] in portfolioflow
   service aggrslos(mdi:chart-timeline-variant) [Aggregate SLOs] in portfolioflow
   service healthrpt(mdi:file-chart) [Health Report] in portfolioflow

   specfile:R --> L:applyrun
   applyrun:R --> L:promalerts
   applyrun:R --> L:grafdash
   applyrun:R --> L:pdsetup
   applyrun:R --> L:recrules
   applyrun:R --> L:slodefs

   portrun:R --> L:scansvcs
   scansvcs:R --> L:aggrslos
   aggrslos:R --> L:healthrpt
```
