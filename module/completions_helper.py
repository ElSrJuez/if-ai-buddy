"""LLM completion helper with schema-guided structured output."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, create_model

from module import my_logging


class CompletionsHelper:
    """
    Orchestrates LLM calls with schema-enforced output.
    
    Supports both OpenAI and Foundry backends.
    """

    def __init__(
        self,
        config: dict[str, Any],
        response_schema: dict[str, Any],
        llm_client: Any,
    ) -> None:
        """
        Initialize the completions helper.
        
        Args:
            config: Configuration dict with llm_provider, llm_model_alias, llm_temperature, etc.
            response_schema: JSON schema dict for structured output.
            llm_client: Initialized OpenAI client or Foundry local client.
        """
        self.config = config
        self.response_schema = response_schema
        self.llm_client = llm_client

        # Validate required config keys
        required = ["llm_provider", "system_prompt", "user_prompt_template"]
        missing = [k for k in required if k not in config]
        if missing:
            raise ValueError(f"Missing config keys: {', '.join(missing)}")

    def run(
        self,
        transcript_chunk: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build prompt, call LLM, and return structured result.
        
        Args:
            transcript_chunk: Latest game transcript snippet.
            context: Optional dict with episodic/state memory (embedded in user message).
        
        Returns:
            Dict with keys:
                - payload: Parsed JSON response (or fallback if parse fails)
                - raw_response: SDK response object
                - diagnostics: {latency, tokens, model}
        """
        start_time = time.time()

        # Build prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(transcript_chunk, context)

        try:
            # Call LLM
            if self.config.get("llm_provider") == "openai":
                raw_response = self._call_openai(system_prompt, user_prompt)
            else:
                # Foundry local or other provider
                raw_response = self._call_foundry(system_prompt, user_prompt)

            # Parse response
            payload = self._parse_response(raw_response)

            # Compute diagnostics
            latency = time.time() - start_time
            tokens = self._extract_token_count(raw_response)
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

            # Log completion
            if my_logging.is_debug_enabled():
                my_logging.log_completion_event({
                    "model": model,
                    "latency": latency,
                    "tokens": tokens,
                    "payload_keys": list(payload.keys()) if isinstance(payload, dict) else [],
                })

            return result

        except Exception as exc:
            my_logging.system_debug(f"Completions error: {exc}")
            # Return minimal fallback
            latency = time.time() - start_time
            return {
                "payload": {
                    "narration": "The game continues...",
                    "game_intent": "Unknown",
                    "game_meta_intent": "Unknown",
                    "hidden_next_command": "look",
                    "hidden_next_command_confidence": 0,
                },
                "raw_response": None,
                "diagnostics": {
                    "latency_seconds": latency,
                    "tokens": 0,
                    "model": self.config.get("llm_model_alias", "unknown"),
                    "error": str(exc),
                },
            }

    # -------- Private helpers --------

    def _build_system_prompt(self) -> str:
        """Build system prompt, interpolating schema as JSON string."""
        template = self.config.get("system_prompt", "")
        schema_json = json.dumps(self.response_schema)
        return template.replace("{response_schema}", schema_json)

    def _build_user_prompt(
        self,
        transcript_chunk: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Build user prompt with game log and optional context."""
        template = self.config.get("user_prompt_template", "")
        game_log = transcript_chunk
        
        # Add context if provided
        if context:
            context_str = json.dumps(context, indent=2)
            game_log = f"Context:\n{context_str}\n\nLatest:\n{transcript_chunk}"
        
        return template.replace("{game_log}", game_log)

    def _call_openai(self, system_prompt: str, user_prompt: str) -> Any:
        """Call OpenAI API with schema enforcement."""
        # Ensure client is OpenAI instance
        if not isinstance(self.llm_client, OpenAI):
            raise ValueError("OpenAI provider requires OpenAI client instance")

        # For now, use regular chat completion without strict schema
        # (strict schema requires pydantic model, which is complex to generate)
        response = self.llm_client.chat.completions.create(
            model=self.config.get("llm_model_alias", "gpt-4"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.get("llm_temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 1000),
        )
        return response

    def _call_foundry(self, system_prompt: str, user_prompt: str) -> Any:
        """Call Foundry local LLM with schema enforcement."""
        # Foundry local API: chat endpoint with schema parameter
        response = self.llm_client.chat(
            model=self.config.get("llm_model_alias", "Phi-3.5-mini-instruct-cuda-gpu"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema=self.response_schema,
            temperature=self.config.get("llm_temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 1000),
        )
        return response

    def _parse_response(self, raw_response: Any) -> dict[str, Any]:
        """
        Parse LLM response into validated JSON dict.
        
        Handles:
        - Direct JSON (OpenAI with schema)
        - JSON in code fences (fallback)
        - Raw JSON string
        """
        if raw_response is None:
            return {"narration": "Error: no response from LLM"}

        # Try to extract JSON content
        content = None
        if hasattr(raw_response, "choices") and raw_response.choices:
            # OpenAI format
            choice = raw_response.choices[0]
            if hasattr(choice, "message"):
                content = choice.message.content
            elif hasattr(choice, "parsed"):
                # Already parsed by OpenAI
                if hasattr(choice.parsed, "model_dump"):
                    return choice.parsed.model_dump()
                else:
                    return dict(choice.parsed) if choice.parsed else {}
        elif isinstance(raw_response, dict):
            # Foundry might return dict directly
            return raw_response
        elif hasattr(raw_response, "content"):
            # Direct content attribute
            content = raw_response.content

        if not content:
            return {"narration": "Error: no content in response"}

        # Try to parse as JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from code fences
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Fallback: return raw content as narration
        my_logging.system_debug(f"Failed to parse JSON response: {content[:200]}")
        return {"narration": content[:500]}

    def _extract_token_count(self, raw_response: Any) -> int:
        """Extract token count from response."""
        if raw_response is None:
            return 0

        # OpenAI format
        if hasattr(raw_response, "usage"):
            if hasattr(raw_response.usage, "total_tokens"):
                return raw_response.usage.total_tokens

        # Foundry might have different format
        if isinstance(raw_response, dict) and "usage" in raw_response:
            usage = raw_response["usage"]
            if isinstance(usage, dict):
                return usage.get("total_tokens", 0)

        return 0


__all__ = ["CompletionsHelper"]
