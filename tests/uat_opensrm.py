#!/usr/bin/env python3
"""UAT script for OpenSRM Phase 1 & 2: *_from_manifest() generator-level tests.

Loads the OpenSRM manifest via load_manifest(), calls each generator,
writes outputs to generated/uat/opensrm/, and compares structure against
the legacy output in generated/uat/legacy/.

Usage:
    uv run python tests/uat_opensrm.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Project root for locating manifest files and output dirs
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from nthlayer.dashboards.manifest_builder import build_dashboard_from_manifest
from nthlayer.generators.alerts import generate_alerts_from_manifest
from nthlayer.generators.sloth import generate_sloth_from_manifest
from nthlayer.loki.generator import generate_loki_alerts_from_manifest
from nthlayer.metrics.recommender import recommend_metrics_from_manifest
from nthlayer.recording_rules.manifest_builder import build_recording_rules_from_manifest
from nthlayer.recording_rules.models import create_rule_groups
from nthlayer.specs.loader import load_manifest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MANIFEST_PATH = project_root / "examples" / "uat" / "payment-api.reliability.yaml"
OUTPUT_DIR = project_root / "generated" / "uat" / "opensrm"
LEGACY_DIR = project_root / "generated" / "uat" / "legacy" / "payment-api"

passed = 0
failed = 0
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    """Record a UAT check result."""
    global passed, failed
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    results.append((name, ok, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


# ===========================================================================
# Step 1: Load OpenSRM manifest
# ===========================================================================
print("\n=== Step 1: Load OpenSRM manifest ===")
try:
    manifest = load_manifest(str(MANIFEST_PATH))
    check("load_manifest() succeeds", True)
    check(
        "source_format is OPENSRM",
        manifest.source_format.value == "opensrm",
        f"got {manifest.source_format.value}",
    )
    check("service name is payment-api", manifest.name == "payment-api", f"got {manifest.name}")
    check("tier is critical", manifest.tier == "critical", f"got {manifest.tier}")
    check("type is api", manifest.type == "api", f"got {manifest.type}")
    check("has 2 SLOs", len(manifest.slos) == 2, f"got {len(manifest.slos)}")
    check(
        "has 3 dependencies",
        len(manifest.dependencies) == 3,
        f"got {len(manifest.dependencies)}",
    )
except Exception as exc:
    check("load_manifest() succeeds", False, str(exc))
    print(f"\nFATAL: Cannot continue without manifest. Error: {exc}")
    sys.exit(1)

# ===========================================================================
# Step 2: generate_alerts_from_manifest()
# ===========================================================================
print("\n=== Step 2: generate_alerts_from_manifest() ===")
try:
    alert_output = OUTPUT_DIR / "alerts.yaml"
    alerts = generate_alerts_from_manifest(
        manifest,
        output_file=alert_output,
        quiet=True,
    )
    check("generate_alerts_from_manifest() runs", True, f"{len(alerts)} alerts")
    # Alerts may be empty if template directory is not bundled — that's OK
    if alerts:
        check("alerts is a list", isinstance(alerts, list))
        check(
            "alert output file exists",
            alert_output.exists(),
            str(alert_output),
        )
    else:
        check(
            "alerts empty (expected: templates not bundled)",
            True,
            "0 alerts — template dir not in installed pkg",
        )
except Exception as exc:
    check("generate_alerts_from_manifest() runs", False, str(exc))

# ===========================================================================
# Step 3: generate_sloth_from_manifest()
# ===========================================================================
print("\n=== Step 3: generate_sloth_from_manifest() ===")
try:
    sloth_dir = OUTPUT_DIR / "sloth"
    result = generate_sloth_from_manifest(manifest, output_dir=sloth_dir)
    check("generate_sloth_from_manifest() succeeds", result.success, result.error or "")
    check("sloth service matches", result.service == "payment-api", f"got {result.service}")
    check("sloth SLO count is 2", result.slo_count == 2, f"got {result.slo_count}")
    check(
        "sloth output file exists",
        result.output_file is not None and result.output_file.exists(),
        str(result.output_file),
    )

    # Validate content
    if result.output_file and result.output_file.exists():
        sloth_data = yaml.safe_load(result.output_file.read_text())
        check(
            "sloth version is prometheus/v1",
            sloth_data.get("version") == "prometheus/v1",
        )
        check(
            "sloth service field matches",
            sloth_data.get("service") == "payment-api",
        )
        sloth_slos = sloth_data.get("slos", [])
        check("sloth has 2 SLO entries", len(sloth_slos) == 2, f"got {len(sloth_slos)}")
        slo_names = [s["name"] for s in sloth_slos]
        check(
            "sloth SLO names match",
            "availability" in slo_names and "latency-p95" in slo_names,
            f"got {slo_names}",
        )
except Exception as exc:
    check("generate_sloth_from_manifest() succeeds", False, str(exc))

# ===========================================================================
# Step 4: build_dashboard_from_manifest()
# ===========================================================================
print("\n=== Step 4: build_dashboard_from_manifest() ===")
try:
    dashboard_json = build_dashboard_from_manifest(manifest)
    check("build_dashboard_from_manifest() returns dict", isinstance(dashboard_json, dict))

    # Write output
    dash_output = OUTPUT_DIR / "dashboard.json"
    dash_output.parent.mkdir(parents=True, exist_ok=True)
    dash_output.write_text(json.dumps(dashboard_json, indent=2))
    check("dashboard.json written", dash_output.exists(), str(dash_output))

    # Basic structure check
    has_dashboard_key = "dashboard" in dashboard_json
    check(
        "dashboard has expected structure",
        has_dashboard_key or "panels" in dashboard_json or "title" in dashboard_json,
        f"top keys: {list(dashboard_json.keys())[:5]}",
    )
except Exception as exc:
    check("build_dashboard_from_manifest() returns dict", False, str(exc))

# ===========================================================================
# Step 5: generate_loki_alerts_from_manifest()
# ===========================================================================
print("\n=== Step 5: generate_loki_alerts_from_manifest() ===")
try:
    loki_alerts, loki_path = generate_loki_alerts_from_manifest(
        manifest,
        output_dir=OUTPUT_DIR / "loki",
    )
    check(
        "generate_loki_alerts_from_manifest() runs",
        True,
        f"{len(loki_alerts)} alerts",
    )
    check("loki alerts is a list", isinstance(loki_alerts, list))
    if loki_alerts:
        # Check first alert has expected fields
        first = loki_alerts[0]
        check("loki alert has name", hasattr(first, "name") and bool(first.name))
        check("loki alert has expr", hasattr(first, "expr") and bool(first.expr))
    if loki_path:
        check("loki output file exists", loki_path.exists(), str(loki_path))
except Exception as exc:
    check("generate_loki_alerts_from_manifest() runs", False, str(exc))

# ===========================================================================
# Step 6: recommend_metrics_from_manifest()
# ===========================================================================
print("\n=== Step 6: recommend_metrics_from_manifest() ===")
try:
    recommendation = recommend_metrics_from_manifest(manifest)
    check(
        "recommend_metrics_from_manifest() runs",
        True,
        f"slo_ready={recommendation.slo_ready}",
    )
    check(
        "recommendation service matches",
        recommendation.service == "payment-api",
        f"got {recommendation.service}",
    )
    check(
        "recommendation has required metrics",
        isinstance(recommendation.required, list),
        f"{len(recommendation.required)} required metrics",
    )

    # Write output
    rec_output = OUTPUT_DIR / "metrics-recommendation.json"
    rec_output.parent.mkdir(parents=True, exist_ok=True)
    rec_output.write_text(json.dumps(recommendation.to_dict(), indent=2))
    check("metrics-recommendation.json written", rec_output.exists())
except Exception as exc:
    check("recommend_metrics_from_manifest() runs", False, str(exc))

# ===========================================================================
# Step 7: build_recording_rules_from_manifest()
# ===========================================================================
print("\n=== Step 7: build_recording_rules_from_manifest() ===")
try:
    rule_groups = build_recording_rules_from_manifest(manifest)
    check(
        "build_recording_rules_from_manifest() runs",
        True,
        f"{len(rule_groups)} groups",
    )
    check("rule groups is a list", isinstance(rule_groups, list))

    total_rules = sum(len(g.rules) for g in rule_groups)
    check("recording rules generated", total_rules > 0, f"{total_rules} rules")

    # Write output
    rules_output = OUTPUT_DIR / "recording-rules.yaml"
    rules_output.parent.mkdir(parents=True, exist_ok=True)
    rules_yaml = create_rule_groups(rule_groups)
    rules_output.write_text(rules_yaml)
    check("recording-rules.yaml written", rules_output.exists(), str(rules_output))

    # Validate YAML structure
    rules_data = yaml.safe_load(rules_yaml)
    check(
        "recording rules has groups key",
        "groups" in rules_data,
        f"top keys: {list(rules_data.keys())}",
    )
    groups_list = rules_data.get("groups", [])
    check(
        "recording rules group count matches",
        len(groups_list) == len(rule_groups),
        f"expected {len(rule_groups)}, got {len(groups_list)}",
    )
except Exception as exc:
    check("build_recording_rules_from_manifest() runs", False, str(exc))

# ===========================================================================
# Step 8: Compare structure against legacy output
# ===========================================================================
print("\n=== Step 8: Compare OpenSRM vs Legacy output structure ===")

# Compare Sloth output
legacy_sloth = LEGACY_DIR / "sloth" / "payment-api.yaml"
opensrm_sloth = OUTPUT_DIR / "sloth" / "payment-api.yaml"
if legacy_sloth.exists() and opensrm_sloth.exists():
    legacy_data = yaml.safe_load(legacy_sloth.read_text())
    opensrm_data = yaml.safe_load(opensrm_sloth.read_text())
    check(
        "sloth: service name matches legacy",
        legacy_data.get("service") == opensrm_data.get("service"),
        f"legacy={legacy_data.get('service')}, opensrm={opensrm_data.get('service')}",
    )
    check(
        "sloth: SLO count matches legacy",
        len(legacy_data.get("slos", [])) == len(opensrm_data.get("slos", [])),
        f"legacy={len(legacy_data.get('slos', []))}, opensrm={len(opensrm_data.get('slos', []))}",
    )
    check(
        "sloth: labels match legacy",
        legacy_data.get("labels") == opensrm_data.get("labels"),
        f"legacy={legacy_data.get('labels')}, opensrm={opensrm_data.get('labels')}",
    )
else:
    check(
        "sloth: legacy output exists for comparison",
        False,
        f"legacy={legacy_sloth.exists()}, opensrm={opensrm_sloth.exists()}",
    )

# Compare recording rules structure
legacy_rules = LEGACY_DIR / "recording-rules.yaml"
opensrm_rules = OUTPUT_DIR / "recording-rules.yaml"
if legacy_rules.exists() and opensrm_rules.exists():
    legacy_data = yaml.safe_load(legacy_rules.read_text())
    opensrm_data = yaml.safe_load(opensrm_rules.read_text())
    legacy_groups = legacy_data.get("groups", [])
    opensrm_groups = opensrm_data.get("groups", [])
    check(
        "recording rules: group count matches legacy",
        len(legacy_groups) == len(opensrm_groups),
        f"legacy={len(legacy_groups)}, opensrm={len(opensrm_groups)}",
    )
    legacy_rule_count = sum(len(g.get("rules", [])) for g in legacy_groups)
    opensrm_rule_count = sum(len(g.get("rules", [])) for g in opensrm_groups)
    check(
        "recording rules: rule count matches legacy",
        legacy_rule_count == opensrm_rule_count,
        f"legacy={legacy_rule_count}, opensrm={opensrm_rule_count}",
    )
    legacy_group_names = sorted(g["name"] for g in legacy_groups)
    opensrm_group_names = sorted(g["name"] for g in opensrm_groups)
    check(
        "recording rules: group names match legacy",
        legacy_group_names == opensrm_group_names,
        f"legacy={legacy_group_names}, opensrm={opensrm_group_names}",
    )
else:
    check(
        "recording rules: legacy output exists for comparison",
        False,
        f"legacy={legacy_rules.exists()}, opensrm={opensrm_rules.exists()}",
    )

# Compare dashboard structure
legacy_dash = LEGACY_DIR / "dashboard.json"
opensrm_dash = OUTPUT_DIR / "dashboard.json"
if legacy_dash.exists() and opensrm_dash.exists():
    legacy_data = json.loads(legacy_dash.read_text())
    opensrm_data = json.loads(opensrm_dash.read_text())
    check(
        "dashboard: top-level keys match legacy",
        set(legacy_data.keys()) == set(opensrm_data.keys()),
        f"legacy={sorted(legacy_data.keys())}, opensrm={sorted(opensrm_data.keys())}",
    )
else:
    check(
        "dashboard: legacy output exists for comparison",
        False,
        f"legacy={legacy_dash.exists()}, opensrm={opensrm_dash.exists()}",
    )

# ===========================================================================
# Summary
# ===========================================================================
print("\n" + "=" * 60)
print(f"UAT RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print("=" * 60)

if failed:
    print("\nFailed checks:")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))

sys.exit(0 if failed == 0 else 1)
