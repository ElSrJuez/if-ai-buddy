
"""OtherOpenAI client factory/adapter.

This is for OpenAI-compatible endpoints (e.g., llama.cpp / Lemonade server).

Design:
- Provide the same internal surface as FoundryChatAdapter: chat() + stream_chat().
- Fail fast on missing config (no env fallbacks, no defaults).
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from module import config_registry


class OtherOpenAIChatAdapter:
	"""Adapter that presents a chat()/stream_chat() surface over an OpenAI-compatible endpoint."""

	def __init__(self, config: dict[str, Any]) -> None:
		self.config = config
		settings = config_registry.resolve_llm_settings(config)
		if settings.provider != "otheropenai":
			raise ValueError(
				"OtherOpenAIChatAdapter requires llm_provider 'otheropenai' "
				f"(got '{settings.provider}')"
			)

		self._client = OpenAI(
			base_url=settings.endpoint,
			api_key=settings.openai_api_key,
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

		# Optional structured output support (only if the endpoint supports it).
		if schema:
			schema_name = self.config.get("llm_schema_name", "narration_response")
			kwargs["response_format"] = {
				"type": "json_schema",
				"json_schema": {
					"name": schema_name,
					"schema": schema,
					"strict": True,
				},
			}

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
			"model": model,
			"messages": messages,
			"stream": True,
		}
		if temperature is not None:
			kwargs["temperature"] = temperature
		if max_tokens is not None:
			kwargs["max_tokens"] = max_tokens
		return self._client.chat.completions.create(**kwargs)


def create_otheropenai_client(config: dict[str, Any]) -> OtherOpenAIChatAdapter:
	return OtherOpenAIChatAdapter(config)


__all__ = ["OtherOpenAIChatAdapter", "create_otheropenai_client"]
