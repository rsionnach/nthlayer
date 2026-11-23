"""The OTel Collector config turns A1 §4 log events into §4.5 series.

Runs the collector image pinned in test/docker-compose.yml with the committed
test/otel-collector.yaml, sends a fixed set of OTLP log records over
OTLP/HTTP JSON, scrapes the Prometheus exporter and checks every sample of
nthlayer_decisions_total, nthlayer_reversals_total and nthlayer_outcomes_total
[opensrm-s4ui], and of the nthlayer_decision_confidence gauge [opensrm-taz2].

Fixture provenance: every event below is built from the attribute tables of
opensrm/OPENSRM-TELEMETRY-ADDENDUM-v2.md §4.1-§4.3 (Required attributes,
enumerated values where the spec enumerates them, the spec's own examples
where it gives examples) and the carriage of §4.0 plus nthlayer-common's
telemetry (event name in LogRecord.event_name, no body, Timestamp set per
T1). The expected labels come from §4.5 N3, not from the config.

Needs Docker. Without it the test FAILS (never skips): a skipped collector
test is a green suite that checks nothing.

    uv run --no-project --with pytest --with pyyaml pytest -q test/test_otel_collector.py
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

TEST_DIR = Path(__file__).resolve().parent
CONFIG = TEST_DIR / "otel-collector.yaml"
COMPOSE = TEST_DIR / "docker-compose.yml"

COUNTERS = ("nthlayer_decisions_total", "nthlayer_reversals_total", "nthlayer_outcomes_total")
# §4.5's name for the gauge of nthlayer.decision.confidence: N1 prefix, N2 no
# unit suffix for a ratio, no `_total` for a gauge.
CONFIDENCE = "nthlayer_decision_confidence"
FAMILIES = (*COUNTERS, CONFIDENCE)
KINDS = {**{f: "counter" for f in COUNTERS}, CONFIDENCE: "gauge"}
NOW_NS = time.time_ns()
HOUR_NS = 3600 * 10**9


# ---------------------------------------------------------------------------
# OTLP/HTTP JSON encoding (opentelemetry-proto JSON mapping)
# ---------------------------------------------------------------------------


def _value(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": v}


def _attrs(d):
    return [{"key": k, "value": _value(v)} for k, v in d.items()]


def record(event_name, attributes, ts_ns):
    """One NthLayer event: event_name, attributes, no body, INFO, Timestamp."""
    rec = {
        "timeUnixNano": str(ts_ns),
        "observedTimeUnixNano": str(NOW_NS),
        "severityNumber": 9,
        "severityText": "INFO",
        "attributes": _attrs(attributes),
    }
    if event_name is not None:
        rec["eventName"] = event_name
    return rec


def payload(by_service):
    """{service.name: [records]} -> ExportLogsServiceRequest JSON."""
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": _attrs({"service.name": svc})},
                "scopeLogs": [{"scope": {"name": "nthlayer"}, "logRecords": recs}],
            }
            for svc, recs in by_service.items()
        ]
    }


# ---------------------------------------------------------------------------
# Fixture events
# ---------------------------------------------------------------------------

# §4.1: nthlayer.decision.type examples `triage`, `refund_approval`;
# nthlayer.decision.value is free (low cardinality) except the reserved
# `escalate` (§6.4). Ids are identifiers: never labels (§4.0, N3).
D1, D2, D3, D4, D5 = (f"bafy-fixture-decision-{i}" for i in range(1, 6))


def decision(did, dtype, value, autonomous, ts_ns, **recommended):
    return record(
        "nthlayer.decision",
        {
            "nthlayer.decision.id": did,
            "nthlayer.decision.type": dtype,
            "nthlayer.decision.value": value,
            "nthlayer.decision.autonomous": autonomous,
            **recommended,
        },
        ts_ns,
    )


def _conf(value):
    return {"nthlayer.decision.confidence": value}


def reversal(did, rtype, actor_type, ts_ns, **recommended):
    # §4.2: type in {human_override, self_reconsideration, automated, appeal};
    # actor_type in {human, service, policy}.
    return record(
        "nthlayer.reversal",
        {
            "nthlayer.reversal.decision_id": did,
            "nthlayer.reversal.type": rtype,
            "nthlayer.reversal.actor_type": actor_type,
            **recommended,
        },
        ts_ns,
    )


def outcome(did, value, source, ts_ns, **recommended):
    # §4.3: value in {correct, incorrect, indeterminate}; source examples
    # incident_resolution, chargeback_feed, human_audit.
    return record(
        "nthlayer.outcome",
        {
            "nthlayer.outcome.decision_id": did,
            "nthlayer.outcome.value": value,
            "nthlayer.outcome.source": source,
            **recommended,
        },
        ts_ns,
    )


BATCH_1 = payload(
    {
        "refund-gate": [
            decision(D1, "refund_approval", "approve", True, NOW_NS,
                     **{**_conf(0.93),
                        "nthlayer.decision.reversible": True,
                        "gen_ai.provider.name": "anthropic"}),
            decision(D2, "refund_approval", "approve", True, NOW_NS + 1),
            # escalate: routed to a human, not autonomous (§6.4).
            decision(D3, "refund_approval", "escalate", False, NOW_NS + 2),
            reversal(D1, "human_override", "human", NOW_NS + 3,
                     **{"nthlayer.reversal.actor": "group:default/refunds",
                        "nthlayer.reversal.new_value": "deny",
                        # Opt-in free text: content, never a label.
                        "nthlayer.reversal.reason": "customer had a prior chargeback"}),
            outcome(D1, "incorrect", "chargeback_feed", NOW_NS + 4,
                    **{"nthlayer.outcome.type": "chargeback",
                       "nthlayer.outcome.severity": "SEV3"}),
            outcome(D3, "correct", "human_audit", NOW_NS + 5),
            # Not counted: another event name carrying the decision's
            # attribute names (the §4.4 grader event names a decision id).
            record("gen_ai.evaluation.result",
                   {"gen_ai.evaluation.name": "opensrm.audit",
                    "gen_ai.evaluation.score.label": "correct",
                    "nthlayer.decision.id": D2,
                    "nthlayer.evaluator.kind": "human",
                    "nthlayer.decision.type": "refund_approval",
                    "nthlayer.decision.value": "approve"},
                   NOW_NS + 6),
            # Not counted: the §4.0 gen_ai.-prefixed form MUST NOT be emitted,
            # and an implementation must not count it as nthlayer.decision.
            record("gen_ai.decision",
                   {"nthlayer.decision.id": D2,
                    "nthlayer.decision.type": "refund_approval",
                    "nthlayer.decision.value": "approve",
                    "nthlayer.decision.autonomous": True},
                   NOW_NS + 7),
            # Not counted: a plain log record (no event name) with the same
            # attributes.
            record(None,
                   {"nthlayer.decision.id": D2,
                    "nthlayer.decision.type": "refund_approval",
                    "nthlayer.decision.value": "approve",
                    "nthlayer.decision.autonomous": True},
                   NOW_NS + 8),
        ],
        "triage-gate": [
            decision(D4, "triage", "page", True, NOW_NS),
            reversal(D4, "self_reconsideration", "service", NOW_NS + 1,
                     **{"nthlayer.reversal.actor": "triage-gate"}),
        ],
    }
)

# A second export, so the counts must accumulate across batches. It carries
# an outcome determined an hour ago and emitted now (T1: a retrospective
# consumer sets Timestamp to when the outcome was determined), which must
# still be counted.
BATCH_2 = payload(
    {
        "refund-gate": [
            decision(D5, "refund_approval", "approve", True, NOW_NS + 10),
            outcome(D2, "correct", "chargeback_feed", NOW_NS - HOUR_NS),
        ],
        "triage-gate": [
            outcome(D4, "indeterminate", "incident_resolution", NOW_NS + 10),
        ],
    }
)

FIXTURE_IDS = {D1, D2, D3, D4, D5}


def _key(labels):
    return frozenset(labels.items())


# §4.5 N3: `service` is metadata.name; each label is the attribute minus the
# `nthlayer.` prefix, dots as underscores. Nothing else.
EXPECTED_AFTER_1 = {
    "nthlayer_decisions_total": {
        _key({"service": "refund-gate", "decision_type": "refund_approval",
              "decision_value": "approve"}): 2,
        _key({"service": "refund-gate", "decision_type": "refund_approval",
              "decision_value": "escalate"}): 1,
        _key({"service": "triage-gate", "decision_type": "triage",
              "decision_value": "page"}): 1,
    },
    "nthlayer_reversals_total": {
        _key({"service": "refund-gate", "reversal_type": "human_override",
              "reversal_actor_type": "human"}): 1,
        _key({"service": "triage-gate", "reversal_type": "self_reconsideration",
              "reversal_actor_type": "service"}): 1,
    },
    "nthlayer_outcomes_total": {
        _key({"service": "refund-gate", "outcome_value": "incorrect",
              "outcome_source": "chargeback_feed"}): 1,
        _key({"service": "refund-gate", "outcome_value": "correct",
              "outcome_source": "human_audit"}): 1,
    },
    # Only D1 carries nthlayer.decision.confidence (Recommended, §4.1); the
    # gauge has the decision counter's labels.
    CONFIDENCE: {
        _key({"service": "refund-gate", "decision_type": "refund_approval",
              "decision_value": "approve"}): 0.93,
    },
}

EXPECTED_AFTER_2 = {
    "nthlayer_decisions_total": {
        **EXPECTED_AFTER_1["nthlayer_decisions_total"],
        _key({"service": "refund-gate", "decision_type": "refund_approval",
              "decision_value": "approve"}): 3,
    },
    "nthlayer_reversals_total": EXPECTED_AFTER_1["nthlayer_reversals_total"],
    "nthlayer_outcomes_total": {
        **EXPECTED_AFTER_1["nthlayer_outcomes_total"],
        _key({"service": "refund-gate", "outcome_value": "correct",
              "outcome_source": "chargeback_feed"}): 1,
        _key({"service": "triage-gate", "outcome_value": "indeterminate",
              "outcome_source": "incident_resolution"}): 1,
    },
    # D5 has no confidence: it is counted above, and leaves D1's gauge value.
    CONFIDENCE: EXPECTED_AFTER_1[CONFIDENCE],
}


# ---------------------------------------------------------------------------
# Prometheus text exposition parsing
# ---------------------------------------------------------------------------


def _parse_labels(s):
    """Parse `a="x",b="y"` (the text format's escapes: \\\\, \\", \\n)."""
    labels, i = {}, 0
    while i < len(s):
        eq = s.index("=", i)
        name = s[i:eq].strip().lstrip(",").strip()
        assert s[eq + 1] == '"', f"unquoted label value in {s!r}"
        j, val = eq + 2, []
        while s[j] != '"':
            if s[j] == "\\":
                val.append({"n": "\n"}.get(s[j + 1], s[j + 1]))
                j += 2
            else:
                val.append(s[j])
                j += 1
        labels[name] = "".join(val)
        i = j + 1
        while i < len(s) and s[i] in ", ":
            i += 1
    return labels


def parse_exposition(text):
    """-> {metric name: {frozenset(labels): value}}, plus TYPE lines."""
    samples, types = {}, {}
    for line in text.splitlines():
        if line.startswith("# TYPE "):
            _, _, name, kind = line.split(" ", 3)
            types[name] = kind
            continue
        if not line or line.startswith("#"):
            continue
        if "{" in line:
            name, rest = line.split("{", 1)
            label_str, value = rest.rsplit("}", 1)
            labels = _parse_labels(label_str)
        else:
            name, value = line.split(" ", 1)
            labels = {}
        samples.setdefault(name, {})[_key(labels)] = float(value.split()[0])
    return samples, types


# ---------------------------------------------------------------------------
# Collector lifecycle
# ---------------------------------------------------------------------------


def pinned_image():
    image = yaml.safe_load(COMPOSE.read_text())["services"]["otel-collector"]["image"]
    tag = image.rpartition(":")[2]
    # An exact version: digits and dots, never `latest` or a floating major.
    assert tag.count(".") == 2 and tag.replace(".", "").isdigit(), image
    return image


def _docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def _host_port(container, port):
    out = _docker("port", container, f"{port}/tcp").stdout.strip().splitlines()[0]
    return int(out.rpartition(":")[2])


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode()


@pytest.fixture(scope="module")
def collector():
    if shutil.which("docker") is None:
        pytest.fail("needs docker: `docker` is not on PATH")
    info = _docker("info", check=False)
    if info.returncode != 0:
        pytest.fail(f"needs docker: `docker info` failed:\n{info.stderr.strip()}")

    image = pinned_image()
    # A network of its own, so the Prometheus below scrapes the collector by
    # container name.
    suffix = uuid.uuid4().hex[:12]
    network, name = f"otel-test-{suffix}", f"otel-test-collector-{suffix}"
    net = _docker("network", "create", network, check=False)
    if net.returncode != 0:
        pytest.fail(f"could not create a docker network:\n{net.stderr.strip()}")
    run = _docker(
        "run", "-d", "--rm", "--name", name, "--network", network,
        "-v", f"{CONFIG}:/etc/otelcol-contrib/config.yaml:ro",
        "-p", "127.0.0.1::4317", "-p", "127.0.0.1::4318", "-p", "127.0.0.1::8889",
        image, "--config=/etc/otelcol-contrib/config.yaml",
        check=False,
    )
    if run.returncode != 0:
        _docker("network", "rm", network, check=False)
        pytest.fail(f"could not start {image}:\n{run.stderr.strip()}")
    container = run.stdout.strip()
    try:
        metrics_url = f"http://127.0.0.1:{_host_port(container, 8889)}/metrics"
        logs_url = f"http://127.0.0.1:{_host_port(container, 4318)}/v1/logs"
        grpc_url = f"http://127.0.0.1:{_host_port(container, 4317)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                _get(metrics_url)
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if time.monotonic() > deadline:
                    logs = _docker("logs", container, check=False)
                    pytest.fail(f"collector exporter not up in 60s:\n{logs.stderr}{logs.stdout}")
                time.sleep(0.5)
        yield {"container": container, "metrics": metrics_url, "logs": logs_url,
               "grpc": grpc_url, "network": network, "name": name}
    finally:
        _docker("rm", "-f", container, check=False)
        _docker("network", "rm", network, check=False)


def send(collector, body):
    req = urllib.request.Request(
        collector["logs"], data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        reply = json.loads(resp.read() or b"{}")
    # A partial success means the receiver rejected records.
    assert not reply.get("partialSuccess", {}).get("rejectedLogRecords"), reply


def wait_for(collector, expected, timeout=30):
    """Poll the exporter until the four families match; return the last scrape."""
    deadline = time.monotonic() + timeout
    while True:
        text = _get(collector["metrics"])
        samples, types = parse_exposition(text)
        got = {f: samples.get(f, {}) for f in FAMILIES}
        if got == expected or time.monotonic() > deadline:
            return text, samples, types, got
        time.sleep(0.5)


def _show(fam):
    return {tuple(sorted(k)): v for k, v in fam.items()}


def check_scrape(collector, expected):
    text, samples, types, got = wait_for(collector, expected)
    for family in FAMILIES:
        assert _show(got[family]) == _show(expected[family]), (
            f"{family}: got {_show(got[family])}\nexporter output:\n{text}"
        )
        assert types.get(family) == KINDS[family], (family, types.get(family))
    # No other nthlayer_ series, and no label anywhere carries an id, the
    # free-text reason, or an actor ref (none of them is low cardinality).
    extra = sorted(n for n in samples if n.startswith("nthlayer_") and n not in FAMILIES)
    assert not extra, f"unexpected nthlayer_ series {extra}:\n{text}"
    forbidden = FIXTURE_IDS | {
        "customer had a prior chargeback", "group:default/refunds", "SEV3", "chargeback",
    }
    for name, fam in samples.items():
        for key in fam:
            for label, value in key:
                assert value not in forbidden, (name, label, value)
                assert "id" not in label.split("_"), (name, label)
    return text


def test_counts_labels_and_exclusions(collector):
    send(collector, BATCH_1)
    check_scrape(collector, EXPECTED_AFTER_1)


def test_counts_accumulate_across_batches(collector):
    # Runs after the first test in the same module (pytest keeps file order).
    send(collector, BATCH_2)
    text = check_scrape(collector, EXPECTED_AFTER_2)
    print("\n".join(line for line in text.splitlines() if line.startswith("nthlayer_")))


# The tests below each use their own service, so they add series without
# touching the ones the two tests above compare exactly; they run after them.


def wait_for_series(collector, family, labels, value, timeout=30):
    """Poll until family{labels} == value; return the last scrape's family."""
    deadline = time.monotonic() + timeout
    while True:
        text = _get(collector["metrics"])
        fam = parse_exposition(text)[0].get(family, {})
        if fam.get(_key(labels)) == value or time.monotonic() > deadline:
            return fam, text
        time.sleep(0.5)


def _of_service(fam, service):
    return {k: v for k, v in _show(fam).items() if ("service", service) in k}


CONCURRENT_EXPORTS = 500


def test_concurrent_exports_to_one_series_are_all_counted(collector):
    # Many exporters (or one exporter's parallel exports) hitting one series
    # at once: every decision is counted, exactly (§4.6 divides by it).
    svc = "concurrent-gate"
    bodies = [
        payload({svc: [decision(f"bafy-fixture-concurrent-{i}", "triage", "page",
                                True, NOW_NS + i)]})
        for i in range(CONCURRENT_EXPORTS)
    ]
    with ThreadPoolExecutor(max_workers=50) as pool:
        list(pool.map(lambda b: send(collector, b), bodies))
    labels = {"service": svc, "decision_type": "triage", "decision_value": "page"}
    fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels,
                                CONCURRENT_EXPORTS)
    # Give a late or lost delta time to show: the value must stay exact.
    time.sleep(2)
    fam = parse_exposition(_get(collector["metrics"]))[0]["nthlayer_decisions_total"]
    assert _of_service(fam, svc) == {tuple(sorted(_key(labels))): CONCURRENT_EXPORTS}, (
        f"got {_of_service(fam, svc)}"
    )


# Each of the six counted attributes is Required (§4.1-§4.3 Req. column):
# nthlayer.decision.type and .value, nthlayer.reversal.type and .actor_type,
# nthlayer.outcome.value and .source. One event lacks each, its other counted
# attribute present, so each `unknown` is that attribute's own default.
MISSING_REQUIRED = [
    # (event name, attributes sent, family, expected labels besides service)
    ("nthlayer.decision",
     {"nthlayer.decision.id": "bafy-fixture-malformed-1",
      "nthlayer.decision.value": "approve", "nthlayer.decision.autonomous": True},
     "nthlayer_decisions_total", {"decision_type": "unknown", "decision_value": "approve"}),
    ("nthlayer.decision",
     {"nthlayer.decision.id": "bafy-fixture-malformed-2",
      "nthlayer.decision.type": "triage", "nthlayer.decision.autonomous": True},
     "nthlayer_decisions_total", {"decision_type": "triage", "decision_value": "unknown"}),
    ("nthlayer.reversal",
     {"nthlayer.reversal.decision_id": "bafy-fixture-malformed-1",
      "nthlayer.reversal.actor_type": "human"},
     "nthlayer_reversals_total", {"reversal_type": "unknown", "reversal_actor_type": "human"}),
    ("nthlayer.reversal",
     {"nthlayer.reversal.decision_id": "bafy-fixture-malformed-2",
      "nthlayer.reversal.type": "human_override"},
     "nthlayer_reversals_total",
     {"reversal_type": "human_override", "reversal_actor_type": "unknown"}),
    ("nthlayer.outcome",
     {"nthlayer.outcome.decision_id": "bafy-fixture-malformed-1",
      "nthlayer.outcome.source": "human_audit"},
     "nthlayer_outcomes_total", {"outcome_value": "unknown", "outcome_source": "human_audit"}),
    ("nthlayer.outcome",
     {"nthlayer.outcome.decision_id": "bafy-fixture-malformed-2",
      "nthlayer.outcome.value": "correct"},
     "nthlayer_outcomes_total", {"outcome_value": "correct", "outcome_source": "unknown"}),
]


def test_missing_required_attribute_is_counted_as_unknown(collector):
    # An event lacking a Required attribute is still an event, and dropping it
    # would undercount the §4.6 denominator. It is counted with the label
    # value `unknown`.
    svc = "malformed-gate"
    send(collector, payload({svc: [
        record(name, attrs, NOW_NS + i) for i, (name, attrs, _, _) in enumerate(MISSING_REQUIRED)
    ]}))
    expected = {}
    for _, _, family, labels in MISSING_REQUIRED:
        expected.setdefault(family, {})[tuple(sorted({"service": svc, **labels}.items()))] = 1
    for family, series in expected.items():
        for key in series:
            fam, text = wait_for_series(collector, family, dict(key), 1)
        assert _of_service(fam, svc) == series, (
            f"{family}: got {_of_service(fam, svc)}\nexporter output:\n{text}"
        )


def test_resource_without_service_name_is_counted_as_unknown(collector):
    # N3's `service` comes from the resource service.name; an emitter that
    # sets none still has its events counted, under service="unknown".
    body = {"resourceLogs": [{
        "resource": {"attributes": []},
        "scopeLogs": [{"scope": {"name": "nthlayer"}, "logRecords": [
            decision("bafy-fixture-anonymous-1", "triage", "page", True, NOW_NS,
                     **_conf(0.61)),
        ]}],
    }]}
    send(collector, body)
    labels = {"service": "unknown", "decision_type": "triage", "decision_value": "page"}
    fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels, 1)
    assert _of_service(fam, "unknown") == {tuple(sorted(labels.items())): 1}, text
    # Nothing counted without a service label.
    assert all(any(k == "service" for k, _ in key) for key in fam), text
    # The gauge takes `service` the same way.
    gauge, text = wait_for_series(collector, CONFIDENCE, labels, 0.61)
    assert _of_service(gauge, "unknown") == {tuple(sorted(labels.items())): 0.61}, text
    assert all(any(k == "service" for k, _ in key) for key in gauge), text


