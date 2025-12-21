"""Lightweight validation/normalization for AI schema outputs."""
from __future__ import annotations

from typing import Any

from module import my_logging


def normalize_ai_payload(payload: dict[str, Any] | None, schema: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized dict honoring the schema defaults/required fields."""
    if not isinstance(payload, dict):
        my_logging.system_warn("LLM payload was not a dict; normalizing to empty payload.")
        payload = {}

    properties = schema.get("properties", {}) or {}
    normalized: dict[str, Any] = {}

    for key, definition in properties.items():
        value = payload.get(key)
        if value is None:
            default = definition.get("default")
            if default is not None:
                normalized[key] = default
            else:
                normalized[key] = _empty_value_for_type(definition.get("type"))
        else:
            normalized[key] = _cast_value(value, definition.get("type"))

    required = schema.get("required") or []
    missing = [field for field in required if not normalized.get(field) and normalized.get(field) is not False]
    if missing:
        my_logging.system_warn(f"LLM payload missing required fields: {missing}")

    # Preserve additional keys not in schema so downstream logic has access.
    for key, value in payload.items():
        if key in normalized:
            continue
        normalized[key] = value

    return normalized


def _empty_value_for_type(type_hint: Any) -> Any:
    if type_hint == "string":
        return ""
    if type_hint in ("integer", "number"):
        return 0
    if type_hint == "boolean":
        return False
    if type_hint == "array":
        return []
    if type_hint == "object":
        return {}
    return None


def _cast_value(value: Any, type_hint: Any) -> Any:
    if type_hint == "string":
        try:
            return str(value)
        except Exception:
            return ""
    if type_hint == "integer":
        try:
            return int(value)
        except Exception:
            my_logging.system_warn(f"Failed to cast LLM payload field to int: {value}")
            return 0
    if type_hint == "number":
        try:
            return float(value)
        except Exception:
            my_logging.system_warn(f"Failed to cast LLM payload field to float: {value}")
            return 0
    if type_hint == "boolean":
        if isinstance(value, bool):
            return value
        lower = str(value).lower()
        return lower in ("true", "1", "yes")
    return value


__all__ = ["normalize_ai_payload"]
