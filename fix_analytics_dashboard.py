import json

# Load current dashboard
with open('generated/analytics-stream/dashboard.json', 'r') as f:
    data = json.load(f)

dashboard = data['dashboard']

# Find and fix panels
for panel in dashboard['panels']:
    if panel.get('type') == 'row':
        continue
        
    # Fix SLO panels
    if panel.get('id') == 2:  # Processing-Availability SLO
        panel['targets'][0]['expr'] = 'sum(rate(events_processed_total{service="$service",status="success"}[5m])) / sum(rate(events_processed_total{service="$service"}[5m])) * 100'
    
    if panel.get('id') == 4:  # Event-Latency-P99 SLO
        panel['targets'][0]['expr'] = 'histogram_quantile(0.50, rate(event_processing_duration_seconds_bucket{service="$service"}[5m])) * 1000'
        if len(panel['targets']) > 1:
            panel['targets'][1]['expr'] = 'histogram_quantile(0.95, rate(event_processing_duration_seconds_bucket{service="$service"}[5m])) * 1000'
        if len(panel['targets']) > 2:
            panel['targets'][2]['expr'] = 'histogram_quantile(0.99, rate(event_processing_duration_seconds_bucket{service="$service"}[5m])) * 1000'
    
    # Fix Service Health panels
    if panel.get('id') == 6:  # Request Rate -> Event Rate
        panel['title'] = 'Event Processing Rate'
        panel['description'] = 'Events processed per second'
        panel['targets'][0]['expr'] = 'sum(rate(events_processed_total{service="$service"}[5m]))'
        panel['targets'][0]['legendFormat'] = 'Events/sec'
    
    if panel.get('id') == 7:  # Error Rate
        panel['title'] = 'Event Error Rate'
        panel['description'] = 'Percentage of events that failed processing'
        panel['targets'][0]['expr'] = 'sum(rate(events_processed_total{service="$service",status="error"}[5m])) / sum(rate(events_processed_total{service="$service"}[5m])) * 100'
    
    if panel.get('id') == 8:  # Response Time -> Processing Time
        panel['title'] = 'Event Processing Time (p95)'
        panel['description'] = '95th percentile event processing duration'
        panel['targets'][0]['expr'] = 'histogram_quantile(0.95, rate(event_processing_duration_seconds_bucket{service="$service"}[5m])) * 1000'

# Write back
with open('generated/analytics-stream/dashboard.json', 'w') as f:
    json.dump(data, f, indent=2)

print("✅ Fixed analytics-stream dashboard queries")
