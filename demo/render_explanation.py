"""Render BudgetExplanation table for demo Step 4 (opensrm-42y.4).

Pattern (b) per the 42y.16 audit: ingest worker-emitted ``slo_status``
and ``drift_signal`` assessments from core's HTTP API, hand them to
the in-process ``ExplanationEngine``, and format the resulting
``BudgetExplanation`` objects for the demo terminal.

The engine lives in ``nthlayer-workers``, which is *not* installed in
the bench venv used for ``test/three_tier_assertions.py`` — so this
helper is intentionally separate and is invoked via ``$RUN_WORKERS
python`` from ``demo.sh``.

Fail-open by design: any failure (unreachable core, malformed
assessment payload, missing service) prints a single diagnostic line
to stderr and exits 0. The demo runs under ``set -euo pipefail``;
aborting on a render hiccup would kill the scenario. Operator
diagnostics are routed through stderr, demo narrative through stdout.

Partial-data semantics: if one of the two assessment-kind fetches
(``slo_status`` / ``drift_signal``) fails while the other succeeds,
the helper proceeds with the partial store. The engine renders
whatever ``slo_status`` it has; drift causes simply don't get
enriched. Intentional for a demo (best-effort > silent abort), but
keep in mind when reading the output — the stderr diagnostic is the
only signal that enrichment was skipped.

**Do not use in assertions.** This helper's silent-success contract
would mask real issues if wired into a test.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys

from nthlayer_common.api_client import CoreAPIClient
from nthlayer_common.explanation import format_explanation
from nthlayer_workers.observe.assessment import from_dict
from nthlayer_workers.observe.explanation import ExplanationEngine
from nthlayer_workers.observe.store import MemoryAssessmentStore

# Exactly the assessment kinds ExplanationEngine consumes. Documented as a
# constant so a future engine extension flows here without a magic-tuple
# search across the helper.
_ENGINE_INPUT_KINDS = ("slo_status", "drift_signal")


async def _populate_store(
    client: CoreAPIClient, service: str, store: MemoryAssessmentStore,
) -> None:
    """Fetch slo_status + drift_signal for ``service`` and stage them.

    Per-kind iteration so a failure on one kind doesn't lose the other.
    Duplicate ids inside the store are silently skipped — the store
    rejects re-puts and we don't care about idempotency here.
    """
    for kind in _ENGINE_INPUT_KINDS:
        # Explicit high limit. NB: limit=0 on the core API means literal
        # "return zero rows", NOT "return all" — surfaced as a real
        # regression during 42y.9's E2E verification (the engine ran
        # against an empty store and returned no explanations). limit=200
        # covers ~40 collect cycles per SLO at the 5s demo interval,
        # plenty of headroom for the demo scenario's 2-minute window
        # while keeping the per-service fetch bounded.
        result = await client.get_assessments(
            service=service, kind=kind, limit=200,
        )
        if not result.ok:
            print(
                f"  ({kind} fetch failed for {service}: {result.error})",
                file=sys.stderr,
            )
            continue
        for raw in (result.data or []):
            try:
                assessment = from_dict(raw)
            except Exception as exc:
                # Broad catch: from_dict raises KeyError on missing fields
                # and TypeError/ValueError on type mismatches; both surface
                # here under fail-open semantics.
                print(
                    f"  (skip malformed {kind}: {exc.__class__.__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            # Duplicate id — same record already staged. Fine.
            with contextlib.suppress(ValueError):
                store.put(assessment)


async def _render(core_url: str, service: str) -> None:
    """Fetch, populate, explain, format. Pure data flow — no argparse coupling."""
    store = MemoryAssessmentStore()
    async with CoreAPIClient(base_url=core_url) as client:
        await _populate_store(client, service, store)

    engine = ExplanationEngine()
    explanations = engine.explain_service(service, store)
    if not explanations:
        # Narrative line (stdout, audience-facing): explains absence of a
        # table when no slo_status is in core yet, or the engine produced
        # no rows. Distinct from the diagnostic lines above which go to
        # stderr per the module's stdout=narrative / stderr=diagnostic
        # contract.
        print(f"  (no explanation available for {service})")
        return

    for exp in explanations:
        for line in format_explanation(exp, "table").splitlines():
            print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="render-explanation",
        description=(
            "Render BudgetExplanation table for demo Step 4 "
            "(opensrm-42y.4). Demo-only; do not use in assertions."
        ),
    )
    parser.add_argument("--core-url", default="http://localhost:8000")
    parser.add_argument("--service", required=True)
    args = parser.parse_args(argv)

    # argparse(required=True) only checks presence — an empty string
    # would pass argparse and then silently fetch the whole portfolio
    # (CoreAPIClient drops empty-string service from query params),
    # producing a confused multi-service table under a "service=''"
    # heading. Reject the empty-string case explicitly.
    if not args.service.strip():
        parser.error("--service must be a non-empty service name")

    try:
        asyncio.run(_render(args.core_url, args.service))
    except Exception as exc:
        # Demo helper: a connection error or unexpected payload must
        # not bubble a Python traceback into the demo terminal. Single
        # diagnostic line on stderr; exit 0 so the scenario continues.
        print(
            f"  (explanation render failed: {exc.__class__.__name__}: {exc})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
