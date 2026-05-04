# VERDICT-INTEGRATION.md — Ecosystem Update Spec

This document tells Claude Code exactly what to change in each ecosystem component to integrate the verdict primitive. Read VERDICT.md first for the full verdict specification. This document only covers the integration changes.

The verdict repo should be created first (from VERDICT.md). Then update each component in the order listed below.


## 1. OpenSRM Spec Repo (`opensrm/`)

### What changes

The spec must define verdicts as a recognised data primitive and reference the verdict repo.

### Files to update

**README.md:**
- Add the verdict repo to the implementations table (alongside Arbiter, NthLayer, SitRep, Mayday)
- In the ecosystem overview section, add Verdict as a Data Primitive in the component taxonomy:
  - Data Sources: OpenSRM manifests, Prometheus/OTel metrics, change event logs
  - **Data Primitives: Verdict (schema + transport library, no reasoning)**
  - Tools: NthLayer
  - Agents: Arbiter, SitRep, Mayday

**spec/ (or wherever the specification content lives):**
- Add a section on the verdict schema as a recognised format in the spec, similar to how the change event schema is defined. The spec doesn't own the verdict schema (the verdict repo does), but it references it and declares that ecosystem components MUST produce verdicts for their judgment outputs.
- Add a section clarifying the relationship between verdicts and OTel semantic conventions: verdicts are the data record, `gen_ai.decision.*` and `gen_ai.override.*` are the OTel transmission format. The spec defines the OTel conventions. The verdict repo defines the storage schema. The verdict library handles the mapping between them.
- In the judgment SLO section, add a note: "Judgment SLO metrics (reversal rate, calibration score, etc.) are computed from verdict records. Each evaluation produces a verdict. Each human override resolves a verdict. The SLO aggregation is a query over resolved verdicts."

**ECOSYSTEM.md (if it exists):**
- Add Verdict to the integration diagram. Verdict sits below all components (every component depends on the verdict library, none depend on each other).
- Update the data flows to show that verdicts are the common output format for all judgment-producing components.
- In the learning loop section, clarify that the learning loop flows through verdicts: Mayday produces investigation and remediation verdicts → human overrides produce resolution verdicts → resolution verdicts feed calibration for all components in the chain via lineage.


## 2. Arbiter Repo (`arbiter/`)

### What changes

The Arbiter's evaluation output becomes a verdict. The self-calibration loop becomes verdict accuracy queries. The governance system reads verdict metrics.

### Files to update

**README.md:**
- Add a "Verdicts" section (after the Self-Calibration section) explaining that every evaluation the Arbiter performs produces a verdict. Link to the verdict repo.
- Update the Self-Calibration section: self-calibration is computed from verdict accuracy queries (`nthlayer-learn accuracy --producer arbiter`). The false accept rate is the override rate on verdicts where `judgment.action == approve`. Precision is the confirmation rate on verdicts where the Arbiter flagged issues.
- Update the OTel metrics reference section: the Arbiter emits `gen_ai.decision.*` OTel events. These events are produced by the verdict library's OTel emission layer when a verdict is created or resolved. The metric names (`gen_ai_decision_total`, `gen_ai_override_reversal_total`, etc.) are unchanged.
- Update the Adapters section: for systems that already produce verdicts natively, no adapter is needed. The Arbiter can consume verdicts directly. For systems that don't produce verdicts, the adapter's job is to convert the system's output format into a verdict before evaluation.

**Implementation code (wherever the evaluation pipeline is):**
- Add the verdict library as a dependency
- When the Arbiter evaluates agent output, the result must be stored as a verdict via `verdict.create()`:
  ```python
  v = verdict.create(
      subject=Subject(
          type="agent_output",
          agent=agent_name,
          service=service_name,
          ref=diff_ref,
          summary=diff_summary,
          content_hash=hash_of_input
      ),
      judgment=Judgment(
          action="approve",  # or "reject", "flag", "escalate"
          score=evaluation_score,
          confidence=evaluation_confidence,
          dimensions=dimension_scores,
          reasoning=evaluation_reasoning
      ),
      producer=Producer(
          system="arbiter",
          instance=instance_id,
          model=model_used,
          prompt_version=prompt_version
      )
  )
  store.put(v)
  ```
