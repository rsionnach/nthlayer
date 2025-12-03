#!/usr/bin/env python3
"""
Fix all dashboard queries to match actual emitted metrics
"""
import json
from pathlib import Path

def fix_checkout_service():
    """checkout-service uses MySQL, RabbitMQ, ECS (NOT Redis or Kubernetes)"""
    with open('generated/checkout-service/dashboard.json', 'r') as f:
        data = json.load(f)
    
    dashboard = data['dashboard']
    panels_to_remove = []
    
    for i, panel in enumerate(dashboard['panels']):
        if panel.get('type') == 'row':
            continue
        
        # Remove Redis panels (checkout doesn't use Redis)
        if panel.get('id') in [10, 11, 12]:  # Redis panels
            panels_to_remove.append(i)
        
        # Remove Kubernetes panels (checkout uses ECS)
        if panel.get('id') in [13, 14, 15]:  # Kubernetes panels
            panels_to_remove.append(i)
    
    # Remove in reverse order to maintain indices
    for i in sorted(panels_to_remove, reverse=True):
        del dashboard['panels'][i]
    
    # Add MySQL panels
    mysql_panels = [
        {
            "id": 20,
            "title": "MySQL Connections",
            "type": "timeseries",
            "targets": [{
                "expr": "mysql_global_status_threads_connected{service=\"$service\"}",
                "legendFormat": "Active connections",
                "refId": "A"
            }, {
                "expr": "mysql_global_variables_max_connections{service=\"$service\"}",
                "legendFormat": "Max connections",
                "refId": "B"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 19},
            "description": "MySQL active connections vs max",
            "fieldConfig": {"defaults": {"unit": "short"}}
        },
        {
            "id": 21,
            "title": "MySQL Queries/sec",
            "type": "timeseries",
            "targets": [{
                "expr": "rate(mysql_global_status_queries_total{service=\"$service\"}[5m])",
                "legendFormat": "Queries/sec",
                "refId": "A"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 19},
            "description": "MySQL queries per second",
            "fieldConfig": {"defaults": {"unit": "qps"}}
        },
        {
            "id": 22,
            "title": "RabbitMQ Queue Depth",
            "type": "timeseries",
            "targets": [{
                "expr": "rabbitmq_queue_messages{service=\"$service\",queue=\"order_queue\"}",
                "legendFormat": "Messages in queue",
                "refId": "A"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 27},
            "description": "RabbitMQ order queue depth",
            "fieldConfig": {"defaults": {"unit": "short"}}
        },
        {
            "id": 23,
            "title": "RabbitMQ Publish Rate",
            "type": "timeseries",
            "targets": [{
                "expr": "rate(rabbitmq_queue_messages_published_total{service=\"$service\",queue=\"order_queue\"}[5m])",
                "legendFormat": "Messages/sec",
                "refId": "A"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 27},
            "description": "Messages published per second",
            "fieldConfig": {"defaults": {"unit": "msgs/s"}}
        },
        {
            "id": 24,
            "title": "ECS Running Tasks",
            "type": "stat",
            "targets": [{
                "expr": "ecs_service_running_count{service=\"$service\",cluster=\"production\"}",
                "legendFormat": "Running tasks",
                "refId": "A"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 35},
            "description": "Number of running ECS tasks",
            "fieldConfig": {"defaults": {"unit": "short"}}
        },
        {
            "id": 25,
            "title": "ECS CPU Utilization",
            "type": "timeseries",
            "targets": [{
                "expr": "ecs_task_cpu_utilization{service=\"$service\"}",
                "legendFormat": "{{task}}",
                "refId": "A"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 35},
            "description": "CPU utilization per ECS task",
            "fieldConfig": {"defaults": {"unit": "percent"}}
        }
    ]
    
    dashboard['panels'].extend(mysql_panels)
    
    with open('generated/checkout-service/dashboard.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Fixed checkout-service: Added MySQL, RabbitMQ, ECS panels")

def fix_notification_worker():
    """notification-worker is a worker, not an API (no HTTP metrics)"""
    with open('generated/notification-worker/dashboard.json', 'r') as f:
        data = json.load(f)
    
    dashboard = data['dashboard']
    
    for panel in dashboard['panels']:
        if panel.get('type') == 'row':
            continue
        
        # Fix SLO panels - use notification metrics instead of HTTP
        if panel.get('id') == 2:  # Delivery-Success SLO
            panel['targets'][0]['expr'] = 'sum(rate(notifications_sent_total{service="$service",status="delivered"}[5m])) / sum(rate(notifications_sent_total{service="$service"}[5m])) * 100'
        
        if panel.get('id') == 3:  # Processing-Latency-P95 SLO
            panel['targets'][0]['expr'] = 'histogram_quantile(0.95, rate(notification_processing_duration_seconds_bucket{service="$service"}[5m])) * 1000'
        
        # Fix Service Health panels - use notification metrics
        if panel.get('id') == 6:  # Request Rate -> Notification Rate
            panel['title'] = 'Notification Rate'
            panel['description'] = 'Notifications sent per second'
            panel['targets'][0]['expr'] = 'sum(rate(notifications_sent_total{service="$service"}[5m]))'
            panel['targets'][0]['legendFormat'] = 'Notifications/sec'
        
        if panel.get('id') == 7:  # Error Rate
            panel['title'] = 'Notification Failure Rate'
            panel['targets'][0]['expr'] = 'sum(rate(notifications_sent_total{service="$service",status="failed"}[5m])) / sum(rate(notifications_sent_total{service="$service"}[5m])) * 100'
        
        if panel.get('id') == 8:  # Response Time -> Processing Time
            panel['title'] = 'Processing Time (p95)'
            panel['description'] = '95th percentile notification processing time'
            panel['targets'][0]['expr'] = 'histogram_quantile(0.95, rate(notification_processing_duration_seconds_bucket{service="$service"}[5m])) * 1000'
        
        # Add Kafka lag panel
        if panel.get('id') == 11:  # Replace Cache Hit Rate with Kafka Lag
            panel['title'] = 'Kafka Consumer Lag'
            panel['description'] = 'Lag in seconds behind latest messages'
            panel['type'] = 'timeseries'
            panel['targets'][0]['expr'] = 'kafka_consumer_lag_seconds{service="$service",topic="notifications"}'
            panel['targets'][0]['legendFormat'] = 'Lag (seconds)'
            panel['fieldConfig']['defaults']['unit'] = 's'
        
        if panel.get('id') == 12:  # Replace Commands/sec with Kafka throughput
            panel['title'] = 'Kafka Offset Progress'
            panel['description'] = 'Message offset progression per partition'
            panel['targets'][0]['expr'] = 'kafka_consumer_offset_total{service="$service",topic="notifications"}'
            panel['targets'][0]['legendFormat'] = 'Partition {{partition}}'
    
    with open('generated/notification-worker/dashboard.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Fixed notification-worker: Replaced HTTP with notification metrics")

def fix_identity_service():
    """identity-service uses ECS, not Kubernetes"""
    with open('generated/identity-service/dashboard.json', 'r') as f:
        data = json.load(f)
    
    dashboard = data['dashboard']
    panels_to_remove = []
    
    for i, panel in enumerate(dashboard['panels']):
        if panel.get('type') == 'row':
            continue
        
        # Remove Kubernetes panels (identity uses ECS)
        if panel.get('id') in [16, 17, 18]:  # Kubernetes panels
            panels_to_remove.append(i)
        
        # Remove Redis cache hit rate panel (we have Redis memory but not keyspace_hits)
        if panel.get('id') == 14:
            panel['title'] = 'Redis Keys'
            panel['description'] = 'Number of keys in Redis'
            panel['targets'][0]['expr'] = 'redis_db_keys{service="$service",db="0"}'
            panel['targets'][0]['legendFormat'] = 'Keys'
            panel['type'] = 'stat'
        
        if panel.get('id') == 15:  # Remove Commands/sec
            panels_to_remove.append(i)
    
    # Remove panels
    for i in sorted(panels_to_remove, reverse=True):
        del dashboard['panels'][i]
    
    # Add ECS panels
    ecs_panels = [
        {
            "id": 30,
            "title": "ECS Running Tasks",
            "type": "stat",
            "targets": [{
                "expr": "ecs_service_running_count{service=\"$service\",cluster=\"production\"}",
                "legendFormat": "Running tasks",
                "refId": "A"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 27},
            "description": "Number of running ECS tasks",
            "fieldConfig": {"defaults": {"unit": "short"}}
        },
        {
            "id": 31,
            "title": "ECS CPU Utilization",
            "type": "timeseries",
            "targets": [{
                "expr": "ecs_task_cpu_utilization{service=\"$service\"}",
                "legendFormat": "{{task}}",
                "refId": "A"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 27},
            "description": "CPU utilization per ECS task",
            "fieldConfig": {"defaults": {"unit": "percent"}}
        }
    ]
    
    dashboard['panels'].extend(ecs_panels)
    
    with open('generated/identity-service/dashboard.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Fixed identity-service: Replaced Kubernetes with ECS panels")

if __name__ == '__main__':
    fix_checkout_service()
    fix_notification_worker()
    fix_identity_service()
    print("\n✅ All dashboards fixed! Ready to push to Grafana.")
