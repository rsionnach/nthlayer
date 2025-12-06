# Supported Technologies

NthLayer includes pre-built monitoring templates for 18 technologies.

## Overview

| Category | Technologies |
|----------|--------------|
| **Databases** | PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch |
| **Message Queues** | Kafka, RabbitMQ, NATS, Pulsar |
| **Proxies/Load Balancers** | Nginx, HAProxy, Traefik |
| **Infrastructure** | Kubernetes, etcd, Consul |

## Databases

### PostgreSQL

```yaml
dependencies:
  - postgresql
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Active Connections | `pg_stat_activity_count` |
| Replication Lag | `pg_replication_lag` |
| Transactions/sec | `pg_stat_database_xact_commit` |
| Cache Hit Ratio | `pg_stat_database_blks_hit` |
| Dead Tuples | `pg_stat_user_tables_n_dead_tup` |

**Alerts:**

- High connection count (> 80% of max)
- Replication lag > 30s
- Low cache hit ratio (< 90%)

---

### MySQL / MariaDB

```yaml
dependencies:
  - mysql
  # or
  - mariadb
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Connections | `mysql_global_status_threads_connected` |
| Queries/sec | `mysql_global_status_queries` |
| Slow Queries | `mysql_global_status_slow_queries` |
| Replication Lag | `mysql_slave_status_seconds_behind_master` |

---

### MongoDB

```yaml
dependencies:
  - mongodb
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Connections | `mongodb_connections` |
| Operations/sec | `mongodb_op_counters_total` |
| Replication Lag | `mongodb_replset_member_replication_lag` |
| Document Operations | `mongodb_mongod_metrics_document_total` |

---

### Redis

```yaml
dependencies:
  - redis
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Memory Usage | `redis_memory_used_bytes` |
| Connected Clients | `redis_connected_clients` |
| Hit Rate | `redis_keyspace_hits_total / (hits + misses)` |
| Commands/sec | `redis_commands_processed_total` |
| Evictions | `redis_evicted_keys_total` |

---

### Elasticsearch

```yaml
dependencies:
  - elasticsearch
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Cluster Health | `elasticsearch_cluster_health_status` |
| JVM Heap | `elasticsearch_jvm_memory_used_bytes` |
| Indexing Rate | `elasticsearch_indices_indexing_index_total` |
| Search Rate | `elasticsearch_indices_search_query_total` |
| Pending Tasks | `elasticsearch_cluster_health_number_of_pending_tasks` |

---

## Message Queues

### Kafka

```yaml
dependencies:
  - kafka
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Consumer Lag | `kafka_consumer_group_lag` |
| Messages/sec | `kafka_server_brokertopicmetrics_messagesin_total` |
| Partitions | `kafka_topic_partitions` |
| Under-replicated | `kafka_server_replicamanager_underreplicatedpartitions` |

**Alerts:**

- Consumer lag > 10,000 messages
- Under-replicated partitions > 0

---

### RabbitMQ

```yaml
dependencies:
  - rabbitmq
  # or
  - rabbit
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Queue Messages | `rabbitmq_queue_messages` |
| Consumers | `rabbitmq_queue_consumers` |
| Publish Rate | `rabbitmq_channel_messages_published_total` |
| Connections | `rabbitmq_connections` |
| Memory | `rabbitmq_node_mem_used` |

---

### NATS

```yaml
dependencies:
  - nats
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Connections | `nats_connections` |
| Messages In/Out | `nats_messages_total` |
| Bytes In/Out | `nats_bytes_total` |
| Subscriptions | `nats_subscriptions` |
| Slow Consumers | `nats_slow_consumers` |

---

### Pulsar

```yaml
dependencies:
  - pulsar
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Throughput In | `pulsar_throughput_in` |
| Throughput Out | `pulsar_throughput_out` |
| Message Backlog | `pulsar_msg_backlog` |
| Subscriptions | `pulsar_subscriptions_count` |
| Storage Size | `pulsar_storage_size` |

---

## Proxies / Load Balancers

### Nginx

```yaml
dependencies:
  - nginx
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Requests/sec | `nginx_http_requests_total` |
| Active Connections | `nginx_connections_active` |
| Response Codes | `nginx_http_requests_total` by status |
| Request Duration | `nginx_http_request_duration_seconds` |
| Upstream Response Time | `nginx_upstream_response_time` |

---

### HAProxy

```yaml
dependencies:
  - haproxy
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Request Rate | `haproxy_frontend_http_requests_total` |
| Active Connections | `haproxy_frontend_current_sessions` |
| Response Time | `haproxy_backend_response_time_average_seconds` |
| Backend Status | `haproxy_backend_up` |
| Error Rate | `haproxy_backend_http_responses_total{code="5xx"}` |
| Queue Length | `haproxy_backend_current_queue` |

---

### Traefik

```yaml
dependencies:
  - traefik
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Requests/sec | `traefik_service_requests_total` |
| Request Duration | `traefik_service_request_duration_seconds` |
| Response Codes | `traefik_service_requests_total` by code |
| Open Connections | `traefik_service_open_connections` |
| Entrypoint Requests | `traefik_entrypoint_requests_total` |

---

## Infrastructure

### Kubernetes

```yaml
dependencies:
  - kubernetes
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Pod Status | `kube_pod_status_phase` |
| Container Restarts | `kube_pod_container_status_restarts_total` |
| CPU Usage | `container_cpu_usage_seconds_total` |
| Memory Usage | `container_memory_usage_bytes` |
| PVC Usage | `kubelet_volume_stats_used_bytes` |

---

### etcd

```yaml
dependencies:
  - etcd
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Leader Status | `etcd_server_has_leader` |
| DB Size | `etcd_mvcc_db_total_size_in_bytes` |
| Proposals | `etcd_server_proposals_committed_total` |
| WAL Fsync | `etcd_disk_wal_fsync_duration_seconds` |
| Network Peer RTT | `etcd_network_peer_round_trip_time_seconds` |

---

### Consul

```yaml
dependencies:
  - consul
```

**Generated Panels:**

| Panel | Metric |
|-------|--------|
| Leader | `consul_raft_leader` |
| Peers | `consul_raft_peers` |
| Services | `consul_catalog_services` |
| Health Checks | `consul_health_checks_critical` |
| RPC Rate | `consul_rpc_request` |

---

## Adding Custom Technologies

See [Service Specifications](../concepts/service-specs.md) for extending with your own configurations.
