"""Central configuration registry and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

__all__ = [
    "ConfigValidationError",
    "apply_aliases",
    "LlmSettings",
    "llm_provider",
    "llm_provider_key",
    "require_llm_value",
    "resolve_llm_settings",
    "required_keys",
    "validate_config",
    "resolve_path",
    "resolve_template_path",
]


class ConfigValidationError(ValueError):
    """Raised when required configuration keys are missing."""


@dataclass(frozen=True, slots=True)
class LlmSettings:
    provider: str
    alias: str
    temperature: float
    max_tokens: int
    endpoint: str | None = None
    openai_api_key: str | None = None


SECTION_KEYS: dict[str, set[str]] = {
    "controller": {
        "player_name",
        "default_game",
        "dfrotz_base_url",
    },
    "llm": {
        "llm_provider",
        "llm_narration_system_prompt",
        "llm_narration_user_prompt_template",
        "llm_memory_system_prompt",
        "llm_memory_user_prompt_template",
    },
    "logging": {
        "system_log",
        "gameapi_jsonl",
        "rest_jsonl",
        "game_engine_jsonl_filename_template",
        "llm_completion_jsonl_filename_template",
        "common_llm_layer_jsonl",
        "loglevel",
    },
    "persistence": {
        "memory_db_path_template",
    },
    "schema": {
        "game_engine_schema_path",
        "ai_engine_schema_path",
    },
}

ALIAS_GROUPS: tuple[set[str], ...] = (
    {"ai_engine_schema_path", "response_schema_path"},
    {"llm_narration_system_prompt", "system_prompt"},
    {"llm_memory_system_prompt", "llm_narration_system_prompt", "system_prompt"},
    {"llm_narration_user_prompt_template", "user_prompt_template"},
    {"llm_memory_user_prompt_template", "llm_narration_user_prompt_template", "user_prompt_template"},
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
    if sections is None or "llm" in sections:
        _validate_llm_provider_keys(config)


def llm_provider(config: Mapping[str, object]) -> str:
    if "llm_provider" not in config:
        raise ConfigValidationError("Missing required config key 'llm_provider'")
    provider = str(config["llm_provider"]).strip()
    if provider not in ("foundry", "otheropenai"):
        raise ConfigValidationError(f"Unsupported llm_provider '{provider}'")
    return provider


def llm_provider_key(provider: str, field: str) -> str:
    return f"llm_model_{field}_{provider}"


def require_llm_value(config: Mapping[str, object], field: str) -> object:
    provider = llm_provider(config)
    key = llm_provider_key(provider, field)
    if key not in config:
        raise ConfigValidationError(
            f"Missing required config key '{key}' for llm_provider '{provider}'"
        )
    return config[key]


def _validate_llm_provider_keys(config: Mapping[str, object]) -> None:
    provider = llm_provider(config)

    if provider == "foundry":
        required_fields = ("alias", "temperature", "max_tokens")
    elif provider == "otheropenai":
        required_fields = ("alias", "temperature", "max_tokens", "endpoint", "openai_api_key")
    else:
        raise ConfigValidationError(f"Unsupported llm_provider '{provider}'")

    missing: list[str] = []
    for field in required_fields:
        key = llm_provider_key(provider, field)
        if key not in config:
            missing.append(key)
    if missing:
        raise ConfigValidationError(
            "Missing required config keys for llm_provider "
            f"'{provider}': {', '.join(sorted(missing))}"
        )


def resolve_llm_settings(config: Mapping[str, object]) -> LlmSettings:
    """Resolve provider-scoped LLM settings in a single, strict place.

    No defaults: missing keys or invalid types raise ConfigValidationError.
    """

    provider = llm_provider(config)

    alias = str(require_llm_value(config, "alias")).strip()
    if not alias:
        raise ConfigValidationError("Resolved LLM alias is empty")

    try:
        temperature = float(require_llm_value(config, "temperature"))
    except Exception as exc:  # noqa: BLE001
        raise ConfigValidationError(f"Invalid LLM temperature: {exc}")

    try:
        max_tokens = int(require_llm_value(config, "max_tokens"))
    except Exception as exc:  # noqa: BLE001
        raise ConfigValidationError(f"Invalid LLM max_tokens: {exc}")

    endpoint: str | None = None
    openai_api_key: str | None = None

    if provider == "otheropenai":
        endpoint = str(require_llm_value(config, "endpoint")).strip()
        if not endpoint:
            raise ConfigValidationError("Resolved LLM endpoint is empty")
        openai_api_key = str(require_llm_value(config, "openai_api_key")).strip()
        if not openai_api_key:
            raise ConfigValidationError("Resolved otheropenai api_key is empty")

    return LlmSettings(
        provider=provider,
        alias=alias,
        temperature=temperature,
        max_tokens=max_tokens,
        endpoint=endpoint,
        openai_api_key=openai_api_key,
    )


def resolve_path(config: Mapping[str, object], key: str, *, project_root: Path | None = None) -> Path:
    """Resolve a path from config, making it absolute relative to project root."""
    if key not in config:
        raise ConfigValidationError(f"Missing required config key '{key}'")
    path = Path(str(config[key]))
    if path.is_absolute() or project_root is None:
        return path
    return project_root / path


def resolve_template_path(
    config: Mapping[str, object],
    key: str,
    context: Mapping[str, object],
    *,
    project_root: Path | None = None,
) -> Path:
    """Resolve a templated path from config (e.g., 'log/{player}.json')."""
    if key not in config:
        raise ConfigValidationError(f"Missing required config key '{key}'")
    template = str(config[key])
    try:
        formatted = template.format(**context)
    except KeyError as exc:
        raise ConfigValidationError(
            f"Failed to format template '{template}': missing placeholder {exc}"
        )
    path = Path(formatted)
    if path.is_absolute() or project_root is None:
        return path
    return project_root / path
