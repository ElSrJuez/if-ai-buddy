"""LLM completions helper with OpenAI and Foundry Local backends."""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from module import my_logging

try:
    from foundry_local import FoundryLocalManager
except ImportError:  # pragma: no cover - optional dependency
    FoundryLocalManager = None  # type: ignore


@dataclass
class CompletionResult:
    payload: dict[str, Any]
    raw_text: str
    model: str
    provider: str
    latency_ms: float
    usage: dict[str, Any] | None


class CompletionError(RuntimeError):
    pass


class CompletionsHelper:
    """Simple abstraction for schema-guided narrator calls."""

    def __init__(self, config: dict[str, Any], schema: dict[str, Any]) -> None:
        self.config = config
        self.schema = schema
        self.provider = str(self._require("llm_provider")).lower()
        if self.provider not in {"openai", "foundry"}:
            raise CompletionError(
                f"Unsupported llm_provider '{self.provider}'. Expected 'openai' or 'foundry'."
            )
        self.model = str(self._require("llm_model_alias"))
        self.temperature = float(self._require("llm_temperature"))
        self.max_tokens = int(self._require("max_tokens"))
        self.system_prompt = self._render_system_prompt()
        self.user_template = str(self._require("user_prompt_template"))
        self._openai_client: AsyncOpenAI | None = None
        self._foundry_client: AsyncOpenAI | None = None
        self._openai_api_key = None
        self._foundry_manager: Any | None = None

    def _render_system_prompt(self) -> str:
        schema_str = json.dumps(self.schema, indent=2)
        prompt = str(self._require("system_prompt"))
        return prompt.replace("|{response_schema}|", schema_str)

    async def run(self, transcript_chunk: str) -> CompletionResult:
        messages = self._build_messages(transcript_chunk)
        start = time.perf_counter()
        if my_logging.is_debug_enabled():
            my_logging.log_completion_event(
                {
                    "event": "request",
                    "provider": self.provider,
                    "model": self.model,
                    "messages": messages,
                }
            )
        if self.provider == "foundry":
            raw, usage = await self._call_foundry(messages)
        else:
            raw, usage = await self._call_openai(messages)
        latency = (time.perf_counter() - start) * 1000
        my_logging.log_completion_event(
            {
                "event": "response",
                "provider": self.provider,
                "model": self.model,
                "raw": raw,
                "usage": usage,
                "latency_ms": latency,
            }
        )
        my_logging.system_debug(
            f"LLM raw response (provider={self.provider}, model={self.model}): {raw[:500]}"
        )
        payload = self._ensure_json(raw)
        return CompletionResult(
            payload=payload,
            raw_text=raw,
            model=self.model or "unknown",
            provider=self.provider,
            latency_ms=latency,
            usage=usage,
        )

    def _build_messages(self, transcript_chunk: str) -> list[dict[str, str]]:
        user_prompt = self.user_template.format(game_log=transcript_chunk)
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    async def _call_openai(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, dict[str, Any] | None]:
        if self._openai_api_key is None:
            self._openai_api_key = self._resolve_secret(
                value_field="openai_api_key",
                env_field="openai_api_key_env",
                secret_label="OpenAI API key",
            )
        client = self._openai_client or AsyncOpenAI(api_key=self._openai_api_key)
        self._openai_client = client
        response = await client.chat.completions.create(  # type: ignore[arg-type]
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        content_parts = response.choices[0].message.content
        if isinstance(content_parts, list):
            raw_fragments = []
            for part in content_parts:
                if isinstance(part, dict):
                    raw_fragments.append(str(part.get("text", "")))
            raw_text = "".join(raw_fragments)
        else:
            raw_text = content_parts or ""
        usage = self._serialize_usage(getattr(response, "usage", None))
        return raw_text.strip(), usage

    async def _call_foundry(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, dict[str, Any] | None]:
        manager = await self._ensure_foundry_manager()
        base_url = getattr(manager, "endpoint", None)
        if not base_url:
            raise CompletionError("FoundryLocalManager does not expose an endpoint")
        api_key = getattr(manager, "api_key", None) or "local"
        client = self._foundry_client or AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._foundry_client = client
        model_id = await self._resolve_foundry_model_id(manager)
        response = await client.chat.completions.create(  # type: ignore[arg-type]
            model=model_id,
            messages=messages,  # type: ignore[arg-type]
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        content_parts = response.choices[0].message.content
        if isinstance(content_parts, list):
            raw_fragments = []
            for part in content_parts:
                if isinstance(part, dict):
                    raw_fragments.append(str(part.get("text", "")))
            raw_text = "".join(raw_fragments)
        else:
            raw_text = content_parts or ""
        usage = self._serialize_usage(getattr(response, "usage", None))
        return raw_text.strip(), usage

    def _ensure_json(self, raw_text: str) -> dict[str, Any]:
        raw_text = raw_text.strip()
        if not raw_text:
            raise CompletionError("LLM returned empty response")
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            my_logging.system_debug(
                f"LLM response could not be parsed as JSON. Raw payload: {raw_text}"
            )
            raise CompletionError("LLM response was not valid JSON") from exc

    @staticmethod
    def _serialize_usage(usage: Any) -> dict[str, Any] | None:
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if hasattr(usage, "dict"):
            return usage.dict()
        if isinstance(usage, dict):
            return usage
        return None

    def _require(self, key: str) -> Any:
        if key not in self.config:
            raise CompletionError(f"Missing configuration value: {key}")
        return self.config[key]

    def _resolve_secret(
        self,
        *,
        value_field: str,
        env_field: str,
        secret_label: str,
        optional: bool = False,
    ) -> str | None:
        if value_field in self.config:
            secret = str(self.config[value_field]).strip()
            if not secret:
                raise CompletionError(f"Configuration value {value_field} cannot be empty")
            return secret
        if env_field in self.config:
            env_name = str(self.config[env_field]).strip()
            if not env_name:
                raise CompletionError(f"Configuration value {env_field} cannot be empty")
            secret = os.environ.get(env_name)
            if not secret:
                raise CompletionError(
                    f"Environment variable {env_name} for {secret_label} is not set"
                )
            return secret
        if optional:
            return None
        raise CompletionError(
            f"Provide {value_field} or {env_field} in config for {secret_label}"
        )

    async def _ensure_foundry_manager(self) -> Any:
        manager_cls = FoundryLocalManager
        if manager_cls is None:
            raise CompletionError(
                "foundry_local package is not installed but llm_provider is 'foundry'"
            )
        if self._foundry_manager is None:
            loop = asyncio.get_running_loop()
            self._foundry_manager = await loop.run_in_executor(
                None, lambda: manager_cls(self.model)
            )
        return self._foundry_manager

    async def _resolve_foundry_model_id(self, manager: Any) -> str:
        loop = asyncio.get_running_loop()
        model_info = await loop.run_in_executor(None, manager.get_model_info, self.model)
        if isinstance(model_info, dict):
            return str(model_info.get("id") or model_info.get("model_id") or self.model)
        identifier = getattr(model_info, "id", None) or getattr(
            model_info, "model_id", None
        )
        return str(identifier or self.model)


__all__ = ["CompletionsHelper", "CompletionResult", "CompletionError"]
