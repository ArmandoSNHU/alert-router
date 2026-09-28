"""Pure alert-processing functions.

Everything in this module is deterministic and free of I/O so it can be unit
tested without a network, a clock, or a database. The service layer wires these
together and adds the impure bits (sending, shared state).
"""

from __future__ import annotations

import hashlib
from typing import Any

from .models import Alert


def fingerprint(alert: Alert) -> str:
    """Return a stable hash identifying an alert by its labels.

    The hash is built from the label pairs sorted by key, so two alerts with the
    same labels produce the same fingerprint regardless of dict insertion order.
    """
    pairs = sorted(alert.labels.items())
    canonical = "\n".join(f"{key}={value}" for key, value in pairs)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def dedup(
    alerts: list[Alert],
    seen: set[str],
    window: int | None = None,
) -> tuple[list[Alert], set[str]]:
    """Drop alerts whose fingerprint has already been seen.

    Returns the list of previously unseen alerts and an updated ``seen`` set.
    ``window`` is accepted for API symmetry with time-windowed dedup strategies;
    this implementation treats ``seen`` as the authoritative window and does not
    mutate the caller's set.
    """
    new_alerts: list[Alert] = []
    updated_seen = set(seen)
    for alert in alerts:
        fp = fingerprint(alert)
        if fp in updated_seen:
            continue
        updated_seen.add(fp)
        new_alerts.append(alert)
    return new_alerts, updated_seen


def enrich(
    alert: Alert,
    severity_map: dict[str, str],
    runbooks: dict[str, str],
) -> dict[str, Any]:
    """Derive severity, attach a runbook link and build a one-line summary.

    Severity resolution order:
      1. an explicit ``severity`` label on the alert,
      2. a ``severity_map`` entry keyed by alertname,
      3. the ``severity_map`` ``"default"`` entry,
      4. the literal ``"unknown"``.

    The runbook is looked up by alertname in ``runbooks`` and is ``None`` when no
    entry matches. The summary prefers the ``summary`` annotation, then the
    ``description`` annotation, then a synthesized "<alertname> on <instance>".
    """
    labels = alert.labels
    alertname = labels.get("alertname", "")

    severity = (
        labels.get("severity")
        or severity_map.get(alertname)
        or severity_map.get("default")
        or "unknown"
    )

    runbook = runbooks.get(alertname)

    annotations = alert.annotations
    summary = annotations.get("summary") or annotations.get("description")
    if not summary:
        instance = labels.get("instance") or labels.get("job") or "unknown target"
        name = alertname or "alert"
        summary = f"{name} on {instance}"

    return {
        "fingerprint": fingerprint(alert),
        "severity": severity,
        "runbook": runbook,
        "summary": summary,
        "alert": alert,
    }


def _rule_matches(rule: dict[str, Any], enriched: dict[str, Any]) -> bool:
    """Return True when every ``match`` condition in ``rule`` holds."""
    match = rule.get("match", {})
    alert: Alert = enriched["alert"]
    for key, expected in match.items():
        if key == "severity":
            actual = enriched["severity"]
        else:
            actual = alert.labels.get(key)
        if actual != expected:
            return False
    return True


def route(enriched: dict[str, Any], rules: list[dict[str, Any]]) -> list[str]:
    """Evaluate routing rules and return the matched destination names.

    Each rule is a dict of the form ``{"match": {...}, "destinations": [...]}``.
    A rule with an empty ``match`` is treated as a catch-all. Destinations are
    accumulated across all matching rules, de-duplicated while preserving order.
    When no rule matches, the ``"default"`` route is returned (or an empty list
    if no default rule exists).
    """
    destinations: list[str] = []
    matched = False

    # First pass: specific rules only (a rule with a real match condition).
    for rule in rules:
        if not rule.get("match"):
            continue
        if _rule_matches(rule, enriched):
            matched = True
            for dest in rule.get("destinations", []):
                if dest not in destinations:
                    destinations.append(dest)

    # Fallback: catch-all rules (empty match, or named "default") only when
    # no specific rule matched.
    if not matched:
        for rule in rules:
            if rule.get("name") == "default" or not rule.get("match"):
                for dest in rule.get("destinations", []):
                    if dest not in destinations:
                        destinations.append(dest)

    return destinations
