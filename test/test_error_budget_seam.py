"""The error-budget seam between nthlayer-generate and nthlayer-workers (opensrm-h0at).

measure read ``slo:error_budget:ratio``, a series nothing wrote, so every
availability SLO evaluated as no data. Each side had a green suite; nothing
checked that the reader asks for what the writer writes. This does: for every
real manifest, the error-budget series generate writes and the error-budget
queries measure sends must be the same set, in both directions.

The manifests are the spec's own examples and generate's shipped examples,
not fixtures written for this test. Both corpora must be present: a missing
checkout fails here rather than skipping (the opensrm-oh27 lesson), and a
minimum count stops an emptied corpus from passing vacuously.

Run from the ecosystem root, against the published packages:

    uv run --with nthlayer-generate --with nthlayer-workers --with pytest \\
        pytest nthlayer/test/test_error_budget_seam.py
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

from nthlayer_common.manifest import ERROR_BUDGET_REMAINING, load_manifest
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
# 24 manifests wrote an error budget when this test was written (2026-11-02).
MIN_WITH_BUDGET = 20


def _corpus() -> list[Path]:
    missing = [d for d in CORPUS_DIRS if not d.is_dir()]
    assert not missing, f"corpus checkout missing: {missing}"
    return sorted(p for d in CORPUS_DIRS for p in d.rglob("*.yaml"))


def _load(path: Path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return load_manifest(path)
        except Exception:  # archetypes etc. that the loader rejects
            return None


def _written(manifest) -> set[str]:
    """Each error-budget series generate writes, as the selector reading it."""
    return {
        ERROR_BUDGET_REMAINING.selector(service=r.labels["service"], slo=r.labels["slo"])
        for group in build_recording_rules_from_manifest(manifest)
        for r in group.rules
        if r.record == ERROR_BUDGET_REMAINING.metric
    }


def _read(path: Path, tmp_path: Path) -> set[str]:
    """Each error-budget query measure sends for the manifest."""
    spec_dir = tmp_path / path.stem
    spec_dir.mkdir()
    shutil.copy(path, spec_dir / path.name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        slos = load_specs(spec_dir).slos
    return {s.query for s in slos if s.query_kind == "error_budget"}


def test_measure_reads_exactly_the_error_budget_generate_writes(tmp_path):
    with_budget = []
    mismatches = {}
    for path in _corpus():
        manifest = _load(path)
        if manifest is None:
            continue
        written, read = _written(manifest), _read(path, tmp_path)
        if written != read:
            mismatches[str(path.relative_to(ROOT))] = {
                "written_not_read": sorted(written - read),
                "read_not_written": sorted(read - written),
            }
        if written:
            with_budget.append(path)

    assert not mismatches, mismatches
    assert len(with_budget) >= MIN_WITH_BUDGET, [str(p) for p in with_budget]
    # Every manifest format the loader serves reaches the seam: the spec's v2
    # example, srm/v1 and legacy.
    names = {p.name for p in with_budget}
    assert "api-full-v2.yaml" in names
    assert any(n.endswith(".reliability.yaml") for n in names)
    assert "payment-api.yaml" in names
