"""API tests using FastAPI's TestClient (no real network)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alertrouter.config import load_config
from alertrouter.senders import ServiceNowSender, SlackSender
from alertrouter.server import create_app
from alertrouter.service import Router

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture()
def client():
    config = load_config(EXAMPLES / "config.json")
    router = Router(
        config,
        senders={"slack": SlackSender(), "servicenow": ServiceNowSender()},
    )
    app = create_app(router)
    return TestClient(app)


@pytest.fixture()
def sample_webhook():
    return json.loads((EXAMPLES / "sample_webhook.json").read_text(encoding="utf-8"))


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_post_alerts_dedupes_and_enriches(client, sample_webhook):
    resp = client.post("/alerts", json=sample_webhook)
    assert resp.status_code == 200
    routed = resp.json()

    # The sample has 3 alerts, two of which are the same alert with reordered
    # labels -> one is deduped, leaving 2 routed alerts.
    assert len(routed) == 2

    by_name = {r["alert"]["labels"]["alertname"]: r for r in routed}
    assert set(by_name) == {"HighErrorRate", "DiskWillFillSoon"}

    high_error = by_name["HighErrorRate"]
    assert high_error["severity"] == "critical"
    assert high_error["runbook"] == "https://runbooks.example.com/high-error-rate"
    # critical -> page-on-critical rule
    assert high_error["destinations"] == ["pagerduty", "slack"]

    disk = by_name["DiskWillFillSoon"]
    assert disk["severity"] == "high"
    # team=infra matches infra-team, severity=high matches ticket-on-high
    assert set(disk["destinations"]) == {"slack", "servicenow"}


def test_recent_reflects_routed_alerts(client, sample_webhook):
    client.post("/alerts", json=sample_webhook)
    resp = client.get("/recent")
    assert resp.status_code == 200
    recent = resp.json()
    assert len(recent) == 2

    limited = client.get("/recent", params={"limit": 1})
    assert len(limited.json()) == 1


def test_duplicate_across_requests_is_dropped(client, sample_webhook):
    first = client.post("/alerts", json=sample_webhook).json()
    assert len(first) == 2
    # Re-posting the same webhook yields no new routed alerts.
    second = client.post("/alerts", json=sample_webhook).json()
    assert second == []
