"""Lightweight configuration loader for If AI Buddy."""

from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Any, Mapping

from module.config_registry import apply_aliases, resolve_path, validate_config

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.json"
_SCENE_IMAGE_CONFIG_PATH = _PROJECT_ROOT / "config" / "scene_image_config.json"
_SCENE_IMAGE_PROMPT_TEMPLATE_PATH = _PROJECT_ROOT / "config" / "scene_image_prompt_template.json"
_config: dict[str, Any] = {}
_scene_image_config: dict[str, Any] = {}
_scene_image_prompt_template: dict[str, Any] = {}
_SCHEMA_KEYS = ("game_engine_schema_path", "ai_engine_schema_path")


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration from disk and cache it in memory."""
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    _config.clear()
    _config.update(data)
    apply_aliases(_config)
    
    # Load environment variables for sensitive config
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    
    # Override with environment variables
    if "DFROTZ_BASE_URL" in os.environ:
        _config["dfrotz_base_url"] = os.environ["DFROTZ_BASE_URL"]
    
    validate_config(_config, sections=("controller", "llm", "logging", "persistence", "schema"))
    _config["_project_root"] = str(_PROJECT_ROOT)
    _config["_config_path"] = str(path)
    _normalize_schema_paths(_config)
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


def get_schema_path(name: str) -> str:
    """Return the configured schema path for a named schema."""
    mapping = {
        "game_engine": "game_engine_schema_path",
        "ai_engine": "ai_engine_schema_path",
    }
    if name not in mapping:
        raise KeyError(f"Unknown schema '{name}'")
    key = mapping[name]
    if key not in _config:
        raise KeyError(f"Schema path '{key}' is not loaded in configuration")
    return str(_config[key])


def get_schema_paths() -> dict[str, str]:
    """Return all known schema paths."""
    return {
        "game_engine": get_schema_path("game_engine"),
        "ai_engine": get_schema_path("ai_engine"),
    }


def load_scene_image_config() -> dict[str, Any]:
    """Load scene image configuration from disk and cache it in memory."""
    if not _scene_image_config:
        # Load base config from JSON
        data = json.loads(_SCENE_IMAGE_CONFIG_PATH.read_text(encoding="utf-8"))
        
        # Load environment variables for sensitive config
        env_path = _PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        
        # Override with environment variables
        if "SD_SERVER_BASE_URL" in os.environ:
            data["sd_server_base_url"] = os.environ["SD_SERVER_BASE_URL"]
        
        _scene_image_config.update(data)
    return _scene_image_config.copy()


def get_scene_image_config_value(setting_name: str, default: Any | None = None) -> Any:
    """Retrieve a scene image configuration value by name."""
    if not _scene_image_config:
        load_scene_image_config()
    return _scene_image_config.get(setting_name, default)


def load_scene_image_prompt_template() -> dict[str, Any]:
    """Load scene image prompt template from disk and cache it in memory."""
    if not _scene_image_prompt_template:
        data = json.loads(_SCENE_IMAGE_PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8"))
        _scene_image_prompt_template.update(data)
    return _scene_image_prompt_template.copy()


def get_scene_image_prompt_template() -> dict[str, Any]:
    """Get the cached scene image prompt template."""
    if not _scene_image_prompt_template:
        load_scene_image_prompt_template()
    return _scene_image_prompt_template.copy()


def _normalize_schema_paths(config: dict[str, Any]) -> None:
    for key in _SCHEMA_KEYS:
        if key in config:
            config[key] = str(resolve_path(config, key, project_root=_PROJECT_ROOT))
