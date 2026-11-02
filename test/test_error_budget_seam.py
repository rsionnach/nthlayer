"""The error-budget seam between nthlayer-generate and nthlayer-workers (opensrm-h0at).

measure read ``slo:error_budget:ratio``, a series nothing wrote, so every
availability SLO evaluated as no data. Each side had a green suite; nothing
checked that the reader asks for what the writer writes. This does: for every
real manifest, the error-budget series generate writes and the error-budget
queries measure sends must be the same set, in both directions.

The manifests are the spec's v2 examples and generate's shipped examples, not
fixtures written for this test. Nothing drops out unseen: a missing checkout
fails rather than skipping (the opensrm-oh27 lesson), every file the loader
rejects must be listed in EXPECTED_REJECTED with its reason, and the number
that write an error budget is pinned. A manifest that stops loading, or a
fixed one that starts, turns this red.

Run from the ecosystem root with CI's command (ci.yml, error-budget-seam).
--isolated --no-project matter: without them uv uses the workspace's
editable sibling checkouts, not the published packages.

    uv run --isolated --no-project --python 3.11 \\
        --with nthlayer-generate --with nthlayer-workers --with pytest \\
        pytest -q nthlayer/test/test_error_budget_seam.py
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

from nthlayer_common.manifest import (
    ERROR_BUDGET_REMAINING,
    ManifestLoadError,
    ReliabilityManifest,
    load_manifest,
)
from nthlayer_generate.recording_rules import build_recording_rules_from_manifest
from nthlayer_workers.measure.adapters.prometheus import load_specs

# nthlayer/test/ -> ecosystem root, where opensrm and nthlayer-generate are
# siblings (locally, and as laid out by the front door's CI job).
ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIRS = (
    ROOT / "opensrm" / "spec" / "v2" / "examples",
    ROOT / "nthlayer-generate" / "examples" / "services",
    ROOT / "nthlayer-generate" / "examples" / "opensrm",
)
# Exact, not a floor: a floor lets manifests leave the seam unseen.
EXPECTED_WITH_BUDGET = 24  # 2026-11-02, common 5.10.1 / generate 4.0.10 / workers 4.0.2

_TEMPLATE = "template or fragment, not a service manifest"
# Every corpus file the loader rejects, with why. Spec examples that should
# load carry the bead tracking the divergence.
EXPECTED_REJECTED = {
    "nthlayer-generate/examples/services/environments/dev.yaml": "environment overlay",
    "nthlayer-generate/examples/services/environments/prod.yaml": "environment overlay",
    "nthlayer-generate/examples/services/environments/staging.yaml": "environment overlay",
    "opensrm/spec/v2/examples/judgment-slo-template.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/judgment-slos/01-reversal-rate.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/judgment-slos/02-high-confidence-failure.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/judgment-slos/03-audit-sampling.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/judgment-slos/04-outcomes.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/judgment-slos/05-escalation.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/judgment-thresholds/ai-gate-template.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/service-manifest-template.yaml": _TEMPLATE,
    "opensrm/spec/v2/examples/template-extension.yaml": "opensrm-moq0",
    "opensrm/spec/v2/examples/minimal.yaml": "opensrm-ta0m",
    "opensrm/spec/v2/examples/x-service-type.yaml": "opensrm-ta0m",
    "opensrm/spec/v2/examples/services/ai-gate-without-judgment-slos.yaml": "opensrm-ta0m",
    "opensrm/spec/v2/examples/services/batch.yaml": "opensrm-ta0m",
    "opensrm/spec/v2/examples/services/database.yaml": "opensrm-ta0m",
    "opensrm/spec/v2/examples/services/api.yaml": "opensrm-1qy1",
    "opensrm/spec/v2/examples/service-manifest-full.yaml": "opensrm-1qy1",
    "opensrm/spec/v2/examples/services/stream.yaml": "opensrm-moq0",
    "opensrm/spec/v2/examples/services/worker.yaml": "opensrm-moq0",
    "opensrm/spec/v2/examples/services/ai-gate.yaml": "opensrm-moq0",
}


def _corpus() -> list[Path]:
    missing = [d for d in CORPUS_DIRS if not d.is_dir()]
    assert not missing, f"corpus checkout missing: {missing}"
    return sorted(p for d in CORPUS_DIRS for p in d.rglob("*.yaml"))


def _load(path: Path) -> ReliabilityManifest | None:
    """The manifest, or None if the loader rejects it (checked against
    EXPECTED_REJECTED by the caller). Any other exception propagates."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return load_manifest(path)
        except ManifestLoadError:
            return None


def _written(manifest: ReliabilityManifest) -> set[str]:
    """Each error-budget series generate writes, as the selector reading it."""
    return {
        ERROR_BUDGET_REMAINING.selector(service=r.labels["service"], slo=r.labels["slo"])
        for group in build_recording_rules_from_manifest(manifest)
        for r in group.rules
        if r.record == ERROR_BUDGET_REMAINING.metric
    }


def _read(path: Path, spec_dir: Path) -> set[str]:
    """Each error-budget query measure sends for the manifest."""
    spec_dir.mkdir()
    shutil.copy(path, spec_dir / path.name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        slos = load_specs(spec_dir).slos
    return {s.query for s in slos if s.query_kind == "error_budget"}


def test_measure_reads_exactly_the_error_budget_generate_writes(tmp_path):
    with_budget = []
    rejected = set()
    mismatches = {}
    for i, path in enumerate(_corpus()):
        manifest = _load(path)
        if manifest is None:
            rejected.add(str(path.relative_to(ROOT)))
            continue
        # A directory per file: load_specs reads every manifest in its directory.
        written, read = _written(manifest), _read(path, tmp_path / str(i))
        if written != read:
            mismatches[str(path.relative_to(ROOT))] = {
                "written_not_read": sorted(written - read),
                "read_not_written": sorted(read - written),
            }
        if written:
            with_budget.append(str(path.relative_to(ROOT)))

    assert not mismatches, mismatches
    assert rejected == set(EXPECTED_REJECTED), {
        "newly_rejected": sorted(rejected - set(EXPECTED_REJECTED)),
        "now_loads": sorted(set(EXPECTED_REJECTED) - rejected),
    }
    assert len(with_budget) == EXPECTED_WITH_BUDGET, with_budget
    # Every manifest format the loader serves reaches the seam: the spec's v2
    # example, srm/v1 and legacy.
    names = {Path(p).name for p in with_budget}
    assert "api-full-v2.yaml" in names  # opensrm v2
    assert any(n.endswith(".reliability.yaml") for n in names)  # srm/v1
    assert "payment-api.yaml" in names  # legacy