def test_service_label_comes_from_the_resource(collector):
    # N3: `service` is the manifest's metadata.name, carried as the emitter's
    # RESOURCE service.name. A record attribute of the same name must not
    # replace it.
    svc = "resource-gate"
    send(collector, payload({svc: [
        decision("bafy-fixture-spoof-1", "triage", "page", True, NOW_NS,
                 **{"service.name": "spoofed-gate", **_conf(0.42)}),
    ]}))
    labels = {"service": svc, "decision_type": "triage", "decision_value": "page"}
    fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels, 1)
    assert _of_service(fam, svc) == {tuple(sorted(_key(labels))): 1}, text
    assert not _of_service(fam, "spoofed-gate"), text
    gauge, text = wait_for_series(collector, CONFIDENCE, labels, 0.42)
    assert _of_service(gauge, svc) == {tuple(sorted(_key(labels))): 0.42}, text
    assert not _of_service(gauge, "spoofed-gate"), text


# ---------------------------------------------------------------------------
# nthlayer_decision_confidence (A1 §4.5 gauge of §4.1's
# nthlayer.decision.confidence: double, Recommended, a ratio 0.0-1.0)
# [opensrm-taz2]
# ---------------------------------------------------------------------------


def _raw_conf(rec, otlp_value):
    """Add a confidence with an explicit OTLP AnyValue (a JSON-only form)."""
    rec["attributes"].append({"key": "nthlayer.decision.confidence", "value": otlp_value})
    return rec


