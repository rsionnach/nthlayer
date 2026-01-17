# NthLayer User Acceptance Testing (UAT)

This document tracks UAT testing for NthLayer releases using the Synology-based test environment.

## Test Environment

### Synology Setup
- **Host**: Synology NAS
- **Services**:
  - Prometheus (metrics collection)
  - Grafana (dashboard visualization)
  - Backstage (service catalog)
- **Access**: Local network

### Prerequisites
- NthLayer CLI installed (`pip install nthlayer`)
- `service.yaml` configured for test service
- Network access to Synology services

---

## Test Scenarios

### 1. CLI Installation & Version
| Test | Command | Expected Result | Status |
|------|---------|-----------------|--------|
| Install from PyPI | `pip install nthlayer` | Installs without errors | |
| Check version | `nthlayer --version` | Shows current version | |
| Help output | `nthlayer --help` | Lists all commands | |

### 2. Configuration Generation (`nthlayer apply`)
| Test | Command | Expected Result | Status |
|------|---------|-----------------|--------|
| Generate all configs | `nthlayer apply` | Creates alerts, dashboard, recording rules | |
| Generate alerts only | `nthlayer apply --alerts` | Creates alerts.yaml | |
| Generate dashboard only | `nthlayer apply --dashboard` | Creates dashboard.json | |
| Push to Grafana | `nthlayer apply --push-grafana` | Dashboard appears in Grafana | |

### 3. Dashboard Commands
| Test | Command | Expected Result | Status |
|------|---------|-----------------|--------|
| Build dashboard | `nthlayer dashboard build` | Generates dashboard JSON | |
| Validate dashboard | `nthlayer dashboard validate` | Validates structure | |
| Push dashboard | `nthlayer dashboard push --prometheus-url <url>` | Uploads to Grafana | |

### 4. Alert Commands
| Test | Command | Expected Result | Status |
|------|---------|-----------------|--------|
| List templates | `nthlayer alerts list` | Shows available templates | |
| Generate alerts | `nthlayer alerts generate` | Creates alert rules | |
| Validate alerts | `nthlayer alerts validate` | Validates PromQL syntax | |

### 5. Dependency Commands
| Test | Command | Expected Result | Status |
|------|---------|-----------------|--------|
| Show dependencies | `nthlayer deps <service>` | Lists upstream/downstream | |
| Blast radius | `nthlayer blast-radius <service>` | Shows impact analysis | |
| DOT output | `nthlayer deps <service> --format dot` | Generates graph | |

### 6. SLO Commands
| Test | Command | Expected Result | Status |
|------|---------|-----------------|--------|
| Validate SLO | `nthlayer validate-slo <service>` | Checks metric existence | |
| Drift analysis | `nthlayer drift <service>` | Shows error budget status | |

### 7. Identity & Ownership
| Test | Command | Expected Result | Status |
|------|---------|-----------------|--------|
| Resolve identity | `nthlayer identity resolve <name>` | Returns canonical name | |
| Show ownership | `nthlayer ownership <service>` | Shows team/on-call info | |

### 8. Integration Tests
| Test | Description | Expected Result | Status |
|------|-------------|-----------------|--------|
| Prometheus connectivity | Query metrics from Prometheus | Returns data | |
| Grafana connectivity | Push dashboard to Grafana | Dashboard visible | |
| Backstage connectivity | Query service catalog | Returns service info | |
| End-to-end workflow | `apply` → verify in Grafana | All artifacts deployed | |

---

## Test Results

### v0.1.0a13 (January 14, 2026)
| Scenario | Result | Notes |
|----------|--------|-------|
| | | |

### v0.1.0a12 (January 12, 2026)
| Scenario | Result | Notes |
|----------|--------|-------|
| | | |

---

## Known Issues

| Issue | Version | Description | Workaround | Status |
|-------|---------|-------------|------------|--------|
| Backstage network error | a13 | "TypeError: Network request failed" on Synology | Check network/CORS config | Investigating |

---

## Environment Variables

```bash
# Grafana
export NTHLAYER_GRAFANA_URL=http://<synology-ip>:3000
export NTHLAYER_GRAFANA_API_KEY=<api-key>

# Prometheus
export NTHLAYER_PROMETHEUS_URL=http://<synology-ip>:9090

# Backstage
export NTHLAYER_BACKSTAGE_URL=http://<synology-ip>:7007
```

---

## Running UAT

1. **Setup environment**
   ```bash
   cd /path/to/service
   export NTHLAYER_GRAFANA_URL=...
   export NTHLAYER_PROMETHEUS_URL=...
   ```

2. **Run test scenarios**
   - Work through each section above
   - Mark Status: PASS / FAIL / SKIP
   - Add notes for any issues

3. **Document results**
   - Add entry to Test Results section
   - Update Known Issues if needed

4. **Report issues**
   - Create GitHub issue for failures
   - Link to this UAT document
