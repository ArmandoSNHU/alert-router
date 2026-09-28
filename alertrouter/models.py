"""Pydantic models for the alert-router request/response surface."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """A single alert, shaped after the Alertmanager webhook alert object."""

    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    status: Literal["firing", "resolved"] = "firing"
    starts_at: Optional[str] = None


class Webhook(BaseModel):
    """The inbound webhook payload: a batch of alerts."""

    alerts: list[Alert]


class RoutedAlert(BaseModel):
    """The result of running one alert through the pipeline."""

    fingerprint: str
    severity: str
    summary: str
    runbook: Optional[str] = None
    destinations: list[str]
    alert: Alert
