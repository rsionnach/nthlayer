# Architecture

This page provides visual documentation of NthLayer's architecture, workflows, and integrations.

## Platform Architecture

The NthLayer platform sits between your service definitions and your observability stack, generating the complete reliability infrastructure.

```mermaid
architecture-beta
    group git(disk)[Git Repository]
    group nthlayer(server)[NthLayer Platform]
    group observability(cloud)[Observability Stack]

    service specs(disk)[services/*.yaml] in git

    service reslayer(server)[ResLayer - SLOs & Error Budgets] in nthlayer
    service govlayer(server)[GovLayer - Policy Enforcement] in nthlayer
    service obslayer(server)[ObserveLayer - Monitoring] in nthlayer

    service prometheus(server)[Prometheus] in observability
    service grafana(server)[Grafana] in observability
    service pagerduty(server)[PagerDuty] in observability
    service loki(server)[Loki] in observability

    specs:R --> L:reslayer
    specs:R --> L:govlayer
    specs:R --> L:obslayer

    reslayer:B --> T:prometheus
    obslayer:B --> T:grafana
    obslayer:B --> T:pagerduty
    obslayer:B --> T:loki
```

## Apply Workflow

When you run `nthlayer apply`, the following artifacts are generated from your service specification:

```mermaid
architecture-beta
    group input(disk)[Input]
    group processing(server)[NthLayer Processing]
    group output(cloud)[Generated Artifacts]

    service yaml(disk)[service.yaml] in input

    service parser(server)[Spec Parser] in processing
    service slo_gen(server)[SLO Generator] in processing
    service alert_gen(server)[Alert Generator] in processing
    service dash_gen(server)[Dashboard Builder] in processing
    service pd_gen(server)[PagerDuty Setup] in processing

    service slos(disk)[slos.yaml] in output
    service alerts(disk)[alerts.yaml] in output
    service dashboard(disk)[dashboard.json] in output
    service recording(disk)[recording-rules.yaml] in output
    service pd_config(disk)[pagerduty-config.json] in output

    yaml:R --> L:parser
    parser:R --> L:slo_gen
    parser:R --> L:alert_gen
    parser:R --> L:dash_gen
    parser:R --> L:pd_gen

    slo_gen:R --> L:slos
    slo_gen:R --> L:recording
    alert_gen:R --> L:alerts
    dash_gen:R --> L:dashboard
    pd_gen:R --> L:pd_config
```

## Integration Architecture

NthLayer integrates with your existing observability stack without requiring changes to your infrastructure:

```mermaid
architecture-beta
    group user(internet)[User Environment]
    group nthlayer_cli(server)[NthLayer CLI]
    group metrics(database)[Metrics Stack]
    group incidents(cloud)[Incident Management]

    service developer(internet)[Developer] in user
    service ci_cd(server)[CI/CD Pipeline] in user
    service k8s(server)[Kubernetes] in user

    service apply(server)[nthlayer apply] in nthlayer_cli
    service portfolio(server)[nthlayer portfolio] in nthlayer_cli
    service setup(server)[nthlayer setup] in nthlayer_cli

    service prom(database)[Prometheus] in metrics
    service grafana(server)[Grafana Cloud] in metrics
    service loki(database)[Loki] in metrics

    service pagerduty(cloud)[PagerDuty] in incidents
    service slack(cloud)[Slack] in incidents

    developer:R --> L:apply
    ci_cd:B --> T:apply

    apply:R --> L:prom
    apply:R --> L:grafana
    apply:R --> L:pagerduty

    portfolio:R --> L:prom
    setup:R --> L:grafana
    setup:R --> L:pagerduty

    pagerduty:R --> L:slack
    prom:B --> T:grafana
```

## SLO Portfolio Flow

The portfolio command aggregates SLO health across all services:

```mermaid
architecture-beta
    group services(disk)[Service Definitions]
    group collection(server)[Portfolio Collection]
    group output(cloud)[Output]

    service svc1(disk)[payment-api.yaml] in services
    service svc2(disk)[checkout-service.yaml] in services
    service svc3(disk)[notification-worker.yaml] in services

    service scanner(server)[Service Scanner] in collection
    service aggregator(server)[SLO Aggregator] in collection
    service health(server)[Health Calculator] in collection

    service text(internet)[Terminal Output] in output
    service json(disk)[JSON Export] in output
    service csv(disk)[CSV Export] in output

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
    group databases(database)[Databases]
    group caches(server)[Caches & Queues]
    group infra(cloud)[Infrastructure]

    service postgres(database)[PostgreSQL] in databases
    service mysql(database)[MySQL] in databases
    service mongodb(database)[MongoDB] in databases
    service elasticsearch(database)[Elasticsearch] in databases

    service redis(server)[Redis] in caches
    service kafka(server)[Kafka] in caches
    service rabbitmq(server)[RabbitMQ] in caches
    service nats(server)[NATS] in caches

    service nginx(cloud)[Nginx] in infra
    service haproxy(cloud)[HAProxy] in infra
    service traefik(cloud)[Traefik] in infra
    service k8s(cloud)[Kubernetes] in infra
```
