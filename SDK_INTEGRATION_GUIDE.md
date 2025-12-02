# Grafana Foundation SDK Integration Guide

**Date:** December 2, 2025  
**SDK Version:** 1759918510!10.1.0 (Grafana 10.1.0)

---

## Installation ✅ COMPLETE

```bash
pip install grafana-foundation-sdk
```

**Added to:** `pyproject.toml`

---

## Import Structure

### Correct Imports ✅

```python
# Dashboard and panels
from grafana_foundation_sdk.builders import dashboard, timeseries, stat, gauge

# Data sources
from grafana_foundation_sdk.builders import prometheus, loki

# JSON serialization
from grafana_foundation_sdk.cog.encoder import JSONEncoder
```

### ❌ Wrong (doesn't work)

```python
# These DON'T work:
from grafana_foundation_sdk import dashboard  # ❌
from grafana_foundation_sdk import cog.encoder  # ❌
```

---

## API Pattern

### Builder Pattern

All SDK objects use the **builder pattern** with fluent API:

```python
dash = (dashboard.Dashboard("Title")
    .uid("unique-id")
    .tags(["tag1", "tag2"])
    .editable()
    .time("now-6h", "now")
)

# Build to get model
dash_model = dash.build()
```

### Models vs Builders

- **Builders** = `.builders` module, fluent API, chainable methods
- **Models** = `.models` module, data classes, returned by `.build()`

```python
from grafana_foundation_sdk.builders import dashboard  # Builder
dash_builder = dashboard.Dashboard("Title")  # Builder instance
dash_model = dash_builder.build()  # Model instance (dashboard.Dashboard model)
```

---

## Core Components

### 1. Dashboard

```python
from grafana_foundation_sdk.builders import dashboard

dash = dashboard.Dashboard("My Dashboard")
dash.uid("my-dashboard")
dash.tags(["service", "production"])
dash.description("Service monitoring dashboard")
dash.editable()  # or .readonly()
dash.time("now-6h", "now")
dash.timezone("browser")  # or "UTC"

# Build the model
model = dash.build()
```

### 2. Panels

**Timeseries Panel:**
```python
from grafana_foundation_sdk.builders import timeseries

panel = timeseries.Panel()
panel.title("HTTP Requests")
panel.description("Request rate over time")
panel.unit("reqps")  # Requests per second
panel.min_val(0)  # Y-axis minimum

model = panel.build()
```

**Stat Panel:**
```python
from grafana_foundation_sdk.builders import stat

panel = stat.Panel()
panel.title("Error Rate")
panel.description("Current error percentage")
panel.unit("percent")
panel.color_mode("value")  # Color the value

model = panel.build()
```

**Gauge Panel:**
```python
from grafana_foundation_sdk.builders import gauge

panel = gauge.Panel()
panel.title("CPU Usage")
panel.description("Current CPU percentage")
panel.unit("percent")
panel.min_val(0)
panel.max_val(100)

model = panel.build()
```

### 3. Queries

**Prometheus:**
```python
from grafana_foundation_sdk.builders import prometheus

query = prometheus.Dataquery()
query.expr("rate(http_requests_total{service=\"$service\"}[5m])")
query.legend_format("{{method}} {{status}}")
query.interval("30s")

# Add to panel
panel.with_target(query)
```

### 4. JSON Serialization

```python
from grafana_foundation_sdk.cog.encoder import JSONEncoder
import json

# Build dashboard
dash_model = dashboard.Dashboard("Test").build()

# Serialize to JSON
encoder = JSONEncoder(sort_keys=False, indent=2)
json_str = encoder.encode(dash_model)

# Parse as dict
data = json.loads(json_str)
```

**Output:**
```json
{
  "title": "Test",
  "uid": null,
  "tags": [],
  "editable": true,
  "schemaVersion": 36,
  "style": "dark",
  "timezone": "browser",
  ...
}
```

---

## Complete Example

```python
from grafana_foundation_sdk.builders import dashboard, timeseries, prometheus
from grafana_foundation_sdk.cog.encoder import JSONEncoder

# Create dashboard
dash = dashboard.Dashboard("Payment API")
dash.uid("payment-api")
dash.tags(["payment", "api", "critical"])
dash.editable()
dash.time("now-6h", "now")

# Create timeseries panel
panel = timeseries.Panel()
panel.title("HTTP Requests/sec")
panel.description("Request rate by method")
panel.unit("reqps")

# Add Prometheus query
query = prometheus.Dataquery()
query.expr("rate(http_requests_total{service=\"payment-api\"}[5m])")
query.legend_format("{{method}}")

panel.with_target(query)

# Add panel to dashboard
dash.with_panel(panel)

# Build and serialize
dash_model = dash.build()
json_str = JSONEncoder(indent=2).encode(dash_model)

print(json_str)
```

---

## Key Features

### Type Safety ✅

