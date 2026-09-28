"""alert-router: ingest, normalize, deduplicate, enrich and route monitoring alerts.

A small webhook service that accepts Alertmanager-style payloads, deduplicates
them by a stable label fingerprint, enriches each alert with a severity and an
optional runbook link, then routes it to one or more destinations by rule.

Outbound delivery is pluggable. The default sender is an in-memory collector so
the whole pipeline runs offline with no network access.
"""

__version__ = "0.1.0"
