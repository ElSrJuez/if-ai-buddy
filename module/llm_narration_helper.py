"""LLM narration helper focused on streaming outputs for the narration column."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from openai import OpenAI

from module import my_logging
from module.ai_engine_parsing import normalize_ai_payload
from module.llm_factory_FoundryLocal import create_llm_client
from module.narration_job_builder import NarrationJobSpec


class CompletionsHelper:
    """Helper that orchestrates narration requests and streaming updates."""

    def __init__(self, config: dict[str, Any], response_schema: dict[str, Any]) -> None:
        self.config = config
        self.response_schema = response_schema
        self.llm_client = create_llm_client(config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream_narration(
        self,
        job: NarrationJobSpec,
        on_chunk: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Stream narration to the provided callback and return the normalized payload."""
        loop = asyncio.get_running_loop()
        start_time = time.time()
        messages = job.messages
        metadata = job.metadata or {}

        try:
            if self.config.get("llm_provider") == "openai":
                narration_text, raw_response = await self._stream_openai(
                    messages,
                    on_chunk,
                    loop,
                )
            else:
                narration_text, raw_response = await self._stream_foundry(
                    messages,
                    on_chunk,
                    loop,
                )

            payload = normalize_ai_payload(
                {"narration": narration_text}, self.response_schema
            )
            tokens = self._extract_token_count(raw_response)
            latency = time.time() - start_time
            model = self.config.get("llm_model_alias", "unknown")

            result = {
                "payload": payload,
                "raw_response": raw_response,
                "diagnostics": {
                    "latency_seconds": latency,
                    "tokens": tokens,
                    "model": model,
                },
            }

            my_logging.log_completion_event({
                "model": model,
                "latency": latency,
                "tokens": tokens,
                "payload_keys": list(payload.keys()),
                "normalized_payload": payload,
                "prompt_messages": messages,
                "raw_response_dump": self._serialize_for_logging(raw_response),
                "job_metadata": metadata,
            })

            return result

        except Exception as exc:
            my_logging.system_debug(f"Narration stream error: {exc}")
            if on_chunk:
                loop.call_soon_threadsafe(on_chunk, "(Narration unavailable)")
            latency = time.time() - start_time
            model = self.config.get("llm_model_alias", "unknown")
            fallback_payload = {
                "narration": "The game continues...",
                "game_intent": "Unknown",
                "game_meta_intent": "Unknown",
                "hidden_next_command": "look",
                "hidden_next_command_confidence": 0,
            }
            payload = normalize_ai_payload(fallback_payload, self.response_schema)
            my_logging.log_completion_event({
                "model": model,
                "latency": latency,
                "tokens": 0,
                "error": str(exc),
                "prompt_messages": messages,
                "raw_response_dump": self._serialize_for_logging(None),
                "normalized_payload": payload,
                "job_metadata": metadata,
            })
            return {
                "payload": payload,
                "raw_response": None,
                "diagnostics": {
                    "latency_seconds": latency,
                    "tokens": 0,
                    "model": model,
                    "error": str(exc),
                },
            }

    def run(self, job: NarrationJobSpec) -> dict[str, Any]:
        """Synchronous fallback for legacy callers (non-streaming)."""
        messages = job.messages

        if self.config.get("llm_provider") == "openai":
            raw_response = self._call_openai(messages)
        else:
            raw_response = self._call_foundry(messages)

        payload = self._parse_response(raw_response)
        payload = normalize_ai_payload(payload, self.response_schema)
        latency = 0
        tokens = self._extract_token_count(raw_response)

        result = {
            "payload": payload,
            "raw_response": raw_response,
            "diagnostics": {
                "latency_seconds": latency,
                "tokens": tokens,
                "model": self.config["llm_model_alias"],
            },
        }
        return result

    async def _stream_openai(
        self,
        messages: list[dict[str, str]],
        on_chunk: Callable[[str], None] | None,
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[str, Any]:
        model = self.config["llm_model_alias"]
        temperature = self.config.get("llm_temperature", 0.7)
        max_tokens = self.config.get("max_tokens", 1000)

        def _job() -> tuple[str, Any]:
            chunks: list[str] = []
            stream = self.llm_client.responses.stream(
                model=model,
                input={"messages": messages},
                temperature=temperature,
                max_output_tokens=max_tokens,
                max_tokens=max_tokens,
            )
            with stream as events:
                for event in events:
                    chunk = self._extract_stream_chunk(event)
                    if chunk:
                        chunks.append(chunk)
                        if on_chunk:
                            loop.call_soon_threadsafe(on_chunk, chunk)
                final_response = events.get_final_response()
            return "".join(chunks), final_response

        return await asyncio.to_thread(_job)

    async def _stream_foundry(
        self,
        messages: list[dict[str, str]],
        on_chunk: Callable[[str], None] | None,
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[str, Any]:
        model = self.config["llm_model_alias"]
        temperature = self.config.get("llm_temperature", 0.7)
        max_tokens = self.config.get("max_tokens", 1000)

        def _job() -> tuple[str, Any]:
            chunks: list[str] = []
            stream = self.llm_client.stream_chat(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            final_response = None
            if hasattr(stream, "__enter__"):
                with stream as events:
                    for event in events:
                        chunk = self._extract_stream_chunk(event)
                        if chunk:
                            chunks.append(chunk)
                            if on_chunk:
                                loop.call_soon_threadsafe(on_chunk, chunk)
                    if hasattr(events, "get_final_response"):
                        final_response = events.get_final_response()
            else:
                for event in stream:
                    chunk = self._extract_stream_chunk(event)
                    if chunk:
                        chunks.append(chunk)
                        if on_chunk:
                            loop.call_soon_threadsafe(on_chunk, chunk)
                if hasattr(stream, "get_final_response"):
                    final_response = stream.get_final_response()
            narration_text = "".join(chunks)
            return narration_text, final_response

        return await asyncio.to_thread(_job)

    def _call_openai(self, messages: list[dict[str, str]]) -> Any:
        if not isinstance(self.llm_client, OpenAI):
            raise ValueError("OpenAI provider requires OpenAI client instance")

        return self.llm_client.chat.completions.create(
            model=self.config["llm_model_alias"],
            messages=messages,
            temperature=self.config.get("llm_temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 1000),
        )

    def _call_foundry(self, messages: list[dict[str, str]]) -> Any:
        return self.llm_client.chat(
            model=self.config["llm_model_alias"],
            messages=messages,
            temperature=self.config.get("llm_temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 1000),
        )

    def _parse_response(self, raw_response: Any) -> dict[str, Any]:
        if raw_response is None:
            return {"narration": "Error: no response from LLM"}

        if hasattr(raw_response, "choices") and raw_response.choices:
            choice = raw_response.choices[0]
            if hasattr(choice, "message"):
                return {"narration": choice.message.content}
            if hasattr(choice, "parsed") and hasattr(choice.parsed, "model_dump"):
                return choice.parsed.model_dump()
        if isinstance(raw_response, dict):
            return raw_response
        if hasattr(raw_response, "content"):
            return {"narration": str(raw_response.content)}
        return {"narration": "Error: unknown response format"}

    def _extract_stream_chunk(self, event: Any) -> str | None:
        if event is None:
            return None
        # Chat Completions streaming chunks: chunk.choices[0].delta.content
        if hasattr(event, "choices"):
            try:
                choices = event.choices
                if choices and hasattr(choices[0], "delta"):
                    delta = choices[0].delta
                    content = getattr(delta, "content", None)
                    if content:
                        return str(content)
            except Exception:
                pass
        if isinstance(event, dict):
            delta = event.get("delta")
            text = self._flatten_delta(delta)
            if text:
                return text
        if hasattr(event, "delta"):
            text = self._flatten_delta(event.delta)
            if text:
                return text
        if hasattr(event, "content"):
            return str(event.content)
        return None

    def _flatten_delta(self, delta: Any) -> str | None:
        if delta is None:
            return None
        if isinstance(delta, str):
            return delta
        if isinstance(delta, list):
            return "".join(str(item) for item in delta)
        if isinstance(delta, dict):
            texts: list[str] = []
            for value in delta.values():
                if isinstance(value, str):
                    texts.append(value)
            return "".join(texts) if texts else None
        if hasattr(delta, "text"):
            return str(getattr(delta, "text"))
        if hasattr(delta, "output_text"):
            return str(getattr(delta, "output_text"))
        if hasattr(delta, "content"):
            return str(getattr(delta, "content"))
        return None

    def _extract_token_count(self, raw_response: Any) -> int:
        if raw_response is None:
            return 0
        if hasattr(raw_response, "usage"):
            usage = raw_response.usage
            if hasattr(usage, "total_tokens"):
                return usage.total_tokens
        if isinstance(raw_response, dict) and "usage" in raw_response:
            usage = raw_response["usage"]
            if isinstance(usage, dict):
                return usage.get("total_tokens", 0)
        return 0

    def _serialize_for_logging(self, raw_response: Any) -> Any:
        if raw_response is None:
            return None
        if isinstance(raw_response, (str, int, float, bool)):
            return raw_response
        if isinstance(raw_response, (list, dict)):
            return raw_response
        if hasattr(raw_response, "model_dump"):
            try:
                return raw_response.model_dump()
            except Exception:
                pass
        if hasattr(raw_response, "dict"):
            try:
                return raw_response.dict()
            except Exception:
                pass
        if hasattr(raw_response, "__dict__"):
            try:
                return {
                    key: str(value)
                    for key, value in raw_response.__dict__.items()
                }
            except Exception:
                pass
        return repr(raw_response)