- When a human overrides an Arbiter evaluation, the override must resolve the verdict:
  ```python
  verdict.resolve(
      verdict_id=original_verdict_id,
      status="overridden",
      override=Override(
          by="human:" + human_id,
          action=what_the_human_decided,
          reasoning=why_they_overrode
      )
  )
  ```
- The existing self-calibration code should be refactored to use `verdict.accuracy()` queries instead of maintaining separate calibration state. If the existing code computes reversal rates and false accept rates, those computations should be replaced with verdict accuracy queries over the same data.
- The governance system should read verdict accuracy metrics (via Prometheus or via direct verdict store queries) to make autonomy decisions.

**Configuration:**
- Add verdict store configuration to the Arbiter's config file:
  ```yaml
  verdict:
    store:
      backend: sqlite        # sqlite | postgres | clickhouse
      path: verdicts.db      # for sqlite
  ```


## 3. SitRep Repo (`sitrep/`)

### What changes

SitRep's output format changes from a bespoke SituationSnapshot to verdicts. SitRep also ingests verdicts from other components as events.

### Files to update

**README.md:**
- Add a "Verdicts" section explaining that SitRep's correlation assessments are produced as verdicts. Each correlation assessment ("this deploy caused this latency spike") is a verdict with `subject.type: correlation`.
- Explain that SitRep consumes verdicts from other components (Arbiter quality verdicts arrive as events, are indexed, and participate in pre-correlation).
- Link to the verdict repo.

**Implementation code:**

*Ingestion changes:*
- The EventStore/ingestion layer should accept `verdict` as an event type in the SitRepEvent schema:
  ```typescript
  type: EventType;  // alert | metric_breach | change | quality_score | verdict | custom
  ```
- Verdicts from external sources (e.g., Arbiter quality verdicts) arrive via the same ingestion path as any other event. They are indexed in the store and participate in pre-correlation (temporal grouping, topology grouping, change indexing all work on verdict events the same way they work on alert events).

*Output changes:*
- The snapshot generator's output changes from `SituationSnapshot` to one or more verdicts:
  ```typescript
  // Before: custom schema
  interface SituationSnapshot {
    groups: Array<{ assessment, causality, priority, ... }>
    overallAssessment: string
  }

  // After: verdicts
  // Each correlation assessment is a verdict:
  const correlationVerdict = verdict.create({
    subject: {
      type: "correlation",
      service: affectedService,
      ref: correlationGroupId,
      summary: "deploy v2.3.1 correlated with latency spike on payment-api"
    },
    judgment: {
      action: "flag",  // flag for human attention
      score: null,     // correlations don't have a quality score
      confidence: 0.71,
      reasoning: "temporal proximity 12 minutes, same dependency chain, deploy touches connection pooling config",
      tags: ["latency", "deploy", "payment-api"]
    },
    producer: {
      system: "sitrep",
      model: modelUsed
    }
  });

  // The overall snapshot is a parent verdict linking the individual correlations:
  const snapshotVerdict = verdict.create({
    subject: {
      type: "correlation",
      service: null,  // system-wide
      summary: "Situation snapshot: 2 active correlation groups, 1 P0"
    },
    judgment: {
      action: "escalate",  // or "watch" for WATCHING mode
      confidence: 0.68,
      reasoning: "P0 group on payment-api with recent deploy correlation. Recommend ALERT state transition."
    },
    producer: { system: "sitrep" },
    lineage: {
      children: [correlationVerdict.id, /* other correlation verdict IDs */]
    }
  });
  ```
- Downstream consumers (Mayday, dashboards, human operators) receive verdicts instead of the custom snapshot schema. Mayday reads SitRep's correlation verdicts via the verdict store query interface.

*State machine:*
- State transitions (WATCHING → ALERT → INCIDENT → DEGRADED) remain transport decisions based on pre-correlation output. No change here.
- In DEGRADED mode (model unavailable), SitRep still produces verdicts but with `confidence: 0.0` and `reasoning: "template-based, model unavailable"`.

**Configuration:**
- Add verdict store configuration (same pattern as Arbiter):
  ```yaml
  verdict:
    store:
      backend: sqlite
      path: verdicts.db
  ```