def test_confidence_gauge_series_labels_and_value(collector):
    # One series per (service, decision_type, decision_value), the labels of
    # nthlayer_decisions_total (N3), valued at the decision's confidence. A
    # decision lacking the Required nthlayer.decision.type or
    # nthlayer.decision.value is `unknown` there, as in the counter.
    svc = "confidence-gate"
    send(collector, payload({svc: [
        decision("bafy-fixture-conf-1", "refund_approval", "approve", True, NOW_NS,
                 **_conf(0.93)),
        decision("bafy-fixture-conf-2", "refund_approval", "deny", True, NOW_NS + 1,
                 **_conf(0.25)),
        decision("bafy-fixture-conf-3", "triage", "escalate", False, NOW_NS + 2,
                 **_conf(0.5)),
        record("nthlayer.decision",
               {"nthlayer.decision.id": "bafy-fixture-conf-4",
                "nthlayer.decision.value": "page", "nthlayer.decision.autonomous": True,
                **_conf(0.8)},
               NOW_NS + 3),
        record("nthlayer.decision",
               {"nthlayer.decision.id": "bafy-fixture-conf-7",
                "nthlayer.decision.type": "triage", "nthlayer.decision.autonomous": True,
                **_conf(0.77)},
               NOW_NS + 6),
        # Not a decision: the same attributes on other event names give no point.
        record("gen_ai.decision",
               {"nthlayer.decision.id": "bafy-fixture-conf-5",
                "nthlayer.decision.type": "refund_approval",
                "nthlayer.decision.value": "approve", **_conf(0.11)},
               NOW_NS + 4),
        record(None,
               {"nthlayer.decision.id": "bafy-fixture-conf-6",
                "nthlayer.decision.type": "refund_approval",
                "nthlayer.decision.value": "approve", **_conf(0.12)},
               NOW_NS + 5),
    ]}))
    expected = {
        (("decision_type", "refund_approval"), ("decision_value", "approve")): 0.93,
        (("decision_type", "refund_approval"), ("decision_value", "deny")): 0.25,
        (("decision_type", "triage"), ("decision_value", "escalate")): 0.5,
        (("decision_type", "unknown"), ("decision_value", "page")): 0.8,
        (("decision_type", "triage"), ("decision_value", "unknown")): 0.77,
    }
    expected = {tuple(sorted({"service": svc, **dict(k)}.items())): v
                for k, v in expected.items()}
    for key, value in expected.items():
        fam, text = wait_for_series(collector, CONFIDENCE, dict(key), value)
    assert _of_service(fam, svc) == expected, f"got {_of_service(fam, svc)}\n{text}"


