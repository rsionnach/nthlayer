# nthlayer-learn — v1-draft

**Status:** Draft for implementation
**Date:** 2026-04-19
**Scope:** NthLayer reference implementation; not part of OpenSRM specification

---

## 1. Purpose

nthlayer-learn is the verdict data primitive and retrospective-analysis component of the NthLayer ecosystem. It owns:

1. **Content-addressed verdict identity.** Every verdict in the ecosystem is assigned an IPLD CID computed from its canonical content. CIDs are the primary key.
2. **Hash-chained verdict lineage.** Verdicts reference their parents by CID, producing an immutable lineage graph.
3. **Three-phase verdict lifecycle.** Each verdict has judgment, outcome, and lineage phases with well-defined state transitions.
4. **External tamper evidence.** Daily Merkle roots of the verdict set are anchored to Sigstore Rekor for third-party-verifiable integrity.
5. **Retrospective analysis.** When outcomes are resolvable, nthlayer-learn attributes outcomes to the decisions that produced them, producing calibration signals for nthlayer-measure and retrospective signals for the Bench.
6. **Retention maintenance.** The daily pruning job that enforces retention policy on older verdicts and assessments.

## 2. Position in the Pipeline

nthlayer-learn sits downstream of every component that produces verdicts. Its outputs feed nthlayer-measure (for calibration) and the Bench (for operator retrospective signals).

```
observe ──┐
measure ──┤
correlate ─┤
respond ──┼──→ learn ──→ measure (calibration signals)
authorise ┤         └──→ Bench   (retrospective signals)
executor ─┘
```

Unlike other components, learn doesn't produce action-triggering verdicts. Its outputs are analytical — retrospectives, calibration scores, lineage summaries. It is the ecosystem's memory.

## 3. Architectural Thesis

**Verdicts are immutable, content-addressed, and hash-chained.** Any mutation produces a new verdict with a new CID that references the old one as its parent. The past is never rewritten; the present is always built from it.

**Content addressing uses real IPLD CIDs, not bespoke hashes.** CIDs are shareable, verifiable, and embed the hash algorithm so future migrations are transparent. NthLayer deliberately uses the existing IPLD spec rather than inventing a parallel format.

**Tamper evidence is external.** Internal integrity (verdicts that hash correctly to their CID) is necessary but not sufficient for audit. External anchoring to Sigstore Rekor gives third-party-verifiable tamper evidence at essentially zero operational cost.

**Phase model makes decision lifecycle legible.** A verdict's three phases (judgment → outcome → lineage) correspond to "what we decided," "what happened," and "how this relates to other decisions." Separating these makes retrospective analysis straightforward.

## 4. The Verdict Primitive

### 4.1 Shape

```python
@dataclass
class Verdict:
    # Identity
    cid: CID
    type: VerdictType
    created_at: datetime
    created_by: PrincipalRef

    # Phase 1: Judgment
    judgment: Judgment

    # Phase 2: Outcome (may be null until resolved)
    outcome: Optional[Outcome]

    # Phase 3: Lineage
    parent_cids: list[CID]
    lineage_reasoning: Optional[str]

    # Pipeline metadata
    pipeline_latency_ms: int
    chain_depth: int
```

### 4.2 CID generation

Verdicts are serialised to canonical CBOR (deterministic byte sequence regardless of source language or field order) and then hashed. The hash plus hash-function identifier is wrapped as an IPLD CIDv1:

```python
from libipld import encode_dag_cbor
from libipld.cid import CID
import hashlib

def compute_cid(verdict: Verdict) -> CID:
    canonical_bytes = encode_dag_cbor(verdict.to_dict())
    digest = hashlib.sha256(canonical_bytes).digest()
    return CID.from_bytes(
        version=1,
        codec="dag-cbor",
        hash_function="sha2-256",
        digest=digest,
    )
```

Canonical CBOR ensures two verdicts with identical content produce identical CIDs regardless of who computed them, when, or in what language — this is what "content-addressed" means in practice.

### 4.3 Hash-chaining

A verdict's `parent_cids` field lists the CIDs of verdicts that informed this one. Because parents' CIDs are inputs to this verdict's CID computation, tampering with any ancestor invalidates every descendant's CID. This is the immutability guarantee.

### 4.4 Phase 1: Judgment

The decision itself. For an `action_request` verdict, the judgment is "the agent proposes rollback." For an `approval` verdict, the judgment is "the operator approves." For an `execution` verdict, the judgment is "the executor ran the action and observed this outcome."