## 4. Mayday Repo (`mayday/`)

**Note:** MAYDAY.md contains the full implementation specification for Mayday (coordinator, agent interfaces, prompt templates, safe action registry, incident lifecycle, post-incident processing). This section covers only the verdict-specific integration. Read MAYDAY.md for the complete picture.

### What changes

Mayday's agents produce verdicts for every judgment (triage, investigation, communication, remediation). Mayday consumes SitRep's correlation verdicts as input. The verdict lineage chain links everything together. The coordinator manages verdict emission and lineage linking. Post-incident processing exports the resolved verdict chain as a replay scenario.

### Files to update

**README.md:**
- Add a "Verdicts" section explaining that each agent role produces verdicts:
  - Triage agent: `subject.type: triage` (severity assessment, blast radius estimate)
  - Investigation agent: `subject.type: investigation` (hypotheses, root cause declaration)
  - Communication agent: `subject.type: communication` (status update content, audience targeting) (note: communication verdicts are lower stakes, but still measurable through edit rates)
  - Remediation agent: `subject.type: remediation` (proposed fix, rollback decision)
- Explain the lineage chain: SitRep correlation verdicts → Mayday triage verdict → investigation verdict → remediation verdict → human override verdict. One human override at any point in the chain feeds calibration signals back to every component via lineage traversal.
- Add the post-incident learning loop through verdicts: after an incident, the resolved verdict chain (with confirmed and overridden outcomes) becomes training data for the evaluation datasets. Curate the most instructive chains into the eval/ directory.
- Link to the verdict repo.

**Implementation code:**

*Consuming SitRep verdicts:*
- When Mayday activates, it queries the verdict store for SitRep's recent correlation verdicts:
  ```python
  sitrep_verdicts = verdict_store.query(
      producer_system="sitrep",
      subject_type="correlation",
      time_range=last_30_minutes,
      min_confidence=0.3  # include low-confidence correlations during incidents
  )
  ```
