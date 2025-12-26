"""LLM narration helper focused on streaming outputs for the narration column."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from module import my_logging
from module import common_llm_layer
from module import config_registry
from module.ai_engine_parsing import normalize_ai_payload
from module.llm_factory_FoundryLocal import create_llm_client
from module.narration_job_builder import NarrationJobSpec


class CompletionsHelper:
    """Helper that orchestrates narration requests and streaming updates."""

    def __init__(self, config: dict[str, Any], response_schema: dict[str, Any]) -> None:
        self.config = config
        self.response_schema = response_schema
        self.llm_settings = config_registry.resolve_llm_settings(config)
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
        provider = self.llm_settings.provider
        model = self.llm_settings.alias

        try:
            narration_text, raw_response = await self._stream_chat(
                messages,
                on_chunk,
                loop,
            )

            payload = normalize_ai_payload(
                {"narration": narration_text}, self.response_schema
            )
            tokens = self._extract_token_count(raw_response)
            latency = time.time() - start_time

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

            # Compact, query-friendly interaction history (no streaming internals).
            common_llm_layer.log_simple_interaction_history(
                request={
                    "provider": provider,
                    "model": model,
                },
                messages=messages,
                response_text=narration_text,
                job_metadata=metadata,
            )

            return result

        except Exception as exc:
            my_logging.system_debug(f"Narration stream error: {exc}")
            if on_chunk:
                loop.call_soon_threadsafe(on_chunk, "(Narration unavailable)")
            latency = time.time() - start_time
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

            common_llm_layer.log_simple_interaction_history(
                request={
                    "provider": provider,
                    "model": model,
                },
                messages=messages,
                response_text=None,
                job_metadata=metadata,
                error=str(exc),
            )
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

        raw_response = self._call_chat(messages)

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
                "model": self.llm_settings.alias,
            },
        }
        return result

    async def _stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: Callable[[str], None] | None,
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[str, Any]:
        model = self.llm_settings.alias
        temperature = self.llm_settings.temperature
        max_tokens = self.llm_settings.max_tokens

        def _job() -> tuple[str, Any]:
            stream = self.llm_client.stream_chat(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            def _emit(text: str) -> None:
                if on_chunk:
                    loop.call_soon_threadsafe(on_chunk, text)

            streamed_text, base_summary, raw_parts = common_llm_layer.stream_text_from_iterable(
                stream,
                on_text=_emit,
            )

            summary = common_llm_layer.StreamSummary(
                model=model,
                streamed_text=streamed_text,
                chunk_count=base_summary.chunk_count,
                text_chunk_count=base_summary.text_chunk_count,
                ignored_chunk_count=base_summary.ignored_chunk_count,
                stream_format=base_summary.stream_format,
                final_channel_seen=base_summary.final_channel_seen,
            )

            common_llm_layer.log_stream_finished(
                request={
                    "provider": self.llm_settings.provider,
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
                streamed_text=streamed_text,
                response=None,
                raw_parts=raw_parts,
                summary=summary,
            )

            return streamed_text, None

        return await asyncio.to_thread(_job)

    def _call_chat(self, messages: list[dict[str, str]]) -> Any:
        return self.llm_client.chat(
            model=self.llm_settings.alias,
            messages=messages,
            temperature=self.llm_settings.temperature,
            max_tokens=self.llm_settings.max_tokens,
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