def test_confidence_gauge_exported_name_and_type(collector):
    # §4.5: exactly nthlayer_decision_confidence, a gauge. N2: a ratio has no
    # unit suffix (no _ratio), and a gauge has no _total.
    svc = "confidence-name-gate"
    send(collector, payload({svc: [
        decision("bafy-fixture-conf-name-1", "triage", "page", True, NOW_NS, **_conf(0.3)),
    ]}))
    labels = {"service": svc, "decision_type": "triage", "decision_value": "page"}
    _, text = wait_for_series(collector, CONFIDENCE, labels, 0.3)
    for accept in (None, "text/plain;version=1.0.0;escaping=allow-utf-8"):
        text = _get(collector["metrics"], headers={"Accept": accept} if accept else None)
        samples, types = parse_exposition(text)
        assert types.get(CONFIDENCE) == "gauge", (types, text)
        assert _key(labels) in samples.get(CONFIDENCE, {}), text
        assert not [n for n in {*samples, *types}
                    if "confidence" in n and n != CONFIDENCE], text


def test_decision_without_confidence_gives_no_point_but_is_counted(collector):
    # nthlayer.decision.confidence is Recommended: its absence is a valid
    # decision, counted, with no gauge point.
    svc = "no-confidence-gate"
    send(collector, payload({svc: [
        decision("bafy-fixture-noconf-1", "triage", "page", True, NOW_NS),
        decision("bafy-fixture-noconf-2", "triage", "page", True, NOW_NS + 1),
        # A control in the same export, so the gauge's absence below is not
        # just a gauge that has not arrived yet.
        decision("bafy-fixture-noconf-3", "triage", "ack", True, NOW_NS + 2, **_conf(0.6)),
    ]}))
    labels = {"service": svc, "decision_type": "triage", "decision_value": "page"}
    control = {**labels, "decision_value": "ack"}
    fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels, 2)
    assert fam.get(_key(labels)) == 2, text
    gauge, text = wait_for_series(collector, CONFIDENCE, control, 0.6)
    assert _of_service(gauge, svc) == {tuple(sorted(control.items())): 0.6}, text


