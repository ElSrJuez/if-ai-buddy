"""LLM client factory - creates OpenAI or Foundry local clients."""

from __future__ import annotations

import logging
import os
from typing import Any

from foundry_local import FoundryLocalManager
from openai import OpenAI


logger = logging.getLogger(__name__)


class FoundryChatAdapter:
    """Thin wrapper that presents a chat() surface over Foundry Local."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.manager = FoundryLocalManager()
        self.model_alias = config.get("llm_model_alias")
        if self.model_alias:
            # Ensure the requested model is available before first invocation.
            try:
                self.manager.load_model(self.model_alias)
            except Exception as exc:
                logger.debug("Foundry model preload skipped: %s", exc)

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
            "model": model,
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
    provider = config.get("llm_provider")

    if provider == "openai":
        api_key = config.get("openai_api_key")
        if not api_key:
            env_var = config.get("openai_api_key_env", "OPENAI_API_KEY")
            api_key = os.getenv(env_var)
        
        if not api_key:
            raise ValueError(
                "OpenAI API key not found. Set 'openai_api_key' in config or "
                f"set the {env_var} environment variable."
            )
        
        return OpenAI(api_key=api_key)
    
    elif provider == "foundry":
        return FoundryChatAdapter(config)
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


__all__ = ["create_llm_client"]
