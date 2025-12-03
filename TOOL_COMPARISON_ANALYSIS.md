# Comparison: NthLayer vs Existing Dashboard Generation Tools

**Date:** December 2, 2025  
**Purpose:** Evaluate whether existing tools solve NthLayer's architectural challenges  
**Context:** After discovering 51% fix rate and validation issues in demo implementation

---

## Executive Summary

This document compares NthLayer's current architecture against 4 mature open-source tools for programmatic Grafana dashboard generation. The analysis reveals that **metric discovery (autograf)** combined with **official SDKs (Grafana Foundation SDK)** could solve our core challenges while preserving NthLayer's service-level abstractions.

**Key Recommendation:** Adopt a hybrid approach using Grafana Foundation SDK for generation and autograf-style metric discovery for validation.

---

## Tools Analyzed

| Tool | Stars | Language | Approach | Last Update | License |
|------|-------|----------|----------|-------------|---------|
| [grafana-dashboard-builder](https://github.com/jakubplichta/grafana-dashboard-builder) | 154 | Python | YAML templates | Nov 2025 | Apache 2.0 |
| [autograf](https://github.com/FUSAKLA/autograf) | 154 | Go | Metric discovery | Jul 2025 | Apache 2.0 |
| [Grafana Foundation SDK](https://github.com/grafana/grafana-foundation-sdk) | Official | Multi-lang | Programmatic builders | Active | Apache 2.0 |
| [grafanalib](https://github.com/weaveworks/grafanalib) | 1.8k | Python | Python DSL | Active | Apache 2.0 |

---

## 1. grafana-dashboard-builder

### Overview
Python tool that generates Grafana dashboards from YAML templates. Very similar conceptually to NthLayer's current approach.

### Architecture
```yaml
# Component definition
- name: graph-name
  panels:
    - graph:
        target: target
        y_formats: [bytes, short]
        span: 4

# Dashboard using components
- name: overview
  dashboard:
    title: overview dashboard
    rows:
      - row-name
```

### What They Do Well
1. **Component reuse** - Clean separation of panels, rows, templates
2. **Project-level parameterization** - One template, multiple dashboards
3. **Multiple exporters** - File, ElasticSearch, Grafana API
4. **10 years mature** - Battle-tested with 420 commits

### What They Struggle With
1. **Same problem as us** - Templates assume specific metric schemas
2. **No validation** - Dashboards can reference non-existent metrics
3. **Manual maintenance** - Each Grafana version needs template updates
4. **Limited technology coverage** - Mostly Graphite/Prometheus basics

### Could We Use It?

**Pros:**
- Apache 2.0 license - could fork
- Similar Python stack
- Proven YAML schema patterns we could adopt

**Cons:**
- Doesn't solve our core problem (template brittleness)
- Would inherit their maintenance burden
- No service-level abstractions (SLOs, dependencies)

**Verdict:** ❌ **Don't adopt** - Same architectural challenges we have

---

## 2. autograf (★ MOST INTERESTING)

### Overview
**THIS IS THE GAME CHANGER.** Autograf generates dashboards by **discovering actual metrics** from Prometheus, not predicting them.

### How It Works

```bash
# Fetch ALL metrics matching selector from live Prometheus
autograf --prometheus-url https://prometheus.io \
         --selector '{app="payment-api"}' \
         --grafana-url https://grafana.io
```

**The Magic:**
1. Queries Prometheus: `group({app="payment-api"}) by (__name__)`
2. Gets actual metric list: `http_requests_total`, `pg_stat_database_blks_hit`, etc.
3. Classifies by type: Counter, Gauge, Histogram, Summary
4. Groups by metric prefix: `http_*`, `pg_*`, `redis_*`
5. Generates optimized panels for each metric type
6. Uploads to Grafana

### What They Do Brilliantly

**1. Zero Template Maintenance**
```go
// autograf/generate.go
func GenerateDashboard(metrics []Metric) Dashboard {
    // Group metrics by prefix
    groups := groupByPrefix(metrics)
    
    for prefix, metricList := range groups {
        // Create panel based on actual metric type
        panel := createPanelForType(metricList[0].Type)
    }
}
```

No templates to maintain! Dashboard adapts to actual metrics.

**2. Metric Type Intelligence**
```go
func createPanelForType(metricType string) Panel {
    switch metricType {
    case "counter":
        return TimeSeriesPanel{
            Expr: "rate(metric[5m])",  // Auto-add rate()
        }
    case "histogram":
        return HeatmapPanel{
            Expr: "histogram_quantile(0.95, sum by (le) (...))", 
        }
    case "gauge":
        return StatPanel{
            Expr: "metric",  // No rate needed
        }
    }
}
```

**3. Self-Validating**
- Only creates panels for metrics that exist
- Impossible to have "no data" panels
- Works with any exporter version

### What They DON'T Do
- No SLO support
- No service-level abstractions
- No dependency intelligence (doesn't know PostgreSQL vs Redis)
- Basic grouping only (by metric name prefix)

### Could We Use It?

**Integration Strategy:**

```python
# NthLayer + autograf hybrid
class NthLayerDashboardGenerator:
    def generate(self, service_spec):
        # 1. Use NthLayer to determine WHAT to monitor
        dependencies = service_spec.dependencies  # PostgreSQL, Redis
        slos = service_spec.slos                   # Availability, Latency
        
        # 2. Use autograf to discover ACTUAL metrics
        discovered_metrics = autograf.discover_metrics(
            prometheus_url=config.prometheus_url,
            selector=f'{{service="{service_spec.name}"}}'
        )
        
        # 3. Classify discovered metrics by technology
        pg_metrics = [m for m in discovered_metrics if m.startswith('pg_')]
        redis_metrics = [m for m in discovered_metrics if 'redis' in m or 'cache' in m]
        
        # 4. Generate panels using autograf's logic
        panels = []
        panels.extend(autograf.generate_panels(pg_metrics, technology='postgresql'))
        panels.extend(autograf.generate_panels(redis_metrics, technology='redis'))
        
        # 5. Add NthLayer SLO panels
        panels.extend(self.generate_slo_panels(slos, discovered_metrics))
        
        return Dashboard(panels=panels)
```

**Verdict:** ✅ **ADOPT METRIC DISCOVERY PATTERN** - Solves our core validation problem

---

## 3. Grafana Foundation SDK (Official)

### Overview
Official Grafana SDK for programmatically building dashboards in Go, TypeScript, Python, Java, PHP.

### Architecture

**Go Example:**
```go
import (
    "github.com/grafana/grafana-foundation-sdk/go/dashboard"
    "github.com/grafana/grafana-foundation-sdk/go/timeseries"
)

func CreateDashboard() *dashboard.Dashboard {
    return dashboard.New("My Dashboard").
        WithPanel(
            timeseries.NewPanel().
                WithTitle("HTTP Requests").
                WithTarget(
                    prometheus.NewQuery().
                        WithExpr("rate(http_requests_total[5m])").
                        Build(),
                ).
                Build(),
        ).
        Build()
}
```

**Python Example:**
```python
from grafana_foundation_sdk import dashboard, timeseries, prometheus

dash = (dashboard.Dashboard("My Dashboard")
    .with_panel(
        timeseries.Panel("HTTP Requests")
            .with_target(
                prometheus.Query()
                    .with_expr("rate(http_requests_total[5m])")
            )
    )
)
```

### What They Do Well

**1. Type Safety**
```python
# This WON'T compile - catches errors early
panel = timeseries.Panel(123)  # TypeError: expected str, got int

# This WON'T work - catches invalid configurations
panel.with_unit("invalid_unit")  # ValueError: unknown unit
```

**2. Official Support**
- Updates with every Grafana release
- Guaranteed compatibility
- No JSON schema breakage

**3. Multi-Language**
- Same API across Go, Python, TypeScript, Java, PHP
- Can switch implementation languages

**4. Builder Pattern**
```python
dashboard.Dashboard("title")
    .with_uid("unique-id")
    .with_tags(["tag1", "tag2"])
    .with_panel(...)
    .with_variable(...)
```
Clean, fluent, discoverable API.

### What They DON'T Do
- No high-level abstractions (you still write queries manually)
- No metric discovery
- No validation
- No technology templates

### Could We Use It?

**Integration Strategy:**

```python
# Replace our current Panel/Target models with Foundation SDK
from grafana_foundation_sdk import dashboard, timeseries
from nthlayer.specs import ServiceSpec

class NthLayerGenerator:
    def generate_dashboard(self, service: ServiceSpec):
        # Use Foundation SDK for dashboard structure
        dash = dashboard.Dashboard(f"{service.name} Overview")
        
        # NthLayer provides intelligent panel selection
        for dependency in service.dependencies:
            if dependency.type == 'postgresql':
                # Use Foundation SDK for panel creation
                dash.with_panel(
                    timeseries.Panel("PostgreSQL Connections")
                        .with_target(prometheus.Query()
                            .with_expr(f'pg_stat_database_numbackends{{service="{service.name}"}}'))
                )
        
        # Foundation SDK handles JSON generation
        return dash.to_json()
```

**Verdict:** ✅ **ADOPT AS DASHBOARD BUILDER** - Replaces our Panel/Target models with official SDK

---

## 4. grafanalib

### Overview
Python DSL for building Grafana dashboards. Most mature Python solution (1.8k stars, Weaveworks).

### Architecture

```python
from grafanalib.core import (
    Dashboard, TimeSeries, Target, Templating
)

dashboard = Dashboard(
    title="Example Dashboard",
    panels=[
        TimeSeries(
            title="HTTP Requests",
            targets=[
                Target(
                    expr='rate(http_requests_total[5m])',
                    legendFormat='{{method}} {{status}}',
                )
            ],
        ),
    ],
    templating=Templating(
        list=[
            Template(
                name='service',
                query='label_values(up, service)',
            )
        ]
    ),
).auto_panel_ids()
```

### What They Do Well

**1. Pythonic API**
```python
# Very clean, native Python feel
from grafanalib.core import *

dashboard = Dashboard(
    title="My Dashboard",
    tags=['production'],
    timezone='UTC',
    panels=[...],
)
```

**2. Template Library**
```python
from grafanalib.prometheus import PromGraph

# Pre-built Prometheus graph with sensible defaults
graph = PromGraph(
    title="CPU Usage",
    expressions=['rate(cpu_seconds_total[5m])'],
)
```

**3. Composability**
```python
def create_http_panel(service):
    return TimeSeries(
        title=f"{service} HTTP Requests",
        targets=[Target(expr=f'http_requests{{service="{service}"}}')] 
    )

# Reuse across dashboards
dashboards = [
    Dashboard(panels=[create_http_panel("api-1")]),
    Dashboard(panels=[create_http_panel("api-2")]),
]
```

**4. Mature Ecosystem**
- 8+ years development
- Used by Weaveworks in production
- Comprehensive docs

### What They DON'T Do
- No metric discovery
- No validation
- Templates still assume metric schemas
- No SLO abstractions

### Could We Use It?

**Comparison with Foundation SDK:**

| Feature | grafanalib | Foundation SDK |
|---------|------------|----------------|
| Official support | ❌ Community | ✅ Grafana Labs |
| Type safety | ❌ Runtime only | ✅ Compile-time |
| Multi-language | ❌ Python only | ✅ 5+ languages |
| Maturity | ✅ 8 years | ⚠️ 1 year |
| Pythonic API | ✅ Excellent | ⚠️ Generated |
| Breaking changes | ⚠️ Community-dependent | ✅ Versioned |

**Verdict:** ⚠️ **Consider as alternative to Foundation SDK** - More mature but less official

---

## Comparative Analysis

### Solving Our Core Problems

| Problem | grafana-dashboard-builder | autograf | Foundation SDK | grafanalib | NthLayer (current) |
|---------|---------------------------|----------|----------------|------------|-------------------|
| Template brittleness | ❌ Same issue | ✅ No templates | ⚠️ Doesn't address | ❌ Same issue | ❌ Same issue |
| Validation | ❌ None | ✅ Built-in | ❌ None | ❌ None | ⚠️ External scripts |
| Metric discovery | ❌ No | ✅ Core feature | ❌ No | ❌ No | ❌ No |
| Type safety | ❌ YAML only | ⚠️ Go types | ✅ Strong typing | ⚠️ Runtime | ⚠️ Pydantic |
| SLO support | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Yes |
| Service abstractions | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Yes |
| Tech templates | ⚠️ Basic | ❌ None | ❌ No | ⚠️ Some | ✅ 7 templates |

### Architecture Comparison

**NthLayer Current:**
```
Service YAML → Templates → Panel Models → JSON → Grafana
                ↓
          (validation external)
```

**autograf:**
```
Prometheus → Metric Discovery → Auto-classify → Generate Panels → Grafana
                                      ↓
                            (validation built-in)
```

**Foundation SDK:**
```
Code → Type-safe Builders → JSON → Grafana
         ↓
   (compile-time validation)
```

**grafana-dashboard-builder:**
```
YAML Templates → Components → JSON → Grafana
                      ↓
              (no validation)
```

---

## Recommended Hybrid Architecture

### The Winning Combination

```
NthLayer Service Spec (YAML)
         ↓
    Service Intelligence Layer (NthLayer)
    - Understand SLOs, dependencies, service types
         ↓
    Metric Discovery Layer (autograf pattern)
    - Query Prometheus for actual metrics
    - Classify by technology and type
         ↓
    Dashboard Generation Layer (Foundation SDK)
    - Type-safe panel creation
    - Official Grafana compatibility
         ↓
    Grafana Dashboard (JSON)
```

### Implementation Plan

**Phase 1: Integrate Foundation SDK (Week 1)**
```python
# Replace src/nthlayer/dashboards/models.py
from grafana_foundation_sdk import dashboard, timeseries, prometheus

class NthLayerBuilder:
    def __init__(self):
        self.sdk_dashboard = dashboard.Dashboard()
    
    def add_panel(self, title, expr):
        panel = timeseries.Panel(title).with_target(
            prometheus.Query().with_expr(expr)
        )
        self.sdk_dashboard.with_panel(panel)
```

**Phase 2: Add Metric Discovery (Week 2)**
```python
from prometheus_api_client import PrometheusConnect

class MetricDiscovery:
    def discover(self, service_name):
        # Query Prometheus for all metrics
        prom = PrometheusConnect(url=config.prometheus_url)
        metrics = prom.custom_query(f'group({{service="{service_name}"}}) by (__name__)')
        
        # Classify by technology
        return {
            'postgresql': [m for m in metrics if m['__name__'].startswith('pg_')],
            'redis': [m for m in metrics if 'redis' in m['__name__']],
            'http': [m for m in metrics if m['__name__'].startswith('http_')],
        }
```

**Phase 3: Intelligent Panel Generation (Week 3)**
```python
class IntelligentGenerator:
    def generate_panels_for_technology(self, technology, discovered_metrics):
        # Use autograf-style classification
        counters = [m for m in discovered_metrics if m.type == 'counter']
        gauges = [m for m in discovered_metrics if m.type == 'gauge']
        histograms = [m for m in discovered_metrics if m.type == 'histogram']
        
        panels = []
        
        # Generate appropriate panels for each type
        for metric in counters:
            panels.append(self.create_counter_panel(metric))
        
        for metric in histograms:
            panels.append(self.create_histogram_panel(metric))
        
        return panels
```

### Benefits of Hybrid Approach

**✅ Solves Template Brittleness**
- Metric discovery eliminates guessing
- Dashboards always match reality

**✅ Maintains NthLayer Value**
- Service-level abstractions (SLOs, dependencies)
- Intelligent panel selection
- Technology awareness

**✅ Leverages Official SDK**
- Type safety
- Guaranteed Grafana compatibility
- Future-proof

**✅ Built-in Validation**
- Can't generate panels for non-existent metrics
- Compile-time + runtime checks

---

## Code Examples

### Current NthLayer Approach (Brittle)

```python
# src/nthlayer/dashboards/templates/redis.py
def _memory_usage_panel(self, service: str) -> Panel:
    return Panel(
        title="Redis Memory Usage",
        targets=[
            Target(
                # PROBLEM: Assumes redis_memory_max_bytes exists
                expr=f'redis_memory_max_bytes{{service="{service}"}}',
            )
        ],
    )
```

### Hybrid Approach (Robust)

```python
from grafana_foundation_sdk import timeseries, prometheus
from nthlayer.discovery import MetricDiscovery

class RedisDashboardGenerator:
    def __init__(self, service_name):
        self.service = service_name
        self.discovery = MetricDiscovery()
    
    def generate_panels(self):
        # 1. Discover actual Redis metrics
        redis_metrics = self.discovery.discover_redis_metrics(self.service)
        
        panels = []
        
        # 2. Only create panels for metrics that exist
        if 'redis_memory_used_bytes' in redis_metrics:
            panels.append(
                timeseries.Panel("Redis Memory")
                    .with_target(
                        prometheus.Query()
                            .with_expr(f'redis_memory_used_bytes{{service="{self.service}"}}')
                    )
            )
        
        if 'cache_hits_total' in redis_metrics:
            # Calculate hit rate from actual metrics
            panels.append(
                timeseries.Panel("Cache Hit Rate")
                    .with_target(
                        prometheus.Query()
                            .with_expr(
                                f'sum(rate(cache_hits_total{{service="{self.service}"}}[5m])) / '
                                f'(sum(rate(cache_hits_total{{service="{self.service}"}}[5m])) + '
                                f'sum(rate(cache_misses_total{{service="{self.service}"}}[5m])))'
                            )
                    )
            )
        
        return panels
```

**Why This Works:**
- ✅ No assumptions about metric names
- ✅ Adapts to actual exporter
- ✅ Self-validating
- ✅ Type-safe with Foundation SDK

---

## Migration Path

### Option 1: Big Bang (Not Recommended)
Replace everything in one PR. Risky, hard to test.

### Option 2: Gradual Migration (Recommended)

**Week 1: Proof of Concept**
- Build one dashboard (payment-api) using hybrid approach
- Compare output quality to current approach
- Measure development time

**Week 2: Parallel Implementation**
- Keep existing system running
- Add `--experimental-hybrid` flag
- Generate dashboards both ways, compare

**Week 3: Validation**
- Run validation scripts on both approaches
- Measure fix rate (current: 51%, target: <10%)
- User testing

**Week 4: Decision Point**
- If hybrid approach works: migrate fully
- If issues found: iterate or revert

**Week 5-6: Full Migration**
- Migrate all technology templates
- Update documentation
- Deprecate old system

---

## Effort Estimation

### Foundation SDK Integration
- **Effort:** 1 week
- **Risk:** Low (straightforward API replacement)
- **Complexity:** Medium

### Metric Discovery Implementation
- **Effort:** 2 weeks
- **Risk:** Medium (Prometheus API complexity)
- **Complexity:** High

### Technology Classification Logic
- **Effort:** 1-2 weeks  
- **Risk:** Medium (heuristics may need tuning)
- **Complexity:** Medium

### Testing & Validation
- **Effort:** 1 week
- **Risk:** Low
- **Complexity:** Low

**Total:** 5-6 weeks for complete hybrid implementation

---

## License Compatibility

All tools use **Apache 2.0 license** ✅

**This means we can:**
- Fork and modify
- Incorporate code
- Use commercially
- Redistribute

**We must:**
- Include original license
- State modifications
- Include NOTICE files

**No restrictions on:**
- Commercial use
- Combining with NthLayer
- Proprietary additions

---

## Conclusion

### Clear Winners

**1. autograf's Metric Discovery Pattern** ⭐⭐⭐⭐⭐
- Solves template brittleness
- Self-validating
- Adapts to any setup
- **Adopt this pattern immediately**

**2. Grafana Foundation SDK** ⭐⭐⭐⭐
- Official support
- Type safety
- Future-proof
- **Replace our Panel/Target models**

### Don't Adopt

**grafana-dashboard-builder** ❌
- Same problems we have
- No additional value

### Consider

**grafanalib** ⚠️
- More mature than Foundation SDK
- Better Python API
- But not official

---

## Recommended Action Plan

**Immediate (Next 2 Weeks):**

1. **Build hybrid prototype**
   - Use Foundation SDK for one dashboard
   - Add metric discovery for validation
   - Measure improvement

2. **Quantify benefits**
   - Fix rate reduction
   - Development velocity
   - Test coverage

3. **Decision point**
   - If metrics improve: full migration
   - If not: investigate further

**Long-term (3-6 Months):**

1. **Golden paths + Hybrid**
   - Certify 3-5 stacks
   - Use discovery for validation
   - Maintain service abstractions

2. **Open source discovery layer**
   - Contribute back to autograf
   - Build NthLayer-specific extensions
   - Community benefits

---

**Bottom Line:** We don't need to choose between NthLayer's high-level abstractions and autograf's discovery magic. **We can have both.** The hybrid architecture preserves our SLO and service intelligence while eliminating template brittleness through metric discovery.

The 51% fix rate can become <10% by adopting proven patterns from the ecosystem.