# §4.1: a double, a ratio 0.0-1.0. Values that are not (each under its own
# decision_type, so each would be its own series) and the two bounds, which are.
NONCONFORMING_CONFIDENCE = [
    # (decision_type, OTLP AnyValue)
    ("string", {"stringValue": "0.9"}),  # a string, even a numeric one
    ("int", {"intValue": "1"}),          # an int, not a double
    ("bool", {"boolValue": True}),
    ("above", {"doubleValue": 1.5}),
    ("below", {"doubleValue": -0.1}),
    ("nan", {"doubleValue": "NaN"}),
    ("inf", {"doubleValue": "Infinity"}),
]
BOUNDARY_CONFIDENCE = [("zero", 0.0), ("one", 1.0)]


def test_nonconforming_confidence_gives_no_point_but_is_counted(collector):
    svc = "bad-confidence-gate"
    recs = [_raw_conf(decision(f"bafy-fixture-badconf-{dtype}", dtype, "approve", True,
                               NOW_NS + i), value)
            for i, (dtype, value) in enumerate(NONCONFORMING_CONFIDENCE)]
    recs += [decision(f"bafy-fixture-edgeconf-{dtype}", dtype, "approve", True,
                      NOW_NS + 100 + i, **_conf(value))
             for i, (dtype, value) in enumerate(BOUNDARY_CONFIDENCE)]
    send(collector, payload({svc: recs}))
    # Every decision is counted, whatever its confidence.
    for dtype, _ in [*NONCONFORMING_CONFIDENCE, *BOUNDARY_CONFIDENCE]:
        labels = {"service": svc, "decision_type": dtype, "decision_value": "approve"}
        fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels, 1)
        assert fam.get(_key(labels)) == 1, (dtype, text)
    # Only the bounds give points, at their own value: never a clamp or a
    # conversion of the others.
    expected = {}
    for dtype, value in BOUNDARY_CONFIDENCE:
        labels = {"service": svc, "decision_type": dtype, "decision_value": "approve"}
        gauge, text = wait_for_series(collector, CONFIDENCE, labels, value)
        expected[tuple(sorted(labels.items()))] = value
    assert _of_service(gauge, svc) == expected, f"got {_of_service(gauge, svc)}\n{text}"


