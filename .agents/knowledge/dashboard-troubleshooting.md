# Dashboard Troubleshooting Guide

## Common Issues and Solutions

### 1. Dashboard Shows "No Data"

#### Check 1: Template Variables
**Symptom**: All panels show no data despite queries looking correct

**Diagnosis**:
```bash
# Check if template variable exists
curl -H "Authorization: Bearer $API_KEY" \
  "https://nthlayer.grafana.net/api/dashboards/uid/SERVICE-overview" \
  | jq '.dashboard.templating.list'
```

**Fix**:
```python
dashboard['templating'] = {
    "list": [{
        "name": "service",
        "type": "constant",
        "current": {"value": "service-name", "text": "service-name"},
        "hide": 2,
        "label": "Service",
        "query": "service-name"
    }]
}
```

**Why it happens**: Queries use `$service` but variable undefined, so Prometheus looks for literal `service="$service"` which doesn't exist.

#### Check 2: Metric Names
**Symptom**: Some panels work, others don't

**Diagnosis**:
```bash
# Check actual metric names in demo endpoint
curl -u nthlayer:PASSWORD https://nthlayer-demo.fly.dev/metrics \
  | grep "^metric_name"

# Check in Grafana Cloud  
curl -H "Authorization: Bearer $API_KEY" \
  "https://nthlayer.grafana.net/api/datasources/proxy/uid/grafanacloud-prom/api/v1/query?query=metric_name"
```

**Common mistakes**:
- ❌ `http_requests{` → ✅ `http_requests_total{`
- ❌ `code!~"5.."` → ✅ `status!~"5.."`
- ❌ `pg_table_bloat_ratio` → ✅ `pg_stat_user_tables_n_dead_tup`

#### Check 3: Service Type Mismatch
**Symptom**: Stream processor or worker dashboard shows no HTTP metrics

**Diagnosis**: Check service type in YAML:
```yaml
service:
  type: stream-processor  # or: worker, api
```

**Metrics by service type**:
- **API**: `http_requests_total`, `http_request_duration_seconds_bucket`
- **Stream**: `events_processed_total`, `event_processing_duration_seconds_bucket`
- **Worker**: `notifications_sent_total`, `notification_processing_duration_seconds_bucket`

**Fix**: Remove HTTP panels from stream/worker dashboards or update queries to service-specific metrics.

### 2. "Multiple queries using the same RefId is not allowed"

**Symptom**: Panel shows error message instead of data

**Diagnosis**: Panel has multiple queries with duplicate RefIds:
```json
"targets": [
  {"refId": "A", "expr": "query1"},
  {"refId": "A", "expr": "query2"}  // ❌ Duplicate!
]
```

**Fix**:
```python
for i, target in enumerate(panel['targets']):
    target['refId'] = chr(65 + i)  # A, B, C, D...
```

**Affected panels**:
- PostgreSQL Connections (current + max)
- Active Queries (active + idle)
- Transaction Rate (commits + rollbacks)
- Disk I/O (reads + hits)

### 3. Wrong Database Type

**Symptom**: All database panels show no data for a specific service

**Diagnosis**: Service uses different database than dashboard queries

**Example**: checkout-service uses **MySQL** but dashboard queries PostgreSQL metrics:
```promql
# ❌ This won't work for checkout-service
pg_stat_database_numbackends{service="checkout-service"}

# ✅ Should use
mysql_global_status_threads_connected{service="checkout-service"}
```

**Fix**: Remove incompatible database panels or add correct database template.

### 4. Advanced Metrics Not Available

**Symptom**: Basic metrics work but advanced ones don't

**Examples**:
- ❌ Redis: Evicted Keys, Network I/O, Slow Commands
- ❌ PostgreSQL: Index statistics, table-level metrics
- ❌ MongoDB: Collection-level stats

**Diagnosis**: These require full exporters (Redis Exporter, postgres_exporter, mongodb_exporter), not just basic Prometheus instrumentation.

**Fix**: Remove these panels or note they require specific exporter setup.

### 5. Dashboard Not Updated After Push

**Symptom**: Changes pushed but Grafana still shows old version

**Diagnosis**:
```bash
# Check version number
curl -H "Authorization: Bearer $API_KEY" \
  "https://nthlayer.grafana.net/api/dashboards/uid/SERVICE-overview" \
  | jq '.dashboard.version'
```

**Fixes**:
1. Hard refresh browser: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
2. Verify push succeeded (check version incremented)
3. Check payload has correct `dashboard` key:
```python
{"dashboard": {...}, "overwrite": True}
```

## Diagnostic Scripts

### Test All Panel Queries
```python
for panel in dashboard['panels']:
    for target in panel['targets']:
        expr = target['expr'].replace('$service', 'service-name')
        # Test query against Grafana Cloud
        response = requests.get(
            f"{GRAFANA_URL}/api/datasources/proxy/uid/grafanacloud-prom/api/v1/query",
            params={"query": expr}
        )
        # Check if returns data
```

### Verify Template Variables
```python
dashboard = get_dashboard_from_grafana(service)
vars = dashboard.get('templating', {}).get('list', [])
if not vars:
    print(f"❌ {service}: No template variables")
```

### Compare Local vs Cloud
```python
local = json.load(open(f"generated/{service}/dashboard-sdk.json"))
cloud = get_dashboard_from_grafana(service)

local_panels = len(local['dashboard']['panels'])
cloud_panels = len(cloud['panels'])

if local_panels != cloud_panels:
    print(f"⚠️  Panel count mismatch: local={local_panels}, cloud={cloud_panels}")
```

## Prevention

### Before Generating Dashboards
1. ✅ Verify service type matches metrics (API/stream/worker)
2. ✅ Check database type (PostgreSQL/MySQL/MongoDB)
3. ✅ Confirm metrics exist in demo endpoint
4. ✅ Use metric discovery to validate availability

### Before Pushing Dashboards
1. ✅ Run `fix_all_dashboard_queries.py` to catch common issues
2. ✅ Verify template variables present
3. ✅ Check RefIds unique in multi-query panels
4. ✅ Test sample queries against Grafana Cloud

### After Pushing Dashboards
1. ✅ Verify version incremented in Grafana Cloud
2. ✅ Hard refresh browser to see changes
3. ✅ Test 3-5 panels to confirm data displays
4. ✅ Check for error messages in panels

## Tools

- `fix_all_dashboard_queries.py` - Systematic query fixer
- `test_all_services_sdk.py` - Generate and validate dashboards
- `push_all_sdk_dashboards.py` - Deploy to Grafana Cloud
- Comprehensive audit script - Test every panel

## Related Documentation

- `.agents/sessions/2025-12-02-week2-dashboard-fixes.md` - Detailed troubleshooting session
- `DASHBOARD_AUDIT_RESULTS.md` - Known issues and limitations
- Issue #10 - Dashboard data display problems
