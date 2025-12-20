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

   specs:R --> L:reslayer
   specs:R --> L:govlayer
   specs:R --> L:obslayer

   reslayer:R --> L:prometheus
   obslayer:R --> L:grafana
   obslayer:R --> L:pagerduty
```

## CLI Commands

NthLayer provides these core commands for reliability shift left:

```mermaid
architecture-beta
   group generate(mdi:cog) [Generate]
   group validate(mdi:check-circle) [Validate]
   group enforce(mdi:shield-check) [Enforce]

   service apply(mdi:play) [nthlayer apply] in generate
   service plan(mdi:file-search) [nthlayer plan] in generate

   service lint(mdi:code-tags-check) [nthlayer apply lint] in validate
   service verify(mdi:check-decagram) [nthlayer verify] in validate

   service checkdeploy(mdi:gate) [nthlayer check deploy] in enforce
   service portfolio(mdi:chart-box) [nthlayer portfolio] in enforce

   plan:R --> L:apply
   apply:R --> L:lint
   lint:R --> L:verify
   verify:R --> L:checkdeploy
```

## Apply Workflow

When you run `nthlayer apply`, the following artifacts are generated from your service specification:

```mermaid
architecture-beta
   group inputgrp(mdi:file-document) [Input]
   group processing(mdi:cog) [NthLayer Processing]
   group outputgrp(mdi:package-variant) [Generated Artifacts]

   service specfile(mdi:file-code) [Service Spec] in inputgrp

   service parser(mdi:file-search) [Spec Parser] in processing
   service slogen(mdi:target) [SLO Generator] in processing
   service alertgen(mdi:bell-alert) [Alert Generator] in processing
   service dashgen(mdi:view-dashboard) [Dashboard Builder] in processing
   service pdgen(logos:pagerduty) [PagerDuty Setup] in processing

   service slofile(mdi:file-check) [SLO File] in outputgrp
   service alertfile(mdi:file-alert) [Alert Rules] in outputgrp
   service dashfile(mdi:file-chart) [Dashboard] in outputgrp
   service recfile(mdi:file-clock) [Recording Rules] in outputgrp
   service pdfile(mdi:file-cog) [PagerDuty Config] in outputgrp

   specfile:R --> L:parser
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

NthLayer integrates with your existing observability stack:

```mermaid
architecture-beta
   group cicd(mdi:pipe) [CICD Pipeline]
   group observability(mdi:cloud) [Observability Stack]

   service developer(mdi:account) [Developer] in cicd
   service pipeline(mdi:source-branch) [Pipeline] in cicd
   service nthlayer(mdi:cog) [NthLayer CLI] in cicd

   service prometheus(logos:prometheus) [Prometheus] in observability
   service grafana(logos:grafana) [Grafana] in observability
   service pagerduty(logos:pagerduty) [PagerDuty] in observability

   developer:R --> L:pipeline
   pipeline:R --> L:nthlayer
   nthlayer:R --> L:prometheus
   nthlayer:R --> L:grafana
   nthlayer:R --> L:pagerduty
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
   service healthcalc(mdi:calculator) [Health Calculator] in collection

   service termout(mdi:console) [Terminal] in outputgrp
   service jsonout(mdi:code-json) [JSON] in outputgrp
   service csvout(mdi:file-delimited) [CSV] in outputgrp

   svc1:R --> L:scanner
   svc2:R --> L:scanner
   svc3:R --> L:scanner

   scanner:R --> L:aggregator
   aggregator:R --> L:healthcalc

   healthcalc:R --> L:termout
   healthcalc:R --> L:jsonout
   healthcalc:R --> L:csvout
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

## Reliability Shift Left Flow

The complete flow from code to production gate:

```mermaid
architecture-beta
   group dev(mdi:code-braces) [Development]
   group validation(mdi:check-circle) [Validation]
   group deploy(mdi:rocket-launch) [Deployment]

   service code(mdi:git) [Git Push] in dev
   service spec(mdi:file-code) [Service Spec] in dev

   service lint(mdi:code-tags-check) [PromQL Lint] in validation
   service verify(mdi:check-decagram) [Metric Verify] in validation
   service budget(mdi:target) [Budget Check] in validation

   service gate(mdi:gate) [Deploy Gate] in deploy
   service prod(mdi:server) [Production] in deploy

   code:R --> L:spec
   spec:R --> L:lint
   lint:R --> L:verify
   verify:R --> L:budget
   budget:R --> L:gate
   gate:R --> L:prod
```
