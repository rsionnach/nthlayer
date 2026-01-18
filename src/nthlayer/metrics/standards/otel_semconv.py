"""
OpenTelemetry Semantic Conventions wrappers.

This module re-exports metric and attribute constants from the official
opentelemetry-semantic-conventions package. Using these constants ensures
our metric definitions stay in sync with the official OTel specifications.

Reference: https://opentelemetry.io/docs/specs/semconv/
Package: https://pypi.org/project/opentelemetry-semantic-conventions/
"""

from __future__ import annotations

# HTTP Metrics
from opentelemetry.semconv.metrics.http_metrics import (
    HTTP_CLIENT_REQUEST_DURATION,
    HTTP_SERVER_REQUEST_DURATION,
)

# DB Metrics
from opentelemetry.semconv.metrics.db_metrics import (
    DB_CLIENT_OPERATION_DURATION,
)

# HTTP Attributes
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
    HTTP_ROUTE,
)

# URL Attributes
from opentelemetry.semconv.attributes.url_attributes import (
    URL_SCHEME,
)

# DB Attributes
from opentelemetry.semconv.attributes.db_attributes import (
    DB_OPERATION_NAME,
)

# Alias for backward compatibility - OTel renamed db.system to db.system.name
DB_SYSTEM = "db.system"

# Server Attributes
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
)

# Error Attributes
from opentelemetry.semconv.attributes.error_attributes import (
    ERROR_TYPE,
)

# Legacy metrics from MetricInstruments (older schema)
from opentelemetry.semconv.metrics import MetricInstruments

# JVM Runtime metrics
JVM_MEMORY_USED = MetricInstruments.PROCESS_RUNTIME_JVM_MEMORY_USAGE
JVM_GC_DURATION = MetricInstruments.PROCESS_RUNTIME_JVM_GC_DURATION
JVM_THREADS_COUNT = MetricInstruments.PROCESS_RUNTIME_JVM_THREADS_COUNT
JVM_CLASSES_LOADED = MetricInstruments.PROCESS_RUNTIME_JVM_CLASSES_LOADED

# HTTP Server legacy metrics
HTTP_SERVER_ACTIVE_REQUESTS = MetricInstruments.HTTP_SERVER_ACTIVE_REQUESTS
HTTP_SERVER_REQUEST_SIZE = MetricInstruments.HTTP_SERVER_REQUEST_SIZE
HTTP_SERVER_RESPONSE_SIZE = MetricInstruments.HTTP_SERVER_RESPONSE_SIZE

# HTTP Client legacy metrics
HTTP_CLIENT_REQUEST_SIZE = MetricInstruments.HTTP_CLIENT_REQUEST_SIZE
HTTP_CLIENT_RESPONSE_SIZE = MetricInstruments.HTTP_CLIENT_RESPONSE_SIZE

# DB Client legacy metrics
DB_CLIENT_CONNECTIONS_USAGE = MetricInstruments.DB_CLIENT_CONNECTIONS_USAGE

__all__ = [
    # HTTP Metrics
    "HTTP_CLIENT_REQUEST_DURATION",
    "HTTP_SERVER_REQUEST_DURATION",
    # DB Metrics
    "DB_CLIENT_OPERATION_DURATION",
    # HTTP Attributes
    "HTTP_REQUEST_METHOD",
    "HTTP_RESPONSE_STATUS_CODE",
    "HTTP_ROUTE",
    # URL Attributes
    "URL_SCHEME",
    # DB Attributes
    "DB_SYSTEM",
    "DB_OPERATION_NAME",
    # Server Attributes
    "SERVER_ADDRESS",
    # Error Attributes
    "ERROR_TYPE",
    # JVM Runtime
    "JVM_MEMORY_USED",
    "JVM_GC_DURATION",
    "JVM_THREADS_COUNT",
    "JVM_CLASSES_LOADED",
    # HTTP Server legacy
    "HTTP_SERVER_ACTIVE_REQUESTS",
    "HTTP_SERVER_REQUEST_SIZE",
    "HTTP_SERVER_RESPONSE_SIZE",
    # HTTP Client legacy
    "HTTP_CLIENT_REQUEST_SIZE",
    "HTTP_CLIENT_RESPONSE_SIZE",
    # DB Client legacy
    "DB_CLIENT_CONNECTIONS_USAGE",
]