def test_confidence_gauge_keeps_the_last_value(collector):
    # A gauge is a last value. Within one export, the last decision of a
    # series in record order, even if its Timestamp is earlier (an event's own
    # time, T1, is not its arrival); across exports, the later export.
    svc = "last-confidence-gate"
    labels = {"service": svc, "decision_type": "triage", "decision_value": "page"}

    def dec(i, ts_ns, **conf):
        return decision(f"bafy-fixture-lastconf-{i}", "triage", "page", True, ts_ns, **conf)

    send(collector, payload({svc: [dec(1, NOW_NS, **_conf(0.4)),
                                   dec(2, NOW_NS - HOUR_NS, **_conf(0.7))]}))
    gauge, text = wait_for_series(collector, CONFIDENCE, labels, 0.7)
    assert _of_service(gauge, svc) == {tuple(sorted(labels.items())): 0.7}, text

    send(collector, payload({svc: [dec(3, NOW_NS + 1, **_conf(0.2))]}))
    gauge, text = wait_for_series(collector, CONFIDENCE, labels, 0.2)
    assert _of_service(gauge, svc) == {tuple(sorted(labels.items())): 0.2}, text

    # A later decision without a conforming confidence leaves the value.
    send(collector, payload({svc: [dec(4, NOW_NS + 2),
                                   _raw_conf(dec(5, NOW_NS + 3), {"doubleValue": 1.5})]}))
    fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels, 5)
    assert fam.get(_key(labels)) == 5, text
    # The counter and the gauge leave the connectors one after the other;
    # give a (wrong) gauge update time to land before reading it.
    time.sleep(2)
    text = _get(collector["metrics"])
    gauge = parse_exposition(text)[0].get(CONFIDENCE, {})
    assert _of_service(gauge, svc) == {tuple(sorted(labels.items())): 0.2}, text


def test_confidence_gauge_last_value_spans_instances_of_one_service(collector):
    # Two replicas of one service (OTel resource semconv: one service.name,
    # each its own service.instance.id) land in one batch, since the batch
    # processor merges exports. `service` is the service.name alone (N3), so
    # they share a series, and its value is the last decision in record
    # order: instance A, then B, then A again gives A's second value, not
    # whichever resource appeared first.
    svc = "replicated-confidence-gate"
    labels = {"service": svc, "decision_type": "triage", "decision_value": "page"}

    def resource_logs(instance, i, conf):
        return {
            "resource": {"attributes": _attrs({"service.name": svc,
                                               "service.instance.id": instance})},
            "scopeLogs": [{"scope": {"name": "nthlayer"}, "logRecords": [
                decision(f"bafy-fixture-replica-{i}", "triage", "page", True,
                         NOW_NS + i, **_conf(conf)),
            ]}],
        }

    send(collector, {"resourceLogs": [resource_logs("replica-a", 1, 0.4),
                                      resource_logs("replica-b", 2, 0.7),
                                      resource_logs("replica-a", 3, 0.9)]})
    fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels, 3)
    assert _of_service(fam, svc) == {tuple(sorted(labels.items())): 3}, text
    gauge, text = wait_for_series(collector, CONFIDENCE, labels, 0.9)
    assert _of_service(gauge, svc) == {tuple(sorted(labels.items())): 0.9}, text


def test_pinned_image_is_exact():
    assert pinned_image().startswith("otel/opentelemetry-collector-contrib:")


def test_exporter_escapes_names_for_a_utf8_scraper(collector):
    # translation_strategy UnderscoreEscapingWithSuffixes: the names are the
    # §4.5 underscore names even for a scraper that accepts UTF-8 names (the
    # pinned Prometheus v2.51 does not offer that, so it cannot pin this).
    svc = "escaping-gate"
    send(collector, payload({svc: [
        decision("bafy-fixture-escaping-1", "triage", "page", True, NOW_NS,
                 **_conf(0.5)),
        reversal("bafy-fixture-escaping-1", "human_override", "human", NOW_NS + 1),
        outcome("bafy-fixture-escaping-1", "correct", "human_audit", NOW_NS + 2),
    ]}))
    wait_for_series(collector, "nthlayer_outcomes_total",
                    {"service": svc, "outcome_value": "correct",
                     "outcome_source": "human_audit"}, 1)
    text = _get(collector["metrics"], headers={
        "Accept": "text/plain;version=1.0.0;escaping=allow-utf-8"})
    _, types = parse_exposition(text)
    for family in FAMILIES:
        assert types.get(family) == KINDS[family], (family, text)
    samples = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert not [ln for ln in samples if ln.startswith("{") or "nthlayer." in ln], text


# ---------------------------------------------------------------------------
# test/fake-service.py as an ai-gate, against the collector
# ---------------------------------------------------------------------------

FAKE_SERVICE = TEST_DIR / "fake-service.py"
FAKE_NAME = "fraud-detect"  # demo/specs/fraud-detect.yaml's metadata.name
# The published package, as CI installs it (no sibling checkout). The floor
# is the release this was verified against: emit_event(timestamp=) and
# init_telemetry's TelemetryStatus.
NTHLAYER_COMMON = os.environ.get("NTHLAYER_COMMON_OTEL", "nthlayer-common[otel]>=5.12")
# §4.2 and §4.3 enumerations.
REVERSAL_TYPES = {"human_override", "self_reconsideration", "automated", "appeal"}
ACTOR_TYPES = {"human", "service", "policy"}
OUTCOME_VALUES = {"correct", "incorrect", "indeterminate"}
# fake-service ramps a /control change over RAMP_STEPS * RAMP_INTERVAL (15s).
RAMP_SETTLE_S = 20
WINDOW_S = 15


def _fake_constant(name):
    """A module-level string constant of fake-service.py (its own vocabulary)."""
    for node in ast.parse(FAKE_SERVICE.read_text()).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {FAKE_SERVICE}")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200


@pytest.fixture(scope="module")
def fake_gate(collector, tmp_path_factory):
    """fake-service.py --type ai-gate exporting to the collector, reversal_rate 1.0.

    Yields after the ramp has settled, so every non-escalate decision from
    then on is reversed.
    """
    if shutil.which("uv") is None:
        pytest.fail("needs uv: `uv` is not on PATH")
    port = _free_port()
    log = tmp_path_factory.mktemp("fake-service") / "fake-service.log"
    with open(log, "w") as out:
        proc = subprocess.Popen(
            ["uv", "run", "--isolated", "--no-project", "--python", sys.executable,
             "--with", NTHLAYER_COMMON, "--with", "prometheus-client",
             "python", str(FAKE_SERVICE), "--name", FAKE_NAME, "--type", "ai-gate",
             "--port", str(port), "--rps", "100", "--outcome-delay", "1",
             "--otlp-endpoint", collector["grpc"]],
            stdout=out, stderr=subprocess.STDOUT,
        )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 300  # first run installs the otel SDK
        while True:
            if proc.poll() is not None:
                pytest.fail(f"fake-service exited {proc.returncode}:\n{log.read_text()}")
            try:
                _get(f"{base}/health")
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if time.monotonic() > deadline:
                    pytest.fail(f"fake-service not up in 300s:\n{log.read_text()}")
                time.sleep(0.5)
        _post(f"{base}/control", {"reversal_rate": 1.0})
        time.sleep(RAMP_SETTLE_S)
        yield {"url": base, "log": log}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