```python
# IDE autocomplete works
dash = dashboard.Dashboard("Test")
dash.uid("test-uid")  # ✅ IDE suggests available methods
dash.invalid_method()  # ❌ IDE warns this doesn't exist
```

### Validation

```python
# SDK validates types at build time
dash.uid(123)  # ❌ TypeError: uid expects str
dash.uid("valid-uid")  # ✅ OK
```

### Official Grafana Compatibility

- Generated from Grafana OpenAPI spec
- Matches Grafana's exact JSON schema
- Auto-updated with Grafana releases

---

## Migration Strategy

### Phase 1: Create Adapter (NEXT)

Create `src/nthlayer/dashboards/sdk_adapter.py`:

```python
from grafana_foundation_sdk.builders import dashboard, timeseries, prometheus
from typing import List
from ..specs.models import ServiceContext, SLO

class SDKAdapter:
    """Converts NthLayer specs to Grafana Foundation SDK builders."""
    
    @staticmethod
    def create_dashboard(service: ServiceContext) -> dashboard.Dashboard:
        dash = dashboard.Dashboard(f"{service.name} - Service Dashboard")
        dash.uid(f"{service.name}-overview")
        dash.tags([service.team, service.tier, service.type])
        dash.editable()
        return dash
    
    @staticmethod
    def create_timeseries_panel(title: str, query_expr: str) -> timeseries.Panel:
        panel = timeseries.Panel()
        panel.title(title)
        
        query = prometheus.Dataquery()
        query.expr(query_expr)
        panel.with_target(query)
        
        return panel
```

### Phase 2: Update DashboardBuilder

Replace custom Panel/Target with SDK:

```python
# OLD (custom models)
from nthlayer.dashboards.models import Panel, Target

panel = Panel(
    title="HTTP Requests",
    targets=[Target(expr="rate(http_requests_total[5m])")]
)

# NEW (SDK)
from grafana_foundation_sdk.builders import timeseries, prometheus

panel_builder = timeseries.Panel()
panel_builder.title("HTTP Requests")

query = prometheus.Dataquery()
query.expr("rate(http_requests_total[5m])")
panel_builder.with_target(query)

panel_model = panel_builder.build()
```

### Phase 3: Serialize

```python
from grafana_foundation_sdk.cog.encoder import JSONEncoder

# All panels are SDK models
panels = [panel1.build(), panel2.build(), panel3.build()]

# Add to dashboard
dash = dashboard.Dashboard("Service")
for panel in panels:
    dash.with_panel(panel)

# Serialize
dash_model = dash.build()
json_str = JSONEncoder(indent=2).encode(dash_model)
```

---

## Benefits

| Before (Custom) | After (SDK) |
|----------------|-------------|
| Manual JSON construction | Type-safe builders |
| No validation | Build-time validation |
| Manual Grafana updates | Auto-updated with Grafana |
| Brittle | Official support |
| No IDE support | Full autocomplete |
| Runtime errors | Compile-time errors |

---

## Testing

```python
def test_sdk_dashboard():
    dash = dashboard.Dashboard("Test")
    dash.uid("test")
    model = dash.build()
    
    assert model.title == "Test"
    assert model.uid == "test"
    assert model.editable == True  # default
    
def test_sdk_json():
    dash = dashboard.Dashboard("Test").build()
    json_str = JSONEncoder().encode(dash)
    
    import json
    data = json.loads(json_str)
    assert data["title"] == "Test"
    assert "schemaVersion" in data
```

---

## Available Panel Types

From `grafana_foundation_sdk.builders`:

- `timeseries` - Time series graphs
- `stat` - Single stat value
- `gauge` - Gauge visualization  
- `table` - Table data
- `barchart` - Bar charts
- `heatmap` - Heatmaps
- `piechart` - Pie charts
- `logs` - Log panels
- `candlestick` - Candlestick charts

---

## Available Data Sources

From `grafana_foundation_sdk.builders`:

- `prometheus` - Prometheus queries
- `loki` - Loki log queries
- `elasticsearch` - Elasticsearch
- `cloudwatch` - AWS CloudWatch
- `tempo` - Tempo traces
- `testdata` - Test data source

---

## Next Steps

1. ✅ SDK installed and tested
2. ⏳ Create SDK adapter (`sdk_adapter.py`)
3. ⏳ Update DashboardBuilder to use SDK
4. ⏳ Migrate technology templates
5. ⏳ Test all 5 dashboards
6. ⏳ Validate JSON compatibility

---

## References

- [Grafana Foundation SDK GitHub](https://github.com/grafana/grafana-foundation-sdk)
- [Python SDK Docs](https://grafana.github.io/grafana-foundation-sdk/python/)
- [Grafana Dashboard Schema](https://grafana.com/docs/grafana/latest/dashboards/json-model/)

---

**Status:** SDK installation COMPLETE ✅  
**Next:** Create adapter layer
