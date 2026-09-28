"""The Router: wires the pure pipeline to configured senders."""

from __future__ import annotations

import logging
from typing import Mapping

from .config import RouterConfig
from .models import RoutedAlert, Webhook
from .pipeline import dedup, enrich, route
from .senders import CollectorSender, Sender

logger = logging.getLogger(__name__)


class Router:
    """Run inbound webhooks through dedup -> enrich -> route -> send.

    A shared ``CollectorSender`` is always present so ``/recent`` and tests have
    a consistent view of what was delivered. Additional named senders can be
    supplied; destinations that name a sender are delivered to it, and every
    routed alert is also recorded by the collector.
    """

    def __init__(
        self,
        config: RouterConfig,
        senders: Mapping[str, Sender] | None = None,
        collector: CollectorSender | None = None,
    ) -> None:
        self.config = config
        self.collector = collector or CollectorSender()
        self.senders: dict[str, Sender] = dict(senders or {})
        self._seen: set[str] = set()

    def handle(self, webhook: Webhook) -> list[RoutedAlert]:
        """Process a webhook and return the alerts that were routed.

        Duplicates already seen by this Router are dropped and do not appear in
        the result.
        """
        new_alerts, self._seen = dedup(webhook.alerts, self._seen)

        routed_alerts: list[RoutedAlert] = []
        for alert in new_alerts:
            enriched = enrich(alert, self.config.severity_map, self.config.runbooks)
            destinations = route(enriched, self.config.rules)
            routed = RoutedAlert(
                fingerprint=enriched["fingerprint"],
                severity=enriched["severity"],
                summary=enriched["summary"],
                runbook=enriched["runbook"],
                destinations=destinations,
                alert=alert,
            )
            self._dispatch(routed)
            routed_alerts.append(routed)

        return routed_alerts

    def _dispatch(self, routed: RoutedAlert) -> None:
        # The collector always records the alert (offline default + /recent).
        self.collector.send(routed)
        for dest in routed.destinations:
            sender = self.senders.get(dest)
            if sender is not None:
                sender.send(routed)
            else:
                logger.debug("No sender configured for destination %r", dest)

    def recent(self, limit: int = 20) -> list[RoutedAlert]:
        return self.collector.recent(limit)
