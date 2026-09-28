"""Unit tests for the pure pipeline functions."""

from alertrouter.models import Alert
from alertrouter.pipeline import dedup, enrich, fingerprint, route


def make_alert(**labels):
    return Alert(labels=labels)


def test_fingerprint_is_label_order_independent():
    a = Alert(labels={"alertname": "HighErrorRate", "service": "checkout"})
    b = Alert(labels={"service": "checkout", "alertname": "HighErrorRate"})
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_differs_for_different_labels():
    a = Alert(labels={"alertname": "HighErrorRate", "service": "checkout"})
    b = Alert(labels={"alertname": "HighErrorRate", "service": "search"})
    assert fingerprint(a) != fingerprint(b)


def test_dedup_drops_duplicate_fingerprint():
    a = Alert(labels={"alertname": "X", "instance": "i1"})
    dup = Alert(labels={"instance": "i1", "alertname": "X"})  # reordered labels
    b = Alert(labels={"alertname": "Y", "instance": "i1"})

    new_alerts, seen = dedup([a, dup, b], set())

    assert len(new_alerts) == 2
    fps = {fingerprint(x) for x in new_alerts}
    assert fps == {fingerprint(a), fingerprint(b)}
    assert fingerprint(a) in seen and fingerprint(b) in seen


def test_dedup_respects_preexisting_seen_set():
    a = Alert(labels={"alertname": "X", "instance": "i1"})
    new_alerts, seen = dedup([a], {fingerprint(a)})
    assert new_alerts == []
    assert fingerprint(a) in seen


def test_enrich_severity_from_label_wins():
    alert = Alert(labels={"alertname": "HighErrorRate", "severity": "info"})
    out = enrich(alert, {"HighErrorRate": "critical"}, {})
    assert out["severity"] == "info"


def test_enrich_severity_from_map_and_default():
    mapped = enrich(
        Alert(labels={"alertname": "HighErrorRate"}),
        {"HighErrorRate": "critical", "default": "warning"},
        {},
    )
    assert mapped["severity"] == "critical"

    fallback = enrich(
        Alert(labels={"alertname": "SomethingElse"}),
        {"HighErrorRate": "critical", "default": "warning"},
        {},
    )
    assert fallback["severity"] == "warning"


def test_enrich_attaches_runbook_when_alertname_matches():
    runbooks = {"HighErrorRate": "https://rb.example/high-error-rate"}
    matched = enrich(Alert(labels={"alertname": "HighErrorRate"}), {}, runbooks)
    assert matched["runbook"] == "https://rb.example/high-error-rate"

    unmatched = enrich(Alert(labels={"alertname": "Other"}), {}, runbooks)
    assert unmatched["runbook"] is None


def test_enrich_summary_prefers_annotation_then_synthesizes():
    from_annotation = enrich(
        Alert(labels={"alertname": "X"}, annotations={"summary": "boom"}),
        {},
        {},
    )
    assert from_annotation["summary"] == "boom"

    synthesized = enrich(
        Alert(labels={"alertname": "X", "instance": "host-1"}),
        {},
        {},
    )
    assert synthesized["summary"] == "X on host-1"


def test_route_matches_rule_by_severity():
    rules = [
        {"name": "page", "match": {"severity": "critical"}, "destinations": ["pagerduty"]},
        {"name": "default", "match": {}, "destinations": ["slack"]},
    ]
    enriched = enrich(Alert(labels={"alertname": "X", "severity": "critical"}), {}, {})
    assert route(enriched, rules) == ["pagerduty"]


def test_route_matches_rule_by_label():
    rules = [
        {"name": "infra", "match": {"team": "infra"}, "destinations": ["slack"]},
    ]
    enriched = enrich(Alert(labels={"alertname": "X", "team": "infra"}), {}, {})
    assert route(enriched, rules) == ["slack"]


def test_route_falls_back_to_default_when_no_match():
    rules = [
        {"name": "page", "match": {"severity": "critical"}, "destinations": ["pagerduty"]},
        {"name": "default", "match": {}, "destinations": ["slack"]},
    ]
    enriched = enrich(Alert(labels={"alertname": "X", "severity": "warning"}), {}, {})
    assert route(enriched, rules) == ["slack"]


def test_route_deduplicates_destinations_across_rules():
    rules = [
        {"name": "a", "match": {"severity": "critical"}, "destinations": ["slack"]},
        {"name": "b", "match": {"team": "infra"}, "destinations": ["slack", "pagerduty"]},
    ]
    enriched = enrich(
        Alert(labels={"alertname": "X", "severity": "critical", "team": "infra"}),
        {},
        {},
    )
    assert route(enriched, rules) == ["slack", "pagerduty"]
