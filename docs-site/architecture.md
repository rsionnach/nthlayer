# Architecture

This page provides visual documentation of NthLayer's architecture, workflows, and integrations.

## Platform Architecture

The NthLayer platform sits between your service definitions and your observability stack, generating the complete reliability infrastructure.

```mermaid
architecture-beta
    group git(logos:git-icon) [Git Repository]
    group nthlayer(mdi:cog) [NthLayer Platform]
    group observability(mdi:cloud) [Observability Stack]

    service specs(mdi:file-code) [Service YAML Files] in git

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

    service yaml(mdi:file-code) [Service YAML] in input

    service parser(mdi:file-search) [Spec Parser] in processing
    service slogen(mdi:target) [SLO Generator] in processing
    service alertgen(mdi:bell-alert) [Alert Generator] in processing
    service dashgen(mdi:view-dashboard) [Dashboard Builder] in processing
    service pdgen(logos:pagerduty) [PagerDuty Setup] in processing

    service slos(mdi:file-check) [SLOs YAML] in output
    service alerts(mdi:file-alert) [Alerts YAML] in output
    service dashboard(mdi:file-chart) [Dashboard JSON] in output
    service recording(mdi:file-clock) [Recording Rules] in output
    service pdconfig(mdi:file-cog) [PagerDuty Config] in output

    yaml:R --> L:parser
    parser:R --> L:slogen
    parser:R --> L:alertgen
    parser:R --> L:dashgen
    parser:R --> L:pdgen

    slogen:R --> L:slos
    slogen:R --> L:recording
    alertgen:R --> L:alerts
    dashgen:R --> L:dashboard
    pdgen:R --> L:pdconfig
```

## Integration Architecture

NthLayer integrates with your existing observability stack without requiring changes to your infrastructure:

```mermaid
architecture-beta
    group user(mdi:account-group) [User Environment]
    group cli(mdi:console) [NthLayer CLI]
    group metrics(mdi:chart-line) [Metrics Stack]
    group incidents(mdi:alert) [Incident Management]

    service developer(mdi:account) [Developer] in user
    service cicd(mdi:pipe) [CICD Pipeline] in user
    service k8s(logos:kubernetes) [Kubernetes] in user

    service apply(mdi:play) [nthlayer apply] in cli
    service portfolio(mdi:chart-box) [nthlayer portfolio] in cli
    service setup(mdi:cog) [nthlayer setup] in cli

    service prom(logos:prometheus) [Prometheus] in metrics
    service grafana(logos:grafana) [Grafana Cloud] in metrics
    service loki(logos:loki) [Loki] in metrics

    service pagerduty(logos:pagerduty) [PagerDuty] in incidents
    service slack(logos:slack-icon) [Slack] in incidents

    developer:R --> L:apply
    cicd:R --> L:apply

    apply:R --> L:prom
    apply:R --> L:grafana
    apply:R --> L:pagerduty

    portfolio:R --> L:prom
    setup:R --> L:grafana
    setup:R --> L:pagerduty

    pagerduty:R --> L:slack
    prom:R --> L:grafana
```

## SLO Portfolio Flow

The portfolio command aggregates SLO health across all services:

```mermaid
architecture-beta
    group services(mdi:folder) [Service Definitions]
    group collection(mdi:cog) [Portfolio Collection]
    group output(mdi:export) [Output]

    service svc1(mdi:file-code) [Payment API] in services
    service svc2(mdi:file-code) [Checkout Service] in services
    service svc3(mdi:file-code) [Notification Worker] in services

    service scanner(mdi:file-search) [Service Scanner] in collection
    service aggregator(mdi:chart-timeline-variant) [SLO Aggregator] in collection
    service health(mdi:calculator) [Health Calculator] in collection

    service text(mdi:console) [Terminal Output] in output
    service json(mdi:code-json) [JSON Export] in output
    service csv(mdi:file-delimited) [CSV Export] in output

    svc1:R --> L:scanner
    svc2:R --> L:scanner
    svc3:R --> L:scanner

    scanner:R --> L:aggregator
    aggregator:R --> L:health

    health:R --> L:text
    health:R --> L:json
    health:R --> L:csv
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

    service yaml(mdi:file-code) [Service YAML] in applyflow
    service apply(mdi:play) [NthLayer Apply] in applyflow
    service alerts(logos:prometheus) [Prometheus Alerts] in applyflow
    service dashboard(logos:grafana) [Grafana Dashboard] in applyflow
    service pdsetup(logos:pagerduty) [PagerDuty Setup] in applyflow
    service rules(mdi:file-clock) [Recording Rules] in applyflow
    service slos(mdi:target) [SLO Definitions] in applyflow

    service portfolio(mdi:chart-box) [NthLayer Portfolio] in portfolioflow
    service scan(mdi:file-search) [Scan Services] in portfolioflow
    service aggregate(mdi:chart-timeline-variant) [Aggregate SLOs] in portfolioflow
    service report(mdi:file-chart) [Health Report] in portfolioflow

    yaml:R --> L:apply
    apply:R --> L:alerts
    apply:R --> L:dashboard
    apply:R --> L:pdsetup
    apply:R --> L:rules
    apply:R --> L:slos

    portfolio:R --> L:scan
    scan:R --> L:aggregate
    aggregate:R --> L:report
```