Judgment content varies by verdict type; the common structure is:

```python
@dataclass
class Judgment:
    content: dict       # verdict-type-specific
    confidence: Optional[float]  # if the producer expressed confidence
    reasoning: Optional[str]     # prose reasoning
    evidence_cids: list[CID]     # verdicts cited as evidence
```

### 4.5 Phase 2: Outcome

What happened downstream. An outcome is *resolvable* through one of five paths:

**Lineage resolution.** A downstream verdict explicitly references this one. If an `execution` verdict cites an `approval` verdict, the approval's outcome is resolved by the execution. If the execution succeeded, the approval is attributed success.

**Calibration sampling.** Periodic audit samples — nthlayer-measure picks a fraction of decisions and evaluates them against ground truth (human review for agent decisions, labelled datasets for classifiers). Calibration results are recorded as outcome resolutions.

**Downstream signal.** An external signal (contract-breach verdict, incident-resolution verdict, customer-support ticket) that can be attributed to a decision. The attribution is explicit — a verdict declares which prior verdicts it resolves.

**Score-outcome divergence.** When a decision is made with expressed confidence and the outcome is later observed, divergence between expected and actual is itself the outcome signal. A high-confidence decision that turns out wrong is recorded with `outcome.calibration_delta` populated.

**Expiry.** For decisions where no outcome arrives within a configured window (default 7 days), the outcome resolves to "expired" — neither positive nor negative, but absence of signal. This is itself information: it surfaces decisions that have no closure mechanism.

```python
@dataclass
class Outcome:
    resolved_at: datetime
    resolution_type: Literal["lineage", "calibration", "downstream", "divergence", "expiry"]
    outcome_label: Literal["success", "failure", "partial", "expired"]
    resolving_verdict_cid: Optional[CID]
    calibration_delta: Optional[float]
    notes: Optional[str]
```

### 4.6 Phase 3: Lineage

The lineage phase is populated on creation (parent CIDs declared by the producer) but can be augmented as downstream verdicts accumulate. Specifically:

- `parent_cids` is immutable at creation
- `descendant_cids` (the inverse) is discoverable via indexed query, not stored in the verdict

This keeps verdicts immutable while making lineage traversal efficient.

## 5. Storage

### 5.1 Primary store

Verdicts are stored in the shared SQLite store with the schema defined in the serve-mode spec (§3.5). The `content` column holds the canonical CBOR encoding; the `cid` column holds the CID string.

```sql
CREATE TABLE verdicts (
    cid TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    service TEXT,
    created_at TIMESTAMP NOT NULL,
    pipeline_latency_ms INTEGER,
    chain_depth INTEGER,
    parent_cids TEXT,          -- JSON array of CID strings
    content BLOB NOT NULL      -- canonical CBOR
);
```

### 5.2 Lineage index

A secondary table indexes the lineage relationships for efficient traversal:

```sql
CREATE TABLE lineage (
    descendant_cid TEXT NOT NULL,
    ancestor_cid TEXT NOT NULL,
    hop_distance INTEGER NOT NULL,
    PRIMARY KEY (descendant_cid, ancestor_cid)
);

CREATE INDEX idx_lineage_ancestor ON lineage(ancestor_cid);
```

