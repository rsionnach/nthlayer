# ADR 001: Foundation SDK Integration Approach

**Status**: Accepted  
**Date**: 2025-11-30  
**Deciders**: robfox, Droid

## Context

NthLayer originally used custom Python code to generate Grafana dashboards as JSON. This worked but:
- No type safety
- Manual JSON construction prone to errors
- Difficult to keep up with Grafana schema changes
- No IDE autocomplete for dashboard properties

The [grafana-foundation-sdk](https://github.com/grafana/grafana-foundation-sdk) provides official Python builders for Grafana resources with full type safety.

## Decision

Integrate grafana-foundation-sdk while maintaining existing templates and dashboard generation patterns.

### Approach Chosen

**Incremental Integration via Adapter Pattern**:

1. **Install SDK**: `grafana-foundation-sdk` package
2. **Create SDKAdapter**: Convert NthLayer models → SDK builders
3. **Create DashboardBuilderSDK**: New builder using SDK internally
4. **Keep existing templates**: PostgreSQL, Redis, MongoDB, etc.
5. **Adapter converts template panels**: Legacy Panel → SDK Panel

### Why Not Full Rewrite

**Rejected**: Rewrite all 6 technology templates to use SDK directly

**Reasons**:
- Templates work and have good test coverage
- Would take 6-8 hours to rewrite
- Risk of introducing bugs
- Adapter achieves same type safety benefit
- Can migrate templates incrementally later

## Options Considered

### Option 1: Adapter Pattern (CHOSEN)
**Pros**:
- Minimal disruption to existing code
- Incremental adoption
- Templates remain readable
- Type safety where it matters (SDK boundary)

**Cons**:
- Extra abstraction layer
- Some conversion overhead
- Two ways to build dashboards initially

### Option 2: Full SDK Rewrite
**Pros**:
- Clean architecture
- Full type safety everywhere
- No legacy code

**Cons**:
- 6-8 hours of work
- High risk of regression
- Blocks other work
- Templates less readable (more verbose)

### Option 3: Stay with Custom JSON
**Pros**:
- No changes needed
- Keep full control

**Cons**:
- No type safety
- Brittle JSON construction
- Hard to maintain long-term

## Implementation

### Created Files

1. **SDK_INTEGRATION_GUIDE.md** (414 lines)
   - Complete SDK API reference
   - Code examples for all panel types
   - Query building patterns

2. **src/nthlayer/dashboards/sdk_adapter.py** (367 lines)
   - ServiceContext → SDK Dashboard
   - Panel → SDK Panel converters
   - SLO → Prometheus query builders
   - Template variable handling

3. **src/nthlayer/dashboards/builder_sdk.py** (299 lines)
   - DashboardBuilderSDK class
   - Generates complete dashboards with SDK
   - Integrates with existing templates

### Key Design Decisions

**ServiceContext as Bridge**:
```python
context = ServiceContext(
    name="payment-api",
    team="payments",
    tier="critical"
)
```

Used by both legacy and SDK builders - enables gradual migration.

**Panel Type Mapping**:
```python
'timeseries' → timeseries.Panel()
'stat' → stat.Panel()  
'gauge' → gauge.Panel()
```

**Query Conversion**:
Legacy Panel.targets → SDK prometheus.Dataquery with proper ref_id and legend_format

## Consequences

### Positive

✅ **Type safety at SDK boundary**: Catch errors before dashboard push  
✅ **Existing templates work**: No disruption to PostgreSQL, Redis, etc. monitoring  
✅ **Incremental adoption**: Can migrate templates one at a time  
✅ **Schema version safety**: SDK handles Grafana v36 schema correctly  
✅ **Better IDE support**: Autocomplete for dashboard properties  

### Negative

⚠️ **Abstraction overhead**: Extra layer between templates and SDK  
⚠️ **Two ways to build**: DashboardBuilder (legacy) and DashboardBuilderSDK coexist  
⚠️ **Conversion logic**: Need to maintain adapter mappings  
⚠️ **Not all SDK features used**: Templates still use legacy Panel models internally  

### Technical Debt

- [ ] Migrate templates to use SDK builders directly (PostgreSQL, Redis, MongoDB, etc.)
- [ ] Deprecate legacy DashboardBuilder once migration complete
- [ ] Remove SDKAdapter once templates use SDK natively

## Validation

**Success Criteria Met**:
- ✅ All 5 demo services generate dashboards with SDK
- ✅ 109 total panels generated successfully
- ✅ All dashboards valid Grafana v36 schema
- ✅ search-api (6th service) added with Elasticsearch template
- ✅ Dashboards push to Grafana Cloud successfully

**Tests**:
- `test_sdk_adapter_integration.py` - Adapter functionality
- `test_all_services_sdk.py` - End-to-end generation
- Manual verification in Grafana Cloud

## Related Decisions

- ADR 002: Metric Discovery System (Week 1)
- ADR 003: Dashboard Query Validation (Week 2)

## References

- [Grafana Foundation SDK](https://github.com/grafana/grafana-foundation-sdk)
- [SDK Python Docs](https://grafana.github.io/grafana-foundation-sdk/python/)
- Issue: Week 2 SDK Integration Milestone
- Commit: `24602f0` - SDK Integration Complete