def _service_samples(collector, service):
    text = _get(collector["metrics"])
    samples = parse_exposition(text)[0]
    return {f: {k: v for k, v in samples.get(f, {}).items() if ("service", service) in k}
            for f in FAMILIES}, text


def _total(fam, pred=lambda labels: True):
    return sum(v for k, v in fam.items() if pred(dict(k)))


def test_fake_service_events_are_counted_with_n3_labels(collector, fake_gate):
    decision_type = _fake_constant("DECISION_TYPE")
    outcome_source = _fake_constant("OUTCOME_SOURCE")
    deadline = time.monotonic() + 60
    while True:
        got, text = _service_samples(collector, FAKE_NAME)
        if all(got.values()) or time.monotonic() > deadline:
            break
        time.sleep(0.5)
    for family, label_names in (
        ("nthlayer_decisions_total", {"service", "decision_type", "decision_value"}),
        ("nthlayer_reversals_total", {"service", "reversal_type", "reversal_actor_type"}),
        ("nthlayer_outcomes_total", {"service", "outcome_value", "outcome_source"}),
        (CONFIDENCE, {"service", "decision_type", "decision_value"}),
    ):
        assert got[family], f"no {family} for {FAKE_NAME}:\n{text}"
        for key in got[family]:
            assert {k for k, _ in key} == label_names, (family, key)
    for key in got["nthlayer_decisions_total"]:
        labels = dict(key)
        assert labels["decision_type"] == decision_type, labels
        assert labels["decision_value"] != "unknown", labels
    assert any(dict(k)["decision_value"] == "escalate" for k in got["nthlayer_decisions_total"])
    # fake-service sets nthlayer.decision.confidence on every decision, so
    # through the published emitter (OTLP/gRPC) each decision series has a
    # gauge, a ratio 0.0-1.0 (§4.1). Scraped once, both come from the same
    # batches; wait until every decision series has shown its gauge.
    while (set(got[CONFIDENCE]) != set(got["nthlayer_decisions_total"])
           and time.monotonic() <= deadline):
        time.sleep(0.5)
        got, text = _service_samples(collector, FAKE_NAME)
    assert set(got[CONFIDENCE]) == set(got["nthlayer_decisions_total"]), text
    for key, value in got[CONFIDENCE].items():
        assert 0.0 <= value <= 1.0, (dict(key), value)
    for key in got["nthlayer_reversals_total"]:
        labels = dict(key)
        assert labels["reversal_type"] in REVERSAL_TYPES, labels
        assert labels["reversal_actor_type"] in ACTOR_TYPES, labels
    for key in got["nthlayer_outcomes_total"]:
        labels = dict(key)
        assert labels["outcome_value"] in OUTCOME_VALUES, labels
        assert labels["outcome_source"] == outcome_source, labels


def test_fake_service_never_reverses_an_escalation(collector, fake_gate):
    # §6.4: escalate routes the decision to a human; there is no option to
    # overturn. At reversal_rate 1.0 every other decision is reversed, so over
    # a window the reversals equal the non-escalate decisions, and would
    # exceed them by the escalations if escalations were reversed too.
    def counts():
        got, _ = _service_samples(collector, FAKE_NAME)
        dec = got["nthlayer_decisions_total"]
        return (_total(got["nthlayer_reversals_total"]),
                _total(dec, lambda lb: lb["decision_value"] != "escalate"),
                _total(dec, lambda lb: lb["decision_value"] == "escalate"))

    rev0, auto0, esc0 = counts()
    time.sleep(WINDOW_S)
    rev1, auto1, esc1 = counts()
    d_rev, d_auto, d_esc = rev1 - rev0, auto1 - auto0, esc1 - esc0
    print(f"window: reversals {d_rev}, non-escalate {d_auto}, escalate {d_esc}")
    # Enough escalations that reversing them would show (~5% of ~1000+).
    assert d_esc >= 20, (d_rev, d_auto, d_esc)
    # A decision and its reversal are emitted back to back; at most a few
    # straddle an export boundary at either end of the window.
    assert abs(d_rev - d_auto) <= 5, (d_rev, d_auto, d_esc)


def test_fake_service_exports_the_bridge_counters(fake_gate):
    # Ruling R1a (until opensrm-vgub): nthlayer-workers' measure worker reads
    # these from the fake service's own /metrics.
    samples = parse_exposition(_get(f"{fake_gate['url']}/metrics"))[0]
    for name in ("gen_ai_decisions_total", "gen_ai_overrides_total",
                 "gen_ai_overrides_hcf_total"):
        fam = samples.get(name, {})
        assert any(("service", FAKE_NAME) in k and v > 0 for k, v in fam.items()), (name, fam)
    actions = {dict(k).get("action") for k in samples["gen_ai_decisions_total"]}
    assert {"approve", "reject", "escalate"} <= actions, actions


# ---------------------------------------------------------------------------
# Prometheus over the collector: the demo's nthlayer_* queries
# ---------------------------------------------------------------------------

FRAUD_SPEC = TEST_DIR.parent / "demo" / "specs" / "fraud-detect.yaml"
DEMO_RULES = TEST_DIR / "rules" / "demo-alerts.yml"
ACCURACY_DASHBOARD = TEST_DIR / "grafana" / "dashboards" / "nthlayer-verdict-accuracy.json"


def pinned_prometheus():
    image = yaml.safe_load(COMPOSE.read_text())["services"]["prometheus"]["image"]
    tag = image.rpartition(":")[2]
    assert tag.startswith("v") and tag[1:].count(".") == 2 and tag[1:].replace(".", "").isdigit(), image
    return image


