"""Routing configuration loading.

The config is plain JSON so it can be edited and version-controlled without
touching code. See ``examples/config.json`` for the shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RouterConfig:
    """Parsed routing configuration."""

    severity_map: dict[str, str] = field(default_factory=dict)
    runbooks: dict[str, str] = field(default_factory=dict)
    rules: list[dict[str, Any]] = field(default_factory=list)
    destinations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouterConfig":
        return cls(
            severity_map=data.get("severity_map", {}),
            runbooks=data.get("runbooks", {}),
            rules=data.get("rules", []),
            destinations=data.get("destinations", {}),
        )


def load_config(path: str | Path) -> RouterConfig:
    """Load routing configuration from a JSON file."""
    text = Path(path).read_text(encoding="utf-8")
    return RouterConfig.from_dict(json.loads(text))
