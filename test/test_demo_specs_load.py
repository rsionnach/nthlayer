"""The demo's manifests load through the published nthlayer-common (opensrm-gx3e).

nthlayer-common used to run this check against the live ``demo/specs`` of a
sibling front-door checkout. opensrm-t93o moved it to a snapshot inside
common, so common's suite no longer notices when a demo spec changes into
something the parser mishandles. The live check belongs where the specs
live, which is here.

Why it matters (opensrm-saun.1): the v1 parser once read a top-level
``query`` while every demo manifest wrote ``indicator.query``. Each SLO
loaded with no query, the worker collected NO_DATA for all of them, and
nothing failed until the three-tier integration run.

The manifests are the demo's own files, not fixtures written for this test,
and the expected values are read from the YAML without the parser. Nothing
drops out unseen: the files are listed (a glob that matched nothing would
collect no tests), and a test keeps the list equal to the directory.

Run with CI's command (.github/workflows/demo-specs.yml). --isolated
--no-project matter: without them uv uses the workspace's editable
nthlayer-common checkout, not the published package.

    uv run --isolated --no-project --python 3.11 \\
        --with nthlayer-common --with pytest --with pyyaml \\
        pytest -q test/test_demo_specs_load.py
"""

from __future__ import annotations

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


def _declared_queries(spec_path: Path) -> dict[str, str]:
    """SLO name -> the ``indicator.query`` the file declares, read from the
    YAML without the parser. srm/v1 writes ``spec.slos`` as a mapping."""
    slos = yaml.safe_load(spec_path.read_text())["spec"]["slos"]
    assert isinstance(slos, dict), f"{spec_path.name}: spec.slos is not a mapping"
    declared = {}
    for name, slo in slos.items():
        indicator = slo.get("indicator") if isinstance(slo, dict) else None
        if isinstance(indicator, dict) and "query" in indicator:
            declared[name] = indicator["query"]
    return declared


def test_every_demo_spec_is_listed():
    on_disk = sorted(
        p.name for p in DEMO_SPECS_DIR.iterdir() if p.suffix in (".yaml", ".yml")
    )
    assert on_disk == DEMO_SPECS


@pytest.mark.parametrize("spec_name", DEMO_SPECS)
def test_demo_spec_loads_with_its_indicator_queries(spec_name: str):
    """Each SLO that declares ``indicator.query`` carries that query,
    unchanged, as ``indicator_query`` after loading."""
    spec_path = DEMO_SPECS_DIR / spec_name
    declared = _declared_queries(spec_path)
    # Every demo spec declares at least one; without this the equality
    # below would pass on two empty dicts.
    assert declared, f"{spec_name}: no SLO declares indicator.query"
    assert all(
        isinstance(q, str) and q.strip() for q in declared.values()
    ), f"{spec_name}: an empty declared query"

    manifest = load_manifest(spec_path)
    assert manifest.name == spec_path.stem
    parsed = {slo.name: slo.indicator_query for slo in manifest.slos}

    assert {name: parsed.get(name) for name in declared} == declared


def test_fraud_detect_reversal_rate_is_a_judgment_slo():
    """fraud-detect's ``reversal_rate`` is the SLO the demo's whole
    measure -> correlate -> respond -> learn chain starts from. It must load
    as a judgment SLO of type ``reversal_rate`` with the file's own query."""
    spec_path = DEMO_SPECS_DIR / "fraud-detect.yaml"
    declared_query = _declared_queries(spec_path)["reversal_rate"]

    manifest = load_manifest(spec_path)
    by_name = {slo.name: slo for slo in manifest.slos}
    reversal = by_name["reversal_rate"]

    assert reversal.judgment_type == "reversal_rate"
    assert reversal.indicator_query == declared_query
