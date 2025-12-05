"""
Loki Log Pattern Templates

Technology-specific log patterns for generating LogQL alert rules.
Each pattern defines what to look for in logs and appropriate alert thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LogPattern:
    """A log pattern definition for a specific error condition."""

    name: str
    pattern: str  # LogQL pattern or regex
    severity: str
    for_duration: str
    summary: str
    description: str
    threshold: int = 0  # 0 means any occurrence triggers
    window: str = "5m"  # Time window for rate/count


# PostgreSQL log patterns
POSTGRESQL_PATTERNS = [
    LogPattern(
        name="PostgresqlFatalError",
        pattern='|= "FATAL"',
        severity="critical",
        for_duration="0m",
        summary="PostgreSQL FATAL error detected",
        description="PostgreSQL logged a FATAL error which typically indicates a serious issu...",
    ),
    LogPattern(
        name="PostgresqlPanicError",
        pattern='|= "PANIC"',
        severity="critical",
        for_duration="0m",
        summary="PostgreSQL PANIC error detected",
        description="PostgreSQL logged a PANIC error - the database may have crashed or be in...",
    ),
    LogPattern(
        name="PostgresqlDeadlock",
        pattern='|= "deadlock detected"',
        severity="warning",
        for_duration="0m",
        summary="PostgreSQL deadlock detected",
        description="A deadlock was detected in PostgreSQL. This may indicate application log...",
    ),
    LogPattern(
        name="PostgresqlConnectionRefused",
        pattern='|~ "connection refused|could not connect"',
        severity="critical",
        for_duration="1m",
        summary="PostgreSQL connection refused",
        description="Applications are unable to connect to PostgreSQL. Check if the database ...",
    ),
    LogPattern(
        name="PostgresqlOutOfConnections",
        pattern='|= "too many connections"',
        severity="critical",
        for_duration="0m",
        summary="PostgreSQL out of connections",
        description="PostgreSQL has reached its maximum connection limit. Consider increasing...",
    ),
    LogPattern(
        name="PostgresqlSlowQuery",
        pattern='|= "duration:" |~ "duration: [0-9]{4,}"',
        severity="warning",
        for_duration="5m",
        summary="PostgreSQL slow queries detected",
        description="Slow queries (>1s) are being logged. Review query performance and consid...",
        threshold=5,
        window="5m",
    ),
    LogPattern(
        name="PostgresqlReplicationLag",
        pattern='|~ "replication.*lag|recovery.*behind"',
        severity="warning",
        for_duration="5m",
        summary="PostgreSQL replication lag detected",
        description="Replication lag detected between primary and replica. Check network and ...",
    ),
]

# Redis log patterns
REDIS_PATTERNS = [
    LogPattern(
        name="RedisOutOfMemory",
        pattern='|~ "OOM|out of memory|Can\'t save"',
        severity="critical",
        for_duration="0m",
        summary="Redis out of memory",
        description="Redis is out of memory. Consider increasing maxmemory or reviewing evict...",
    ),
    LogPattern(
        name="RedisConnectionRefused",
        pattern='|~ "Connection refused|ECONNREFUSED"',
        severity="critical",
        for_duration="1m",
        summary="Redis connection refused",
        description="Applications cannot connect to Redis. Check if Redis is running and acce...",
    ),
    LogPattern(
        name="RedisRDBSaveFailed",
        pattern='|~ "MISCONF|Background saving|RDB"',
        severity="warning",
        for_duration="0m",
        summary="Redis RDB save failed",
        description="Redis background save (RDB) failed. Check disk space and permissions.",
    ),
    LogPattern(
        name="RedisReplicationBroken",
        pattern='|~ "MASTER aborted|Disconnected from MASTER|replication"',
        severity="critical",
        for_duration="1m",
        summary="Redis replication broken",
        description="Redis replication to master is broken. Check network connectivity and ma...",
    ),
    LogPattern(
        name="RedisSlowlog",
        pattern='|~ "Slow|slowlog"',
        severity="warning",
        for_duration="5m",
        summary="Redis slow commands detected",
        description="Slow Redis commands detected. Review command patterns and consider optim...",
        threshold=10,
        window="5m",
    ),
    LogPattern(
        name="RedisClusterDown",
        pattern='|~ "CLUSTERDOWN|cluster.*down|slots.*not covered"',
        severity="critical",
        for_duration="0m",
        summary="Redis cluster down",
        description="Redis cluster is in a down state. Some slots may not be covered.",
    ),
]

# Kafka log patterns
KAFKA_PATTERNS = [
    LogPattern(
        name="KafkaUnderReplicatedPartitions",
        pattern='|~ "under.?replicated|UnderReplicated"',
        severity="critical",
        for_duration="5m",
        summary="Kafka under-replicated partitions",
        description="Kafka has under-replicated partitions. Data durability may be at risk.",
    ),
    LogPattern(
        name="KafkaLeaderElection",
        pattern='|~ "leader.*election|LeaderElection|partition.*leader"',
        severity="warning",
        for_duration="0m",
        summary="Kafka leader election in progress",
        description="Kafka is performing leader election. This may cause brief unavailability...",
    ),
    LogPattern(
        name="KafkaBrokerDown",
        pattern='|~ "broker.*down|BrokerNotAvailable|disconnected"',
        severity="critical",
        for_duration="1m",
        summary="Kafka broker down",
        description="A Kafka broker appears to be down or unreachable.",
    ),
    LogPattern(
        name="KafkaConsumerLag",
        pattern='|~ "consumer.*lag|ConsumerLag|offset.*behind"',
        severity="warning",
        for_duration="10m",
        summary="Kafka consumer lag detected",
        description="Consumer group is lagging behind. Messages may not be processed in time.",
    ),
    LogPattern(
        name="KafkaOutOfDiskSpace",
        pattern='|~ "No space left|disk.*full|ENOSPC"',
        severity="critical",
        for_duration="0m",
        summary="Kafka out of disk space",
        description="Kafka broker is out of disk space. Immediate action required.",
    ),
    LogPattern(
        name="KafkaAuthenticationFailure",
        pattern='|~ "authentication.*fail|AuthenticationException|SASL"',
        severity="warning",
        for_duration="5m",
        summary="Kafka authentication failures",
        description="Authentication failures detected when connecting to Kafka.",
        threshold=5,
        window="5m",
    ),
]

# Kubernetes log patterns
KUBERNETES_PATTERNS = [
    LogPattern(
        name="KubernetesOOMKilled",
        pattern='|= "OOMKilled"',
        severity="critical",
        for_duration="0m",
        summary="Container OOMKilled",
        description="A container was killed due to out of memory. Consider increasing memory ...",
    ),
    LogPattern(
        name="KubernetesCrashLoopBackOff",
        pattern='|= "CrashLoopBackOff"',
        severity="critical",
        for_duration="0m",
        summary="Pod in CrashLoopBackOff",
        description="A pod is in CrashLoopBackOff state. Check container logs for the root ca...",
    ),
    LogPattern(
        name="KubernetesImagePullBackOff",
        pattern='|~ "ImagePullBackOff|ErrImagePull"',
        severity="warning",
        for_duration="5m",
        summary="Image pull failed",
        description="Kubernetes cannot pull container image. Check image name and registry cr...",
    ),
    LogPattern(
        name="KubernetesNodeNotReady",
        pattern='|~ "NodeNotReady|node.*not ready"',
        severity="critical",
        for_duration="5m",
        summary="Kubernetes node not ready",
        description="A Kubernetes node is not ready. Pods may be evicted or unable to schedule.",
    ),
    LogPattern(
        name="KubernetesPodEvicted",
        pattern='|= "Evicted"',
        severity="warning",
        for_duration="0m",
        summary="Pod evicted",
        description="A pod was evicted. This may be due to resource pressure on the node.",
    ),
    LogPattern(
        name="KubernetesSchedulingFailed",
        pattern='|~ "FailedScheduling|Insufficient|Unschedulable"',
        severity="warning",
        for_duration="5m",
        summary="Pod scheduling failed",
        description="Kubernetes cannot schedule pod. Check resource requests and node capacity.",
    ),
    LogPattern(
        name="KubernetesProbeFailure",
        pattern='|~ "Liveness probe failed|Readiness probe failed|probe failed"',
        severity="warning",
        for_duration="5m",
        summary="Health probe failures",
        description="Container health probes are failing. The container may be unhealthy.",
        threshold=3,
        window="5m",
    ),
]

# MongoDB log patterns
MONGODB_PATTERNS = [
    LogPattern(
        name="MongodbConnectionError",
        pattern='|~ "connection.*refused|failed to connect|ECONNREFUSED"',
        severity="critical",
        for_duration="1m",
        summary="MongoDB connection error",
        description="Applications cannot connect to MongoDB. Check if MongoDB is running.",
    ),
    LogPattern(
        name="MongodbReplicaSetError",
        pattern='|~ "replica set|replication.*error|cannot reach"',
        severity="critical",
        for_duration="5m",
        summary="MongoDB replica set error",
        description="MongoDB replica set has issues. Check member connectivity and elections.",
    ),
    LogPattern(
        name="MongodbSlowQuery",
        pattern='|~ "Slow query|operation exceeded|exceeded.*ms"',
        severity="warning",
        for_duration="5m",
        summary="MongoDB slow queries detected",
        description="Slow queries detected. Review query patterns and indexes.",
        threshold=5,
        window="5m",
    ),
    LogPattern(
        name="MongodbDiskSpaceLow",
        pattern='|~ "disk space|storage.*full|ENOSPC"',
        severity="critical",
        for_duration="0m",
        summary="MongoDB disk space low",
        description="MongoDB is running low on disk space.",
    ),
]

# Elasticsearch log patterns
ELASTICSEARCH_PATTERNS = [
    LogPattern(
        name="ElasticsearchClusterRed",
        pattern='|~ "cluster.*red|RED.*status"',
        severity="critical",
        for_duration="0m",
        summary="Elasticsearch cluster status RED",
        description="Elasticsearch cluster is in RED state. Some primary shards are unallocated.",
    ),
    LogPattern(
        name="ElasticsearchClusterYellow",
        pattern='|~ "cluster.*yellow|YELLOW.*status"',
        severity="warning",
        for_duration="10m",
        summary="Elasticsearch cluster status YELLOW",
        description="Elasticsearch cluster is YELLOW. Replica shards are unallocated.",
    ),
    LogPattern(
        name="ElasticsearchOutOfMemory",
        pattern='|~ "OutOfMemoryError|heap.*space|CircuitBreakingException"',
        severity="critical",
        for_duration="0m",
        summary="Elasticsearch out of memory",
        description="Elasticsearch is experiencing memory issues. Consider increasing heap size.",
    ),
    LogPattern(
        name="ElasticsearchShardFailure",
        pattern='|~ "shard.*fail|ShardNotFound|unassigned.*shard"',
        severity="warning",
        for_duration="5m",
        summary="Elasticsearch shard failure",
        description="Elasticsearch shard allocation failure detected.",
    ),
]

# MySQL log patterns
MYSQL_PATTERNS = [
    LogPattern(
        name="MysqlError",
        pattern='|~ "\\\\[ERROR\\\\]"',
        severity="critical",
        for_duration="0m",
        summary="MySQL error detected",
        description="MySQL logged an ERROR level message.",
    ),
    LogPattern(
        name="MysqlConnectionRefused",
        pattern='|~ "Connection refused|Can\'t connect|Access denied"',
        severity="critical",
        for_duration="1m",
        summary="MySQL connection error",
        description="Applications cannot connect to MySQL.",
    ),
    LogPattern(
        name="MysqlTooManyConnections",
        pattern='|= "Too many connections"',
        severity="critical",
        for_duration="0m",
        summary="MySQL too many connections",
        description="MySQL has reached max_connections limit.",
    ),
    LogPattern(
        name="MysqlDeadlock",
        pattern='|~ "Deadlock found|deadlock"',
        severity="warning",
        for_duration="0m",
        summary="MySQL deadlock detected",
        description="A deadlock was detected in MySQL.",
    ),
    LogPattern(
        name="MysqlSlowQuery",
        pattern='|~ "slow query|Query_time:"',
        severity="warning",
        for_duration="5m",
        summary="MySQL slow queries detected",
        description="Slow queries being logged. Review query performance.",
        threshold=5,
        window="5m",
    ),
    LogPattern(
        name="MysqlReplicationError",
        pattern='|~ "Slave.*error|replication.*error|Got fatal error"',
        severity="critical",
        for_duration="1m",
        summary="MySQL replication error",
        description="MySQL replication is experiencing errors.",
    ),
    LogPattern(
        name="MysqlTableCorruption",
        pattern='|~ "Table.*corrupt|Incorrect key file|crashed"',
        severity="critical",
        for_duration="0m",
        summary="MySQL table corruption detected",
        description="MySQL table corruption detected. Immediate action required.",
    ),
]

# RabbitMQ log patterns
RABBITMQ_PATTERNS = [
    LogPattern(
        name="RabbitmqConnectionError",
        pattern='|~ "connection.*closed|ECONNREFUSED|connection_closed"',
        severity="critical",
        for_duration="1m",
        summary="RabbitMQ connection error",
        description="Applications cannot connect to RabbitMQ.",
    ),
    LogPattern(
        name="RabbitmqNodeDown",
        pattern='|~ "node.*down|nodedown|rabbit.*stopped"',
        severity="critical",
        for_duration="0m",
        summary="RabbitMQ node down",
        description="A RabbitMQ node appears to be down.",
    ),
    LogPattern(
        name="RabbitmqMemoryAlarm",
        pattern='|~ "memory.*alarm|vm_memory_high_watermark"',
        severity="critical",
        for_duration="0m",
        summary="RabbitMQ memory alarm",
        description="RabbitMQ has triggered a memory alarm. Publishing blocked.",
    ),
    LogPattern(
        name="RabbitmqDiskAlarm",
        pattern='|~ "disk.*alarm|disk_free_limit"',
        severity="critical",
        for_duration="0m",
        summary="RabbitMQ disk alarm",
        description="RabbitMQ has triggered a disk alarm. Publishing blocked.",
    ),
    LogPattern(
        name="RabbitmqQueueOverflow",
        pattern='|~ "queue.*overflow|message.*dropped|queue.*limit"',
        severity="warning",
        for_duration="5m",
        summary="RabbitMQ queue overflow",
        description="RabbitMQ queue is overflowing. Messages may be dropped.",
    ),
    LogPattern(
        name="RabbitmqClusterPartition",
        pattern='|~ "partition|network.*partition|mnesia.*inconsistent"',
        severity="critical",
        for_duration="0m",
        summary="RabbitMQ cluster partition",
        description="RabbitMQ cluster partition detected. Split-brain possible.",
    ),
    LogPattern(
        name="RabbitmqAuthFailure",
        pattern='|~ "authentication.*fail|ACCESS_REFUSED|invalid credentials"',
        severity="warning",
        for_duration="5m",
        summary="RabbitMQ authentication failures",
        description="Authentication failures connecting to RabbitMQ.",
        threshold=5,
        window="5m",
    ),
]

# Nginx log patterns
NGINX_PATTERNS = [
    LogPattern(
        name="NginxError",
        pattern='|~ "\\\\[error\\\\]|\\\\[crit\\\\]|\\\\[alert\\\\]|\\\\[emerg\\\\]"',
        severity="warning",
        for_duration="5m",
        summary="Nginx errors detected",
        description="Nginx is logging error-level messages.",
        threshold=10,
        window="5m",
    ),
    LogPattern(
        name="NginxUpstreamTimeout",
        pattern='|~ "upstream timed out|upstream.*timeout"',
        severity="warning",
        for_duration="5m",
        summary="Nginx upstream timeouts",
        description="Nginx is experiencing upstream timeouts.",
        threshold=5,
        window="5m",
    ),
    LogPattern(
        name="NginxUpstreamUnavailable",
        pattern='|~ "no live upstreams|upstream.*unavailable|connect.*failed"',
        severity="critical",
        for_duration="1m",
        summary="Nginx upstream unavailable",
        description="Nginx cannot reach upstream servers.",
    ),
    LogPattern(
        name="Nginx5xxErrors",
        pattern='|~ "" 50[0-9] |" 5[0-9][0-9] "',
        severity="warning",
        for_duration="5m",
        summary="Nginx 5xx errors detected",
        description="Nginx is returning 5xx server errors.",
        threshold=10,
        window="5m",
    ),
    LogPattern(
        name="NginxHighLatency",
        pattern='|~ "request_time.*[0-9]{2,}\\\\."',
        severity="warning",
        for_duration="5m",
        summary="Nginx high latency requests",
        description="Nginx is serving slow requests (>10s).",
        threshold=5,
        window="5m",
    ),
    LogPattern(
        name="NginxConnectionLimit",
        pattern='|~ "limiting connections|worker_connections"',
        severity="critical",
        for_duration="0m",
        summary="Nginx connection limit reached",
        description="Nginx has reached its connection limit.",
    ),
    LogPattern(
        name="NginxSSLError",
        pattern='|~ "SSL.*error|certificate.*error|handshake.*failed"',
        severity="warning",
        for_duration="5m",
        summary="Nginx SSL errors",
        description="Nginx is experiencing SSL/TLS errors.",
        threshold=5,
        window="5m",
    ),
]

# NATS log patterns
NATS_PATTERNS = [
    LogPattern(
        name="NatsConnectionError",
        pattern='|~ "connection.*error|disconnect|ECONNREFUSED"',
        severity="critical",
        for_duration="1m",
        summary="NATS connection error",
        description="Clients cannot connect to NATS.",
    ),
    LogPattern(
        name="NatsSlowConsumer",
        pattern='|~ "slow consumer|Slow Consumer"',
        severity="warning",
        for_duration="5m",
        summary="NATS slow consumer detected",
        description="A NATS consumer is not keeping up with messages.",
    ),
    LogPattern(
        name="NatsAuthFailure",
        pattern='|~ "authentication.*fail|Authorization.*Violation"',
        severity="warning",
        for_duration="5m",
        summary="NATS authentication failures",
        description="Authentication failures connecting to NATS.",
        threshold=5,
        window="5m",
    ),
    LogPattern(
        name="NatsClusterError",
        pattern='|~ "route.*error|cluster.*error|peer.*disconnect"',
        severity="critical",
        for_duration="1m",
        summary="NATS cluster error",
        description="NATS cluster connectivity issues.",
    ),
    LogPattern(
        name="NatsStreamError",
        pattern='|~ "JetStream.*error|stream.*error|consumer.*error"',
        severity="warning",
        for_duration="5m",
        summary="NATS JetStream error",
        description="NATS JetStream is experiencing errors.",
    ),
]

# Pulsar log patterns
PULSAR_PATTERNS = [
    LogPattern(
        name="PulsarBrokerError",
        pattern='|~ "BrokerService.*error|broker.*exception"',
        severity="critical",
        for_duration="1m",
        summary="Pulsar broker error",
        description="Pulsar broker is experiencing errors.",
    ),
    LogPattern(
        name="PulsarBookkeeperError",
        pattern='|~ "BookKeeper.*error|bookie.*error|ledger.*error"',
        severity="critical",
        for_duration="1m",
        summary="Pulsar BookKeeper error",
        description="Pulsar storage layer is experiencing errors.",
    ),
    LogPattern(
        name="PulsarTopicError",
        pattern='|~ "topic.*error|Topic.*not found|subscription.*error"',
        severity="warning",
        for_duration="5m",
        summary="Pulsar topic error",
        description="Pulsar topic operations are failing.",
    ),
    LogPattern(
        name="PulsarBacklogGrowing",
        pattern='|~ "backlog.*growing|message.*backlog"',
        severity="warning",
        for_duration="10m",
        summary="Pulsar backlog growing",
        description="Pulsar message backlog is growing.",
    ),
    LogPattern(
        name="PulsarZookeeperError",
        pattern='|~ "ZooKeeper.*error|zk.*connection|metadata.*error"',
        severity="critical",
        for_duration="1m",
        summary="Pulsar ZooKeeper error",
        description="Pulsar cannot connect to ZooKeeper.",
    ),
]

# HAProxy log patterns
HAPROXY_PATTERNS = [
    LogPattern(
        name="HaproxyBackendDown",
        pattern='|~ "backend.*DOWN|Server.*is DOWN"',
        severity="critical",
        for_duration="0m",
        summary="HAProxy backend server down",
        description="An HAProxy backend server is down.",
    ),
    LogPattern(
        name="HaproxyConnectionError",
        pattern='|~ "Connection refused|connect.*timeout|ECONNREFUSED"',
        severity="critical",
        for_duration="1m",
        summary="HAProxy connection error",
        description="HAProxy cannot connect to backend servers.",
    ),
    LogPattern(
        name="Haproxy5xxErrors",
        pattern='|~ " 50[0-9] | 5[0-9][0-9] "',
        severity="warning",
        for_duration="5m",
        summary="HAProxy 5xx errors",
        description="HAProxy is returning 5xx server errors.",
        threshold=10,
        window="5m",
    ),
    LogPattern(
        name="HaproxyQueueFull",
        pattern='|~ "queue.*full|no server available"',
        severity="critical",
        for_duration="0m",
        summary="HAProxy queue full",
        description="HAProxy request queue is full.",
    ),
    LogPattern(
        name="HaproxyHighLatency",
        pattern='|~ "Tr:.*[0-9]{5,}|backend.*timeout"',
        severity="warning",
        for_duration="5m",
        summary="HAProxy high latency",
        description="HAProxy is experiencing high backend latency.",
        threshold=5,
        window="5m",
    ),
]

# Traefik log patterns
TRAEFIK_PATTERNS = [
    LogPattern(
        name="TraefikServiceError",
        pattern='|~ "service.*error|backend.*error|server.*error"',
        severity="critical",
        for_duration="1m",
        summary="Traefik service error",
        description="Traefik cannot reach backend service.",
    ),
    LogPattern(
        name="Traefik5xxErrors",
        pattern='|~ "" 50[0-9] |" 5[0-9][0-9] "',
        severity="warning",
        for_duration="5m",
        summary="Traefik 5xx errors",
        description="Traefik is returning 5xx server errors.",
        threshold=10,
        window="5m",
    ),
    LogPattern(
        name="TraefikCertificateError",
        pattern='|~ "certificate.*error|TLS.*error|ACME.*error"',
        severity="warning",
        for_duration="5m",
        summary="Traefik certificate error",
        description="Traefik is experiencing TLS certificate issues.",
    ),
    LogPattern(
        name="TraefikProviderError",
        pattern='|~ "provider.*error|configuration.*error|Docker.*error"',
        severity="warning",
        for_duration="5m",
        summary="Traefik provider error",
        description="Traefik configuration provider is failing.",
    ),
    LogPattern(
        name="TraefikRateLimitHit",
        pattern='|~ "rate.*limit|too many requests|429"',
        severity="warning",
        for_duration="5m",
        summary="Traefik rate limit hit",
        description="Clients are hitting Traefik rate limits.",
        threshold=10,
        window="5m",
    ),
]

# etcd log patterns
ETCD_PATTERNS = [
    LogPattern(
        name="EtcdLeaderChanged",
        pattern='|~ "elected leader|leader changed|lost leader"',
        severity="warning",
        for_duration="0m",
        summary="etcd leader changed",
        description="etcd cluster leader election occurred.",
    ),
    LogPattern(
        name="EtcdHighLatency",
        pattern='|~ "slow.*request|apply.*took too long|database.*slow"',
        severity="warning",
        for_duration="5m",
        summary="etcd high latency",
        description="etcd is experiencing slow operations.",
        threshold=5,
        window="5m",
    ),
    LogPattern(
        name="EtcdClusterError",
        pattern='|~ "cluster.*error|member.*error|peer.*error"',
        severity="critical",
        for_duration="1m",
        summary="etcd cluster error",
        description="etcd cluster communication error.",
    ),
    LogPattern(
        name="EtcdDiskError",
        pattern='|~ "disk.*error|quota.*exceeded|no space"',
        severity="critical",
        for_duration="0m",
        summary="etcd disk error",
        description="etcd is experiencing disk issues.",
    ),
    LogPattern(
        name="EtcdSnapshotError",
        pattern='|~ "snapshot.*failed|backup.*error"',
        severity="warning",
        for_duration="0m",
        summary="etcd snapshot failed",
        description="etcd snapshot/backup operation failed.",
    ),
]

# Consul log patterns
CONSUL_PATTERNS = [
    LogPattern(
        name="ConsulLeaderError",
        pattern='|~ "leader.*error|no cluster leader|leadership.*lost"',
        severity="critical",
        for_duration="1m",
        summary="Consul leader error",
        description="Consul cluster has no leader.",
    ),
    LogPattern(
        name="ConsulAgentError",
        pattern='|~ "agent.*error|agent.*failed|RPC.*error"',
        severity="warning",
        for_duration="5m",
        summary="Consul agent error",
        description="Consul agent is experiencing errors.",
    ),
    LogPattern(
        name="ConsulServiceDeregistered",
        pattern='|~ "deregister.*service|service.*critical|health.*critical"',
        severity="warning",
        for_duration="0m",
        summary="Consul service deregistered",
        description="A service was deregistered from Consul.",
    ),
    LogPattern(
        name="ConsulSerfError",
        pattern='|~ "serf.*error|memberlist.*error|gossip.*error"',
        severity="critical",
        for_duration="1m",
        summary="Consul Serf/gossip error",
        description="Consul cluster gossip protocol error.",
    ),
    LogPattern(
        name="ConsulACLError",
        pattern='|~ "ACL.*denied|permission.*denied|token.*error"',
        severity="warning",
        for_duration="5m",
        summary="Consul ACL error",
        description="Consul ACL permission errors.",
        threshold=5,
        window="5m",
    ),
]

# Application-level patterns (generic)
APPLICATION_PATTERNS = [
    LogPattern(
        name="ApplicationError",
        pattern='|~ "(?i)error|exception|fatal"',
        severity="warning",
        for_duration="5m",
        summary="Application errors detected",
        description="Error-level log entries detected in application logs.",
        threshold=10,
        window="5m",
    ),
    LogPattern(
        name="ApplicationPanic",
        pattern='|~ "(?i)panic|segfault|SIGSEGV"',
        severity="critical",
        for_duration="0m",
        summary="Application panic/crash detected",
        description="Application appears to have crashed or panicked.",
    ),
    LogPattern(
        name="ApplicationHighErrorRate",
        pattern='|~ "(?i)error|exception"',
        severity="critical",
        for_duration="5m",
        summary="High error rate in application",
        description="Application is experiencing a high rate of errors.",
        threshold=100,
        window="5m",
    ),
]

# All patterns organized by technology
LOG_PATTERNS: dict[str, list[LogPattern]] = {
    "postgresql": POSTGRESQL_PATTERNS,
    "postgres": POSTGRESQL_PATTERNS,
    "pg": POSTGRESQL_PATTERNS,
    "mysql": MYSQL_PATTERNS,
    "mariadb": MYSQL_PATTERNS,
    "redis": REDIS_PATTERNS,
    "kafka": KAFKA_PATTERNS,
    "kubernetes": KUBERNETES_PATTERNS,
    "k8s": KUBERNETES_PATTERNS,
    "mongodb": MONGODB_PATTERNS,
    "mongo": MONGODB_PATTERNS,
    "elasticsearch": ELASTICSEARCH_PATTERNS,
    "elastic": ELASTICSEARCH_PATTERNS,
    "rabbitmq": RABBITMQ_PATTERNS,
    "rabbit": RABBITMQ_PATTERNS,
    "nginx": NGINX_PATTERNS,
    "nats": NATS_PATTERNS,
    "pulsar": PULSAR_PATTERNS,
    "haproxy": HAPROXY_PATTERNS,
    "traefik": TRAEFIK_PATTERNS,
    "etcd": ETCD_PATTERNS,
    "consul": CONSUL_PATTERNS,
    "application": APPLICATION_PATTERNS,
    "api": APPLICATION_PATTERNS,
    "worker": APPLICATION_PATTERNS,
    "stream": APPLICATION_PATTERNS,
}


def get_patterns_for_technology(technology: str) -> list[LogPattern]:
    """Get log patterns for a specific technology.

    Args:
        technology: Technology name (e.g., "postgresql", "redis", "kafka")

    Returns:
        List of LogPattern objects for that technology
    """
    tech_lower = technology.lower()
    return LOG_PATTERNS.get(tech_lower, APPLICATION_PATTERNS)


def list_available_technologies() -> list[str]:
    """List all technologies with log patterns."""
    return sorted(set(LOG_PATTERNS.keys()))