@pytest.fixture(scope="module")
def prometheus(collector, fake_gate, tmp_path_factory):
    cfg = tmp_path_factory.mktemp("prometheus") / "prometheus.yml"
    cfg.write_text(yaml.safe_dump({
        "global": {"scrape_interval": "1s", "evaluation_interval": "1s"},
        "scrape_configs": [{"job_name": "otel-collector",
                            "static_configs": [{"targets": [f"{collector['name']}:8889"]}]}],
    }))
    cfg.chmod(0o644)  # read by the image's `nobody`
    image = pinned_prometheus()
    run = _docker(
        "run", "-d", "--rm", "--network", collector["network"],
        "-v", f"{cfg}:/etc/prometheus/prometheus.yml:ro", "-p", "127.0.0.1::9090",
        image, "--config.file=/etc/prometheus/prometheus.yml",
        "--storage.tsdb.path=/prometheus",
        check=False,
    )
    if run.returncode != 0:
        pytest.fail(f"could not start {image}:\n{run.stderr.strip()}")
    container = run.stdout.strip()
    try:
        base = f"http://127.0.0.1:{_host_port(container, 9090)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                _get(f"{base}/-/ready")
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if time.monotonic() > deadline:
                    logs = _docker("logs", container, check=False)
                    pytest.fail(f"prometheus not ready in 60s:\n{logs.stderr}{logs.stdout}")
                time.sleep(0.5)
        yield base
    finally:
        _docker("rm", "-f", container, check=False)


def promql(base, expr, until, timeout=90):
    """Poll an instant query until `until(result)`; return the last result."""
    deadline = time.monotonic() + timeout
    while True:
        url = f"{base}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
        body = json.loads(_get(url))
        assert body["status"] == "success", body
        result = body["data"]["result"]
        if until(result) or time.monotonic() > deadline:
            return result
        time.sleep(1)


def test_fraud_detect_reversal_sli_query_reads_the_collector(prometheus):
    spec = yaml.safe_load(FRAUD_SPEC.read_text())
    expr = spec["spec"]["slos"]["reversal_rate"]["indicator"]["query"]
    assert "nthlayer_reversals_total" in expr and "nthlayer_decisions_total" in expr, expr
    # 1 - reversals/decisions; the fake gate reverses every non-escalate
    # decision once the ramp settles, so the SLI is well below 1 but >= 0.
    result = promql(prometheus, expr, lambda r: bool(r) and float(r[0]["value"][1]) < 0.9)
    assert len(result) == 1, result
    value = float(result[0]["value"][1])
    assert 0.0 <= value < 0.9, result


def test_demo_nthlayer_alert_expressions_read_the_collector(prometheus):
    rules = [r for g in yaml.safe_load(DEMO_RULES.read_text())["groups"]
             for r in g["rules"] if "nthlayer_" in r["expr"]]
    assert rules, f"no nthlayer_* rule in {DEMO_RULES}"
    for rule in rules:
        expr = rule["expr"]
        result = promql(prometheus, expr, lambda r: any(
            s["metric"].get("service") == FAKE_NAME for s in r))
        mine = [s for s in result if s["metric"].get("service") == FAKE_NAME]
        assert len(mine) == 1, (rule.get("alert"), result)
        assert 0.0 < float(mine[0]["value"][1]) <= 1.0, (rule.get("alert"), mine)


def _dashboard_exprs(path):
    """Every target expression in a Grafana dashboard, collapsed rows included."""
    def panels(items):
        for p in items:
            yield p
            yield from panels(p.get("panels", []))
    return [t["expr"] for p in panels(json.loads(path.read_text())["panels"])
            for t in p.get("targets", []) if "expr" in t]


def test_verdict_accuracy_dashboard_reversal_panel_reads_the_collector(prometheus):
    """The reversal-rate panel reads A1's nthlayer_reversals_total over
    nthlayer_decisions_total, the only quantity named reversal rate (opensrm-5lxs);
    respond's nthlayer_verdict_reversal_rate gauge is retired (opensrm-l0ki), and a
    panel on a removed series is an empty panel, not an error (opensrm-sz3a)."""
    exprs = _dashboard_exprs(ACCURACY_DASHBOARD)
    assert not [e for e in exprs if "nthlayer_verdict_reversal_rate" in e], exprs
    reversal = [e for e in exprs if "nthlayer_reversals_total" in e]
    assert len(reversal) == 1, exprs
    expr = reversal[0]
    assert "nthlayer_decisions_total" in expr, expr
    result = promql(prometheus, expr, lambda r: any(
        s["metric"].get("service") == FAKE_NAME for s in r))
    mine = [s for s in result if s["metric"].get("service") == FAKE_NAME]
    assert len(mine) == 1, result
    # The fake gate reverses decisions once the ramp settles: a real rate, not 0.
    assert 0.0 < float(mine[0]["value"][1]) <= 1.0, mine
    # Pin the value, not just its range: the panel minus A1's ratio, written here
    # from the §4.5 names and evaluated in the same query (one instant), is 0.
    reference = ("sum by (service) (increase(nthlayer_reversals_total[7d]))"
                 " / sum by (service) (increase(nthlayer_decisions_total[7d]))")
    diff = promql(prometheus, f"abs(({expr}) - ({reference}))", lambda r: any(
        s["metric"].get("service") == FAKE_NAME for s in r))
    mine = [s for s in diff if s["metric"].get("service") == FAKE_NAME]
    assert len(mine) == 1 and float(mine[0]["value"][1]) < 1e-9, diff


def test_verdict_accuracy_reversal_panel_shows_zero_before_any_reversal(prometheus):
    """The count connector creates nthlayer_reversals_total only when a reversal
    arrives, so a service with decisions and no reversals has no numerator. The
    panel must show it at 0, not drop it: a missing line is the silent empty
    panel opensrm-sz3a exists to prevent. Selecting a reversal_type no event
    carries stands in for that service, against the same real decisions."""
    (expr,) = [e for e in _dashboard_exprs(ACCURACY_DASHBOARD) if "nthlayer_reversals_total" in e]
    assert expr.count("nthlayer_reversals_total[") == 1, expr
    no_reversals = expr.replace(
        "nthlayer_reversals_total[", 'nthlayer_reversals_total{reversal_type="none-emitted"}[')
    result = promql(prometheus, no_reversals, lambda r: any(
        s["metric"].get("service") == FAKE_NAME for s in r))
    mine = [s for s in result if s["metric"].get("service") == FAKE_NAME]
    assert len(mine) == 1, result
    assert float(mine[0]["value"][1]) == 0.0, mine