- These verdicts provide the incident context. Their timestamps tell Mayday how stale they are. Their confidence tells Mayday how much to trust them. If no SitRep verdicts are available, Mayday operates without pre-correlated context (reduced quality, noted in its own verdicts' reasoning).

*Producing verdicts:*
- Every agent judgment produces a verdict with lineage linking to the SitRep verdicts that informed it:
  ```python
  triage_verdict = verdict.create(
      subject=Subject(
          type="triage",
          service=incident_service,
          ref=incident_id,
          summary="Incident on payment-api: latency spike affecting checkout"
      ),
      judgment=Judgment(
          action="escalate",
          confidence=0.75,
          reasoning="P99 latency 5x SLO target, checkout flow impacted, recent deploy correlation from SitRep",
          tags=["severity-2", "customer-facing"]
      ),
      producer=Producer(system="mayday", instance="triage-agent"),
      lineage=Lineage(
          context=[sitrep_verdict.id for sitrep_verdict in sitrep_verdicts]
      )
  )
  ```

*Human overrides:*
- When a human overrides any Mayday verdict (changes severity, rejects root cause, modifies remediation), the verdict is resolved as overridden with the human's reasoning.
- Because of lineage, this override propagates calibration signals: if the triage was overridden, the triage agent's accuracy is affected. If the investigation was confirmed but the remediation was overridden, only the remediation agent's accuracy is affected.

**Configuration:**
- Add verdict store configuration (same pattern as Arbiter and SitRep):
  ```yaml
  verdict:
    store:
      backend: sqlite
      path: verdicts.db
  ```


## 5. NthLayer Repo (`nthlayer/`)

### What changes

NthLayer doesn't produce or consume verdicts directly. NthLayer queries Prometheus metrics that originate from verdicts. No code changes to NthLayer are needed for verdict integration as long as the OTel metric names remain `gen_ai_decision_*` and `gen_ai_override_*` (which they do).

### Files to update

**README.md only:**
- In the Judgment SLO support section, add a note explaining that the `gen_ai_decision_*` and `gen_ai_override_*` metrics NthLayer queries originate from verdict records. The Arbiter (and other verdict-producing components) emit these metrics via the verdict library's OTel layer. NthLayer doesn't need to know about verdicts directly. It queries standard Prometheus metrics.
- In the ecosystem section, add the verdict repo to the component table with a note: "Verdict is the data primitive that produces the metrics NthLayer queries. NthLayer does not depend on the verdict library."
- Link to the verdict repo.


## 6. Ecosystem-Level Documentation

### BRIEF.md

The BRIEF.md has already been updated with the Arbiter's OTel metric emission and NthLayer's judgment SLO recording rules. The remaining update for BRIEF.md:

- In the component taxonomy section, add Verdict as a Data Primitive
- In the ecosystem component list, add a Verdict section between OpenSRM and Arbiter:

  ```
  ### Verdict

  **Repo: `verdict`**

  **One-liner:** The atomic unit of AI judgment, like Beads for task management.

  **What it is:** A schema and transport library for recording AI decisions and
  closing the loop on whether they were correct. Every time any component makes
  a judgment (evaluating quality, correlating signals, triaging incidents), it
  produces a verdict. Verdicts track what was evaluated, what was decided, how
  confident the producer was, and eventually whether the decision was right.

  **What it is not:** A framework, an agent, or a model. Verdicts are pure data
  and pure transport. No reasoning involved. The library creates, stores, links,
  resolves, and queries verdicts. That's it.

  **Independence:** Verdicts work without the OpenSRM ecosystem. Any system where
  an AI makes decisions that can later be validated can use verdicts. Content
  moderation, medical triage, legal review, code review, recommendation systems.
  The OpenSRM ecosystem is the most sophisticated consumer, not the only one.

  **Key concepts:**
  - Three phases: judgment (at decision time), outcome (filled later), lineage (links between verdicts)
  - Outcome resolution is the critical feature: confirmed, overridden, partial, superseded, expired
  - Replay: every verdict contains its input reference, so historical judgments can be re-evaluated
  - Evaluation datasets: curated verdicts with known outcomes, stored in Git, used for bootstrapping calibration
  - Accuracy queries: compute confirmation rate, override rate, calibration gap from resolved verdicts
  - OTel emission: verdicts produce gen_ai.decision.* and gen_ai.override.* OTel events automatically
  ```

- In the data flows section, add a verdict flow:
  ```
  - **Verdict flow:** All judgment-producing components (Arbiter, SitRep, Mayday agents) produce
    verdicts via the verdict library → verdicts stored in component-local verdict stores → verdict
    OTel emission produces gen_ai.* metrics → Prometheus → NthLayer queries for judgment SLO
    compliance → deploy gates. Human overrides resolve verdicts → resolved verdicts feed accuracy
    queries → accuracy informs Arbiter governance decisions. Verdict lineage links the full chain
    so one human override at any point calibrates every component upstream.
  ```

- In the integration diagram, add Verdict as a foundation layer below all components.

### ECOSYSTEM.md guidance

- Update the learning loop section to show that the learning loop flows through verdicts
- Update the component taxonomy to include the Data Primitives category


## Implementation Order

1. **Create verdict repo** (from VERDICT.md): schema, Python library, SQLite store, CLI
2. **Update Arbiter**: add verdict library dependency, refactor evaluation output to produce verdicts, refactor self-calibration to use verdict accuracy queries
3. **Update SitRep** (see SITREP-PRECORRELATION.md for full spec): add verdict as an ingestion event type, refactor snapshot output to produce correlation verdicts with lineage
4. **Implement Mayday** (see MAYDAY.md for full spec): coordinator, agent interfaces, verdict consumption from SitRep, verdict production from each agent role, safe action registry, post-incident scenario export
5. **Update NthLayer README**: documentation only, no code changes
6. **Update OpenSRM spec**: add verdict as a recognised data primitive, update semantic conventions documentation
7. **Update BRIEF.md**: add Verdict component section, update data flows, update integration diagram

Items 1-2 are the critical path (the Arbiter already exists and is the first component to integrate). Item 3 depends on SitRep being implemented (see SITREP-PRECORRELATION.md). Item 4 depends on both verdicts and SitRep (see MAYDAY.md). Items 5-7 are documentation updates that can happen any time.
