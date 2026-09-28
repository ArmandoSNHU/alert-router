"""FastAPI application exposing the alert router over HTTP."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Query

from . import __version__
from .config import RouterConfig, load_config
from .models import RoutedAlert, Webhook
from .senders import ServiceNowSender, SlackSender
from .service import Router

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "examples" / "config.json"


def build_router() -> Router:
    """Construct a Router from the config pointed to by ALERTROUTER_CONFIG."""
    config_path = os.environ.get("ALERTROUTER_CONFIG", str(DEFAULT_CONFIG))
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        config = RouterConfig()

    # Stub senders are registered by name; they only log until wired via config.
    senders = {
        "slack": SlackSender(),
        "servicenow": ServiceNowSender(),
    }
    return Router(config, senders=senders)


def create_app(router: Router | None = None) -> FastAPI:
    """Application factory. Pass a Router to inject test/config state."""
    app = FastAPI(title="alert-router", version=__version__)
    app.state.router = router or build_router()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.post("/alerts", response_model=list[RoutedAlert])
    def post_alerts(webhook: Webhook) -> list[RoutedAlert]:
        return app.state.router.handle(webhook)

    @app.get("/recent", response_model=list[RoutedAlert])
    def recent(limit: int = Query(default=20, ge=1, le=200)) -> list[RoutedAlert]:
        return app.state.router.recent(limit)

    return app


app = create_app()
