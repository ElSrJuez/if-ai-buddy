"""LLM client factory - creates OpenAI or Foundry local clients."""

from __future__ import annotations

import logging
from typing import Any

from foundry_local import FoundryLocalManager
from openai import OpenAI

from module import config_registry
from module import llm_factory_otheropenai


logger = logging.getLogger(__name__)


class FoundryChatAdapter:
    """Thin wrapper that presents a chat() surface over Foundry Local."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        # Fail fast: Foundry must be fully configured via provider-scoped keys.
        alias = str(config_registry.require_llm_value(config, "alias"))

        self.manager = FoundryLocalManager()
        self._loaded_aliases: dict[str, str] = {}
        self._ensure_alias_loaded(alias)

        self._client = OpenAI(
            base_url=self.manager.endpoint,
            api_key=self.manager.api_key,
        )

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self._ensure_alias_loaded(model),
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response_format = self._build_response_format(schema)
        if response_format:
            kwargs["response_format"] = response_format

        return self._client.chat.completions.create(**kwargs)

    def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": self._ensure_alias_loaded(model),
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        return self._client.chat.completions.create(**kwargs)

    def _build_response_format(self, schema: dict[str, Any] | None) -> dict[str, Any] | None:
        if not schema:
            return None
        schema_name = self.config.get("llm_schema_name", "narration_response")
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }

    def _ensure_alias_loaded(self, alias: str) -> str:
        model_id = self._loaded_aliases.get(alias)
        if model_id:
            return model_id

        model_info = self.manager.load_model(alias)
        if not model_info or not getattr(model_info, "id", None):
            raise ValueError(f"Could not resolve Foundry model alias '{alias}'")

        model_id = model_info.id
        self._loaded_aliases[alias] = model_id
        return model_id


def create_llm_client(config: dict[str, Any]) -> Any:
    """
    Create and return an LLM client based on config.
    
    Args:
        config: Configuration dict with llm_provider, openai_api_key, etc.
    
    Returns:
        Initialized OpenAI or Foundry local client.
    
    Raises:
        ValueError: If provider is unknown or required config is missing.
    """
    provider = config_registry.llm_provider(config)

    if provider == "foundry":
        return FoundryChatAdapter(config)

    if provider == "otheropenai":
        return llm_factory_otheropenai.create_otheropenai_client(config)
    
    else:
        # llm_provider() already validates supported values; keep this for safety.
        raise ValueError(f"Unknown LLM provider: {provider}")


__all__ = ["create_llm_client"]
