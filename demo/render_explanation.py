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

**Do not use in assertions.** This helper's silent-success contract
would mask real issues if wired into a test.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from nthlayer_common.api_client import CoreAPIClient
from nthlayer_common.explanation import format_explanation
from nthlayer_workers.observe.assessment import from_dict
from nthlayer_workers.observe.explanation import ExplanationEngine
from nthlayer_workers.observe.store import MemoryAssessmentStore


async def _populate_store(
    client: CoreAPIClient, service: str, store: MemoryAssessmentStore,
) -> None:
    """Fetch slo_status + drift_signal for ``service`` and stage them.

    Per-kind iteration so a failure on one kind doesn't lose the other.
    Duplicate ids inside the store are silently skipped — the store
    rejects re-puts and we don't care about idempotency here.
    """
    for kind in ("slo_status", "drift_signal"):
        result = await client.get_assessments(
            service=service, kind=kind, limit=50,
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
                print(
                    f"  (skip malformed {kind}: {exc.__class__.__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            try:
                store.put(assessment)
            except ValueError:
                # Duplicate id — same record already staged. Fine.
                pass


async def _main(args: argparse.Namespace) -> None:
    store = MemoryAssessmentStore()
    async with CoreAPIClient(base_url=args.core_url) as client:
        await _populate_store(client, args.service, store)

    engine = ExplanationEngine()
    explanations = engine.explain_service(args.service, store)
    if not explanations:
        # No slo_status yet OR engine produced no rows. Honest signal
        # to the audience that the breach narrative cannot yet be told.
        print(f"  (no explanation available for {args.service})")
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

    try:
        asyncio.run(_main(args))
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
