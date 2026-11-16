"""The OTel Collector config turns A1 §4 log events into the §4.5 counters.

Runs the collector image pinned in test/docker-compose.yml with the committed
test/otel-collector.yaml, sends a fixed set of OTLP log records over
OTLP/HTTP JSON, scrapes the Prometheus exporter and checks every sample of
nthlayer_decisions_total, nthlayer_reversals_total and nthlayer_outcomes_total
[opensrm-s4ui].

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

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

TEST_DIR = Path(__file__).resolve().parent
CONFIG = TEST_DIR / "otel-collector.yaml"
COMPOSE = TEST_DIR / "docker-compose.yml"

FAMILIES = ("nthlayer_decisions_total", "nthlayer_reversals_total", "nthlayer_outcomes_total")
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
                     **{"nthlayer.decision.confidence": 0.93,
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


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.read().decode()


@pytest.fixture(scope="module")
def collector():
    if shutil.which("docker") is None:
        pytest.fail("needs docker: `docker` is not on PATH")
    info = _docker("info", check=False)
    if info.returncode != 0:
        pytest.fail(f"needs docker: `docker info` failed:\n{info.stderr.strip()}")

    image = pinned_image()
    run = _docker(
        "run", "-d", "--rm",
        "-v", f"{CONFIG}:/etc/otelcol-contrib/config.yaml:ro",
        "-p", "127.0.0.1::4318", "-p", "127.0.0.1::8889",
        image, "--config=/etc/otelcol-contrib/config.yaml",
        check=False,
    )
    if run.returncode != 0:
        pytest.fail(f"could not start {image}:\n{run.stderr.strip()}")
    container = run.stdout.strip()
    try:
        metrics_url = f"http://127.0.0.1:{_host_port(container, 8889)}/metrics"
        logs_url = f"http://127.0.0.1:{_host_port(container, 4318)}/v1/logs"
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
        yield {"container": container, "metrics": metrics_url, "logs": logs_url}
    finally:
        _docker("rm", "-f", container, check=False)


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
    """Poll the exporter until the three families match; return the last scrape."""
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
        assert types.get(family) == "counter", (family, types.get(family))
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


def test_missing_required_attribute_is_counted_as_unknown(collector):
    # §4.1-§4.3 mark these attributes Required; an event lacking one is still
    # an event, and dropping it would undercount the §4.6 denominator. It is
    # counted with the label value `unknown`.
    svc = "malformed-gate"
    send(collector, payload({svc: [
        record("nthlayer.decision",
               {"nthlayer.decision.id": "bafy-fixture-malformed-1",
                "nthlayer.decision.value": "approve",
                "nthlayer.decision.autonomous": True}, NOW_NS),
        record("nthlayer.reversal",
               {"nthlayer.reversal.decision_id": "bafy-fixture-malformed-1",
                "nthlayer.reversal.type": "human_override"}, NOW_NS + 1),
        record("nthlayer.outcome",
               {"nthlayer.outcome.decision_id": "bafy-fixture-malformed-1",
                "nthlayer.outcome.source": "human_audit"}, NOW_NS + 2),
    ]}))
    expected = {
        "nthlayer_decisions_total": {"service": svc, "decision_type": "unknown",
                                     "decision_value": "approve"},
        "nthlayer_reversals_total": {"service": svc, "reversal_type": "human_override",
                                     "reversal_actor_type": "unknown"},
        "nthlayer_outcomes_total": {"service": svc, "outcome_value": "unknown",
                                    "outcome_source": "human_audit"},
    }
    for family, labels in expected.items():
        fam, text = wait_for_series(collector, family, labels, 1)
        assert _of_service(fam, svc) == {tuple(sorted(_key(labels))): 1}, (
            f"{family}: got {_of_service(fam, svc)}\nexporter output:\n{text}"
        )


def test_service_label_comes_from_the_resource(collector):
    # N3: `service` is the manifest's metadata.name, carried as the emitter's
    # RESOURCE service.name. A record attribute of the same name must not
    # replace it.
    svc = "resource-gate"
    send(collector, payload({svc: [
        decision("bafy-fixture-spoof-1", "triage", "page", True, NOW_NS,
                 **{"service.name": "spoofed-gate"}),
    ]}))
    labels = {"service": svc, "decision_type": "triage", "decision_value": "page"}
    fam, text = wait_for_series(collector, "nthlayer_decisions_total", labels, 1)
    assert _of_service(fam, svc) == {tuple(sorted(_key(labels))): 1}, text
    assert not _of_service(fam, "spoofed-gate"), text


def test_pinned_image_is_exact():
    assert pinned_image().startswith("otel/opentelemetry-collector-contrib:")
