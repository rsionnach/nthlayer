"""The demo's manifests migrate with the published nthlayer-generate (opensrm-jg1e).

nthlayer-generate vendors the four demo manifests under
``tests/fixtures/demo_specs`` so its migrate-manifest tests cannot skip in CI
(opensrm-w658). Those are copies: when ``demo/specs`` changes here, generate's
suite keeps proving the migration on the old files. This runs the same
migration on the live files, with the published package, so a demo spec that
stops migrating is caught where it is edited. (The copies still want a
refresh after a change; docs/integration-testing.md says where they are.)

What it holds each demo spec to, through the real ``nthlayer
migrate-manifest`` command:

- it exits 0 and writes an ``opensrm.nthlayer.io/v2`` document that the
  published nthlayer-common loads, under the same name;
- the SLOs that come out are exactly the file's: none dropped, none added;
- a judgment SLO stays one, with its type; which SLOs those are is pinned in
  EXPECTED_JUDGMENT, not read from the output;
- every other SLO keeps its ``indicator.query`` unchanged.

A judgment SLO's v1 query is not compared: v2 judgment SLOs carry a target
and a measurement window, not a query.

The manifests are the demo's own files and the expected values are read from
them without the migrator. The files are listed (a glob that matched nothing
would collect no tests), and a test keeps the list equal to the directory.

Run with CI's command (.github/workflows/demo-specs.yml). --isolated
--no-project matter: without them uv uses the workspace's editable sibling
checkouts, not the published packages.

    uv run --isolated --no-project --python 3.11 \\
        --with nthlayer-generate --with pytest --with pyyaml \\
        pytest -q test/test_demo_specs_migrate.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from nthlayer_common.manifest import load_manifest

DEMO_SPECS_DIR = Path(__file__).resolve().parents[1] / "demo" / "specs"

# Listed, not globbed. test_every_demo_spec_is_listed keeps it complete.
DEMO_SPECS = [
    "checkout-svc.yaml",
    "fraud-detect.yaml",
    "order-service.yaml",
    "payment-api.yaml",
]

# The demo's judgment SLOs, by file. fraud-detect's reversal_rate is the one
# the demo's measure -> correlate -> respond -> learn chain starts from; in
# srm/v1 a judgment SLO is named for its type. Everything else is a classical
# SLO read by its query.
EXPECTED_JUDGMENT = {"fraud-detect.yaml": {"reversal_rate"}}

V2_API_VERSION = "opensrm.nthlayer.io/v2"


def _declared_queries(spec_path: Path) -> dict[str, str]:
    """SLO name -> the ``indicator.query`` the srm/v1 file declares, read
    from the YAML without the migrator or the parser."""
    slos = yaml.safe_load(spec_path.read_text())["spec"]["slos"]
    assert isinstance(slos, dict) and slos, f"{spec_path.name}: no spec.slos mapping"
    return {name: slo["indicator"]["query"] for name, slo in slos.items()}


def _migrate(spec_path: Path, out_dir: Path) -> Path:
    cli = shutil.which("nthlayer")
    assert cli, "the nthlayer command is not on PATH (run with --with nthlayer-generate)"
    out = out_dir / f"{spec_path.stem}.v2.yaml"
    result = subprocess.run(
        [cli, "migrate-manifest", str(spec_path), "--output", str(out)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"{spec_path.name}: exit {result.returncode}\n{result.stderr}"
    assert out.is_file(), f"{spec_path.name}: exit 0 but nothing written to {out}"
    return out


def test_every_demo_spec_is_listed():
    on_disk = sorted(
        p.name for p in DEMO_SPECS_DIR.iterdir() if p.suffix in (".yaml", ".yml")
    )
    assert on_disk == DEMO_SPECS
    assert set(EXPECTED_JUDGMENT) <= set(DEMO_SPECS)


@pytest.mark.parametrize("spec_name", DEMO_SPECS)
def test_demo_spec_migrates_to_a_loadable_v2_manifest(spec_name: str, tmp_path: Path):
    spec_path = DEMO_SPECS_DIR / spec_name
    declared = _declared_queries(spec_path)
    judgment = EXPECTED_JUDGMENT.get(spec_name, set())
    assert judgment <= set(declared), f"{spec_name}: a pinned judgment SLO is not in the file"

    out = _migrate(spec_path, tmp_path)

    document = yaml.safe_load(out.read_text())
    assert document["apiVersion"] == V2_API_VERSION
    assert document["metadata"]["name"] == spec_path.stem

    manifest = load_manifest(out)
    assert manifest.name == spec_path.stem
    migrated = {slo.name: slo for slo in manifest.slos}
    assert len(migrated) == len(manifest.slos), f"{spec_name}: a duplicated SLO name"
    assert set(migrated) == set(declared)

    assert {n: s.judgment_type for n, s in migrated.items() if s.judgment_type} == {
        name: name for name in judgment
    }
    classical = {name: q for name, q in declared.items() if name not in judgment}
    assert {name: migrated[name].indicator_query for name in classical} == classical