On each verdict write, the lineage table is populated with entries for all ancestors (the direct parents from `parent_cids` plus the transitive ancestors, joined from the parents' existing lineage rows). This lets "find all descendants of X" and "find all ancestors of Y" run as indexed queries.

### 5.3 Outcome resolution table

```sql
CREATE TABLE outcome_resolutions (
    verdict_cid TEXT PRIMARY KEY,
    resolved_at TIMESTAMP NOT NULL,
    resolution_type TEXT NOT NULL,
    outcome_label TEXT NOT NULL,
    resolving_verdict_cid TEXT,
    calibration_delta REAL,
    notes TEXT
);
```

Outcomes are mutable (a verdict can be re-resolved if stronger evidence arrives), but all prior resolutions are preserved in an `outcome_history` append-only table for audit purposes.

## 6. Sigstore Rekor Anchoring

### 6.1 Mechanism

Daily (configurable, default 24h), nthlayer-learn:

1. Gathers all verdicts written in the prior window, ordered by CID
2. Computes a Merkle root over the ordered CID list
3. Signs the root with the deployment's Ed25519 key
4. Submits `{merkle_root, signature, window_start, window_end, key_id}` to the Sigstore public Rekor instance via `sigstore-python`
5. Records the Rekor log index and UUID in the `rekor_anchors` table

### 6.2 Submission format

```python
from sigstore.rekor import RekorClient
from pynacl.signing import SigningKey

rekor = RekorClient.production()

def anchor_daily_root(date: Date):
    verdicts = store.get_verdicts_in_window(date)
    ordered_cids = sorted(v.cid for v in verdicts)

    merkle_root = compute_merkle_root(ordered_cids)

    signing_key = load_signing_key()
    signature = signing_key.sign(merkle_root.encode())

    anchor_payload = {
        "deployment_id": config.deployment_id,
        "window_start": date.isoformat(),
        "window_end": (date + timedelta(days=1)).isoformat(),
        "merkle_root": merkle_root,
        "signature": signature.hex(),
        "key_id": config.signing_key_id,
        "verdict_count": len(ordered_cids),
    }

    entry = rekor.create_entry(
        kind="hashedrekord",
        content=json.dumps(anchor_payload).encode(),
    )

    store.record_anchor(date, merkle_root, entry.log_index, entry.uuid)
```

### 6.3 Verification workflow

Any third party with access to the verdict set can verify the anchor:

1. Query `rekor_anchors` for the date of interest
2. Fetch the entry from Rekor by UUID
3. Re-compute the Merkle root over the claimed verdict set
4. Verify the signature against the deployment's public key
5. Confirm the Merkle root matches

If any step fails, the audit trail has been tampered with or is incomplete. If all pass, the verdict set's integrity for that day is publicly attested.

### 6.4 Why this is cheap

- One Rekor entry per day, regardless of verdict volume
- Rekor entries are well under the 100KB cap for anchor payloads
- Sigstore public Rekor instance absorbs availability concern
- No ongoing operational cost beyond running the daily job
- Payload contains no secrets — it's public by design

### 6.5 Why this is disproportionately valuable

The common audit-trail posture is "trust us, our logs are tamper-proof." Rekor anchoring converts this from a trust claim to a verifiable property. For compliance audiences (SOC 2, ISO 27001, regulated industries), the upgrade from "claim" to "property" is substantial. For CNCF positioning, aligning with the Sigstore ecosystem is low-friction credibility.

## 7. Retrospective Analysis

### 7.1 Decision-to-outcome attribution

When a verdict's outcome resolves, learn computes attributions:

- Which ancestor verdicts contributed to this outcome?
- Were any ancestor decisions pivotal (would the outcome differ if that decision had gone the other way)?
- What calibration signal does this outcome produce for the decision-makers?

Attribution is structural (follow the lineage graph) supplemented by LLM-assisted reasoning for the "pivotal" question. The LLM sees the decision chain and the outcome and produces a structured judgement about which decisions materially affected the result.

### 7.2 Calibration signal generation

For each ancestor verdict whose outcome resolves:

```python
@dataclass
class CalibrationSignal:
    decision_cid: CID
    decision_maker: PrincipalRef       # agent or human
    expressed_confidence: Optional[float]
    observed_outcome: str              # success | failure | partial
    calibration_delta: Optional[float] # expected_vs_actual if confidence was expressed
    attribution: AttributionWeight     # how much this decision affected the outcome
    created_at: datetime
```

These signals feed nthlayer-measure, which aggregates them into judgment-SLO statistics.

### 7.3 Operator retrospective signals

When a case previously handled by an operator reaches outcome resolution, a retrospective signal is emitted for that operator's history:

- "Your approval on case bafyrei...abc on 2026-04-19 contributed to resolution of INC-2026-04-01847 within 14 minutes (success)"
- "Your rejection of action_request bafyrei...def on 2026-04-20 was followed by a different action that succeeded (outcome: neutral)"

These signals are *operator-facing only*, rendered in the Bench's retrospective section. Aggregation into team-level statistics is an ecosystem concern, but raw operator retrospective signals belong to the operator.

### 7.4 Organisational learning signals

At longer time horizons (weeks, months), learn produces organisational signals:

- Which action types have the highest outcome-success rate?
- Which services see the most retrospective positive signals?
- Which decisions were most often pivotal?

These signals are structured and stored in the `retrospective_signals` table; rendering them is out of scope for learn itself.

## 8. Retention Maintenance

### 8.1 Policy

Retention defaults from the serve-mode spec (§3.7):

- verdicts: 365 days
- assessments: 90 days
- cases: 365 days
- change_freezes: active indefinitely, lifted 90 days
- heartbeats: 1 day
- suppressions: 90 days
- rekor_anchors: permanent

### 8.2 Pruning job

Runs daily. For each retention-constrained table:

1. Identify rows older than the retention window
2. Check for references from younger rows (a verdict parented by an older verdict whose own retention has expired — the parent is kept if any descendant references it)
3. Delete unreferenced rows
4. Vacuum the database periodically (weekly)

### 8.3 Anchor preservation

rekor_anchors are never pruned regardless of verdict retention. The anchor contains only the Merkle root and metadata, not the verdicts themselves, so keeping it permanently is cheap and preserves the integrity claim even after verdicts are purged.

### 8.4 Compliance variations

Deployments in regulated industries may require longer retention. The retention policy is configurable per table. Deployments may also externalise retained verdicts to long-term storage (S3 Glacier, Azure Archive) before pruning; this is deployment-specific and outside the spec.

## 9. Component Responsibilities Summary

At a cycle boundary, nthlayer-learn:

1. Processes new verdicts since last cursor (compute lineage table entries, write to lineage index)
2. Processes newly-resolved outcomes (compute attributions, generate calibration signals, emit operator retrospective signals)
3. Runs the retention pruning job if the configured interval has elapsed
4. Runs the Rekor anchoring job if the configured interval has elapsed
5. Emits heartbeat with state

## 10. Failure Modes

**Rekor submission fails.** Anchor is retried for up to 24 hours. If still failing, a degraded-state verdict is emitted; anchor resumes when Rekor is reachable. Missing days are not back-filled — the audit trail has a gap, which is itself auditable.

**Lineage index inconsistency.** On startup, learn verifies lineage table consistency against the verdicts table. Inconsistencies are rebuilt from source (expensive but correct). This shouldn't happen but guards against corruption.

**Outcome attribution LLM unavailable.** Fall back to structural attribution only. Pivotal-decision determination is marked "unavailable." Calibration signals are still generated.

**Canonical CBOR encoding drift.** If a new library version produces different byte sequences for the same content, CIDs change. This would be catastrophic for the immutability guarantee. The library version is pinned exactly; version changes require migration scripts that re-compute affected CIDs and update the lineage graph.

## 11. Implementation Notes

### 11.1 Library dependencies

- `libipld` (MarshalX/python-libipld, Rust+PyO3, MIT) — CID generation, CBOR encoding
- `sigstore-python` (sigstore/sigstore-python, Apache-2.0) — Rekor client
- `pynacl` — Ed25519 signing
- `sqlite-utils` — store access ergonomics
- `pydantic` — data models

### 11.2 Performance characteristics

For a mid-sized deployment (~10,000 verdicts per day):

- Lineage index insertion per verdict: < 5ms
- Daily Merkle root computation: < 2 seconds
- Rekor submission: 1-5 seconds (network-bound)
- Retention pruning per day: < 30 seconds

None of these are hot-path sensitive. learn can run on a small cycle (every few minutes is fine).

### 11.3 Lineage traversal

Traversals use the pre-computed lineage table:

```python
def ancestors_of(cid: CID, max_hops: int = None) -> list[Verdict]:
    query = "SELECT ancestor_cid, hop_distance FROM lineage WHERE descendant_cid = ?"
    if max_hops:
        query += " AND hop_distance <= ?"
    ancestor_cids = db.execute(query, ...).fetchall()
    return [load_verdict(c) for c in ancestor_cids]
```

This is O(lookup) rather than O(graph traversal) which matters as the graph grows.

## 12. Future Work

**Verkle trees for Merkle root.** If verdict volume grows significantly, Verkle trees compress the inclusion proof size meaningfully. Not urgent.

**External lineage federation.** Multiple NthLayer deployments sharing lineage for cross-deployment decisions. Out of scope for v1.

**Graph-based retrospective queries.** "Show me all decisions upstream of this incident" as a first-class query. Foundationally supported by the lineage table but the operator UX is future work.

**Selective anchoring.** For high-volume deployments, anchor the hourly Merkle root rather than daily. Simple extension.

## 13. References

- libipld: https://github.com/MarshalX/python-libipld
- IPLD CID specification: https://github.com/multiformats/cid
- CBOR RFC 8949: https://www.rfc-editor.org/rfc/rfc8949
- sigstore-python: https://github.com/sigstore/sigstore-python
- Sigstore Rekor: https://github.com/sigstore/rekor
- PyNaCl: https://pynacl.readthedocs.io/
- OpenSRM serve mode v2.1 (store, heartbeats, retention)

## 14. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1-draft | 2026-04-19 | Initial spec |
