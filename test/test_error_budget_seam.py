"""The error-budget seam between nthlayer-generate and nthlayer-workers (opensrm-h0at).

measure read ``slo:error_budget:ratio``, a series nothing wrote, so every
availability SLO evaluated as no data. Each side had a green suite; nothing
checked that the reader asks for what the writer writes. This does: for every
real manifest, the error-budget series generate writes and the error-budget
queries measure sends must be the same set, in both directions.

Since opensrm-zo0o (rulings Z1, D5; generate 4.1.0, workers 4.2.0) both sides
cover every request-ratio SLO (availability, latency, error_rate), so the
seam is per SLO of each of those kinds, not availability alone. Each kind is
pinned by a named witness that must be written and read. Where generate
deliberately writes no budget that measure still asks for, the SLO is listed in
EXPECTED_READ_NOT_WRITTEN with the bead whose fix would give it one; a budget
written but not read is never expected.

The manifests are the spec's v2 examples and generate's shipped examples, not
fixtures written for this test. Nothing drops out unseen: a missing checkout
fails rather than skipping (the opensrm-oh27 lesson), every file the loader
rejects must be listed in EXPECTED_REJECTED with its reason, and the number
that write an error budget is pinned. A manifest that stops loading, or a
fixed one that starts, turns this red.

Run from the ecosystem root with CI's command (.github/workflows/error-budget-seam.yml).
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
EXPECTED_WITH_BUDGET = 24  # 2026-11-07, common 5.12.0 / generate 4.1.0 / workers 4.2.0

# Budgets measure asks for and generate's guard deliberately does not write
# (generate recording_rules `_budget_skip_reason`: no budget is better than a
# wrong one, and measure reports each as NO DATA). Keyed (corpus file, SLO
# name), valued by the bead whose fix should give it a budget. Exact, as the
# other pins: fixing a bead turns this red, and the entry goes.
_T13C = "opensrm-t13c: srm/v1 keeps a latency bound or an error_rate maximum in target"
_S7B1 = "opensrm-s7b1: legacy indicators[].threshold_ms is not read"
EXPECTED_READ_NOT_WRITTEN = {
    ("nthlayer-generate/examples/opensrm/ai-gate.reliability.yaml", "latency"): _T13C,
    ("nthlayer-generate/examples/opensrm/api-basic.reliability.yaml", "latency"): _T13C,
    ("nthlayer-generate/examples/opensrm/api-critical.reliability.yaml", "latency"): _T13C,
    ("nthlayer-generate/examples/opensrm/api-critical.reliability.yaml", "error_rate"): _T13C,
    ("nthlayer-generate/examples/opensrm/batch.reliability.yaml", "error_rate"): _T13C,
    ("nthlayer-generate/examples/opensrm/stream.reliability.yaml", "error_rate"): _T13C,
    ("nthlayer-generate/examples/opensrm/worker.reliability.yaml", "error_rate"): _T13C,
    ("nthlayer-generate/examples/services/analytics-stream.yaml", "event-latency-p99"): _S7B1,
    ("nthlayer-generate/examples/services/checkout-service.yaml", "latency-p95"): _S7B1,
    ("nthlayer-generate/examples/services/checkout-service.yaml", "latency-p99"): _S7B1,
    ("nthlayer-generate/examples/services/identity-service.yaml", "latency-p95"): _S7B1,
    ("nthlayer-generate/examples/services/identity-service.yaml", "latency-p99"): _S7B1,
    ("nthlayer-generate/examples/services/notification-worker.yaml", "processing-latency-p95"): _S7B1,
    ("opensrm/spec/v2/examples/migration/api-full-v2.yaml", "payment-api-latency"): (
        "opensrm-8jpp: a v2 latency bound is read from the objective"
    ),
}

# One budget per request-ratio kind that both sides must agree on, named so
# the check needs neither side's kind classifier. If a kind lost every budget
# (as latency and error_rate had none before zo0o), the set comparison alone
# would still pass.
KIND_WITNESSES = {
    "availability": ("nthlayer-generate/examples/opensrm/ai-gate.reliability.yaml", "availability"),
    "latency": ("nthlayer-generate/examples/services/admin-dashboard-api.yaml", "latency-p95"),
    "error_rate": ("opensrm/spec/v2/examples/migration/api-full-v2.yaml", "payment-api-error-rate"),
}

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
    return sorted(p for d in CORPUS_DIRS for p in d.rglob("*") if p.suffix in (".yaml", ".yml"))


def _load(path: Path) -> ReliabilityManifest | None:
    """The manifest, or None if the loader rejects it (checked against
    EXPECTED_REJECTED by the caller). Any other exception propagates to the
    caller, which reports it against the file."""
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


def _selector(manifest: ReliabilityManifest, slo: str) -> str:
    return ERROR_BUDGET_REMAINING.selector(service=manifest.name, slo=slo)


def _read(path: Path, spec_dir: Path) -> set[str]:
    """Each error-budget query measure sends for the manifest."""
    spec_dir.mkdir()
    shutil.copy(path, spec_dir / path.name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        loaded = load_specs(spec_dir)
    # A manifest load_manifest accepted must not fail measure's load; one that
    # did would read as no SLOs, and with no budget written would pass unseen.
    assert loaded.parse_failures == 0, "measure failed to load it (its reason is in the captured log)"
    return {s.query for s in loaded.slos if s.query_kind == "error_budget"}


def test_measure_reads_exactly_the_error_budget_generate_writes(tmp_path):
    with_budget = []
    rejected = set()
    read_not_written: set[tuple[str, str]] = set()
    agreed: set[tuple[str, str]] = set()
    problems: dict[str, object] = {}
    for i, path in enumerate(_corpus()):
        rel = str(path.relative_to(ROOT))
        try:
            manifest = _load(path)
            if manifest is None:
                rejected.add(rel)
                continue
            # A directory per file: load_specs reads every manifest in its directory.
            written, read = _written(manifest), _read(path, tmp_path / str(i))
        except Exception as exc:  # name the file; a bare traceback does not
            problems[rel] = f"raised {exc!r}"
            continue
        unread, unwritten = written - read, read - written
        # This file's pins, as the selector each would be read with.
        pinned = {
            slo: _selector(manifest, slo) for (f, slo) in EXPECTED_READ_NOT_WRITTEN if f == rel
        }
        file_problems = {}
        if unread:
            file_problems["written_not_read"] = sorted(unread)
        if unwritten - set(pinned.values()):
            file_problems["read_not_written, unpinned"] = sorted(unwritten - set(pinned.values()))
        if set(pinned.values()) - unwritten:
            file_problems["pinned, now written or not read"] = sorted(
                set(pinned.values()) - unwritten
            )
        if file_problems:
            problems[rel] = file_problems
        read_not_written |= {(rel, slo) for slo, sel in pinned.items() if sel in unwritten}
        agreed |= {(f, slo) for (f, slo) in KIND_WITNESSES.values()
                   if f == rel and _selector(manifest, slo) in written & read}
        if written:
            with_budget.append(rel)

    # Collected, then asserted once, so one failure does not hide another.
    if rejected != set(EXPECTED_REJECTED):
        problems["EXPECTED_REJECTED (add each new file with a reason or bead)"] = {
            "newly_rejected": sorted(rejected - set(EXPECTED_REJECTED)),
            "now_loads": sorted(set(EXPECTED_REJECTED) - rejected),
        }
    # A pinned file that left the corpus or stopped loading must not pass.
    if read_not_written != set(EXPECTED_READ_NOT_WRITTEN):
        problems["EXPECTED_READ_NOT_WRITTEN entries not seen"] = sorted(
            set(EXPECTED_READ_NOT_WRITTEN) - read_not_written
        )
    missing_kinds = sorted(k for k, w in KIND_WITNESSES.items() if w not in agreed)
    if missing_kinds:
        problems["request-ratio kinds whose witness budget is not written and read"] = missing_kinds
    if len(with_budget) != EXPECTED_WITH_BUDGET:
        problems[f"EXPECTED_WITH_BUDGET is {EXPECTED_WITH_BUDGET}, got {len(with_budget)}"] = (
            with_budget
        )
    # Every manifest format the loader serves reaches the seam.
    names = {Path(p).name for p in with_budget}
    formats = {
        "opensrm v2": "api-full-v2.yaml" in names,
        "srm/v1": any(n.endswith(".reliability.yaml") for n in names),
        "legacy": "payment-api.yaml" in names,
    }
    missing = [f for f, present in formats.items() if not present]
    if missing:
        problems["formats with no budget-writing manifest"] = missing
    assert not problems, problems
