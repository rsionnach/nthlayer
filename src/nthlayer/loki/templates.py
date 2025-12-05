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
    "redis": REDIS_PATTERNS,
    "kafka": KAFKA_PATTERNS,
    "kubernetes": KUBERNETES_PATTERNS,
    "k8s": KUBERNETES_PATTERNS,
    "mongodb": MONGODB_PATTERNS,
    "mongo": MONGODB_PATTERNS,
    "elasticsearch": ELASTICSEARCH_PATTERNS,
    "elastic": ELASTICSEARCH_PATTERNS,
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
