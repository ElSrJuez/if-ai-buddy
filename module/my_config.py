"""Lightweight configuration loader for If AI Buddy."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Mapping

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.json"
_config: dict[str, Any] = {}


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration from disk and cache it in memory."""
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    _config.clear()
    _config.update(data)
    _config["_config_path"] = str(path)
    return _config.copy()


def update_config(overrides: Mapping[str, Any]) -> None:
    """Merge overrides into the cached configuration."""
    _config.update(overrides)


def set_config_value(setting_name: str, value: Any) -> None:
    """Set a single configuration value in memory."""
    _config[setting_name] = value


def get_config_value(setting_name: str, default: Any | None = None) -> Any:
    """Retrieve a configuration value by name."""
    return _config.get(setting_name, default)
