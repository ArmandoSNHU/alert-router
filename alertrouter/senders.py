"""Pluggable alert senders.

The pipeline never talks to a real endpoint on its own. A ``Sender`` receives a
fully routed alert and is responsible for delivery. The default
``CollectorSender`` just keeps sent alerts in memory, which keeps the service
runnable offline and makes assertions in tests trivial.

``SlackSender`` and ``ServiceNowSender`` are deliberate stubs: they build the
payload they *would* post and log it. Wiring a real endpoint (webhook URL, auth
token, instance URL) is a configuration/deployment step, not a code change here.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from .models import RoutedAlert

logger = logging.getLogger(__name__)


@runtime_checkable
class Sender(Protocol):
    """Anything that can deliver a routed alert."""

    def send(self, routed: RoutedAlert) -> None: ...


class CollectorSender:
    """Default sender that records routed alerts in an in-memory list.

    Used as the offline default and by the tests. ``recent`` returns the last
    ``limit`` alerts, newest last.
    """

    def __init__(self) -> None:
        self.sent: list[RoutedAlert] = []

    def send(self, routed: RoutedAlert) -> None:
        self.sent.append(routed)

    def recent(self, limit: int = 20) -> list[RoutedAlert]:
        return self.sent[-limit:]

    def clear(self) -> None:
        self.sent.clear()


class SlackSender:
    """Stub Slack sender.

    Builds a Slack-style message payload and logs it instead of posting. Set
    ``webhook_url`` from config and replace the log call with a real HTTP POST to
    go live -- that wiring is intentionally left out so nothing leaves the host.
    """

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url

    def build_payload(self, routed: RoutedAlert) -> dict:
        runbook_line = f"\n<{routed.runbook}|Runbook>" if routed.runbook else ""
        return {
            "text": (
                f"[{routed.severity.upper()}] {routed.summary}{runbook_line}"
            ),
            "fingerprint": routed.fingerprint,
        }

    def send(self, routed: RoutedAlert) -> None:
        payload = self.build_payload(routed)
        # Real delivery would POST `payload` to `self.webhook_url`.
        logger.info("SlackSender (stub) would post: %s", payload)


class ServiceNowSender:
    """Stub ServiceNow sender.

    Builds an incident record and logs it. Point ``instance_url`` at a real
    ServiceNow instance and replace the log call with a table API POST to go
    live; deliberately omitted so the service stays offline by default.
    """

    def __init__(self, instance_url: str | None = None) -> None:
        self.instance_url = instance_url

    _SEVERITY_TO_IMPACT = {
        "critical": 1,
        "high": 2,
        "warning": 3,
        "info": 4,
    }

    def build_payload(self, routed: RoutedAlert) -> dict:
        return {
            "short_description": routed.summary,
            "impact": self._SEVERITY_TO_IMPACT.get(routed.severity, 3),
            "correlation_id": routed.fingerprint,
            "u_runbook": routed.runbook or "",
        }

    def send(self, routed: RoutedAlert) -> None:
        payload = self.build_payload(routed)
        # Real delivery would POST `payload` to the ServiceNow table API.
        logger.info("ServiceNowSender (stub) would create incident: %s", payload)
