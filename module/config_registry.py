"""Central configuration registry and validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

__all__ = [
    "ConfigValidationError",
    "apply_aliases",
    "required_keys",
    "validate_config",
    "resolve_path",
]


class ConfigValidationError(ValueError):
    """Raised when required configuration keys are missing."""


SECTION_KEYS: dict[str, set[str]] = {
    "controller": {
        "player_name",
        "default_game",
        "dfrotz_base_url",
    },
    "llm": {
        "llm_provider",
        "system_prompt",
        "user_prompt_template",
        "llm_model_alias",
    },
    "logging": {
        "system_log",
        "gameapi_jsonl",
        "rest_jsonl",
        "game_engine_jsonl_filename_template",
        "llm_completion_jsonl_filename_template",
        "loglevel",
    },
    "schema": {
        "game_engine_schema_path",
        "ai_engine_schema_path",
    },
}

ALIAS_GROUPS: tuple[set[str], ...] = (
    {"ai_engine_schema_path", "response_schema_path"},
)


def _select_keys(sections: Iterable[str] | None) -> set[str]:
    if sections is None:
        sections = SECTION_KEYS.keys()
    keys: set[str] = set()
    for section in sections:
        if section not in SECTION_KEYS:
            raise KeyError(f"Unknown config section '{section}'")
        keys.update(SECTION_KEYS[section])
    return keys


def required_keys(sections: Iterable[str] | None = None) -> set[str]:
    """Return the set of required keys for the provided sections."""
    return _select_keys(sections)


def apply_aliases(config: MutableMapping[str, object]) -> None:
    """Populate canonical keys across alias groups when missing."""
    for group in ALIAS_GROUPS:
        value = None
        for key in group:
            if key in config:
                value = config[key]
                break
        if value is None:
            continue
        for key in group:
            config.setdefault(key, value)


def validate_config(config: Mapping[str, object], *, sections: Iterable[str] | None = None) -> None:
    """Validate that required keys exist for the given sections."""
    missing = [key for key in _select_keys(sections) if key not in config]
    if missing:
        raise ConfigValidationError(
            "Missing required config keys: " + ", ".join(sorted(missing))
        )


def resolve_path(config: Mapping[str, object], key: str, *, project_root: Path | None = None) -> Path:
    """Resolve a path from config, making it absolute relative to project root."""
    if key not in config:
        raise ConfigValidationError(f"Missing required config key '{key}'")
    path = Path(str(config[key]))
    if path.is_absolute() or project_root is None:
        return path
    return project_root / path
