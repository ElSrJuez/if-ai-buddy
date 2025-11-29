"""LLM client factory - creates OpenAI or Foundry local clients."""

from __future__ import annotations

import os
from typing import Any

from foundry_local import FoundryLocalManager
from openai import OpenAI


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
    provider = config.get("llm_provider", "foundry")

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
        return FoundryLocalManager()
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


__all__ = ["create_llm_client"]
