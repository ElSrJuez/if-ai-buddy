"""Quick smoke test for the configured LLM provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from openai import BadRequestError

from module import my_config
from module.llm_factory_FoundryLocal import create_llm_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM smoke test")
    parser.add_argument(
        "--prompt",
        default="Summarize the feeling of finding a mysterious object in 1 sentence.",
        help="User prompt to send",
    )
    parser.add_argument(
        "--model",
        help="Override model alias from config",
    )
    parser.add_argument(
        "--use-schema",
        action="store_true",
        help="Attach the configured narration schema as response_format",
    )
    parser.add_argument(
        "--schema-key",
        default="ai_engine_schema_path",
        help="Config key pointing to the schema path",
    )
    return parser.parse_args()


def load_schema(config: dict[str, object], key: str) -> dict | None:
    path_value = config.get(key)
    if not path_value:
        return None
    schema_path = Path(str(path_value))
    if not schema_path.is_absolute():
        schema_path = Path(__file__).resolve().parents[1] / schema_path
    if not schema_path.exists():
        return None
    return json.loads(schema_path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    config = my_config.load_config()
    llm = create_llm_client(config)

    messages = [
        {"role": "system", "content": "You are a concise narrator."},
        {"role": "user", "content": args.prompt},
    ]

    request_kwargs = {
        "model": args.model or config.get("llm_model_alias"),
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 128,
    }

    if args.use_schema:
        schema = load_schema(config, args.schema_key)
        if schema:
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "narration_schema",
                    "schema": schema,
                    "strict": True,
                },
            }
        else:
            print("[warn] --use-schema enabled but schema file missing", file=sys.stderr)

    print("Requesting LLM with:")
    print(json.dumps({k: v for k, v in request_kwargs.items() if k != "messages"}, indent=2))

    try:
        provider = config.get("llm_provider")
        temperature = request_kwargs["temperature"]
        max_tokens = request_kwargs["max_tokens"]
        model = request_kwargs["model"]
        if provider == "foundry" and hasattr(llm, "stream_chat"):
            response = _stream_foundry(
                llm,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            response = _stream_openai(
                llm,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
    except BadRequestError as exc:
        print("LLM call failed with 400 Bad Request", file=sys.stderr)
        print("Response headers:", file=sys.stderr)
        print(exc.response.headers, file=sys.stderr)
        try:
            body = exc.response.json()
        except Exception:  # noqa: BLE001
            body = exc.response.text
        print("Response body:", file=sys.stderr)
        print(body, file=sys.stderr)
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"LLM call failed: {exc}", file=sys.stderr)
        raise

    def _make_serializable(obj):
        """Recursively convert objects to JSON-serializable Python types."""
        # Primitives
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        # Containers
        if isinstance(obj, dict):
            return {k: _make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_make_serializable(v) for v in obj]
        # Common library methods
        if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
            return _make_serializable(obj.to_dict())
        if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
            return _make_serializable(obj.dict())
        # Fallback to __dict__ for simple objects
        if hasattr(obj, "__dict__"):
            return _make_serializable(vars(obj))
        # Last resort: string representation
        try:
            return str(obj)
        except Exception:
            return repr(obj)

    printable = _make_serializable(response)
    print(json.dumps(printable, indent=2))


def _extract_stream_chunk(event: Any) -> str | None:
    """Extract text from either chat.completions streaming chunks or responses streaming events."""
    if event is None:
        return None

    # OpenAI Responses API streaming events: event.type == 'response.output_text.delta'
    event_type = getattr(event, "type", None) if not isinstance(event, dict) else event.get("type")
    if event_type == "response.output_text.delta":
        delta = getattr(event, "delta", None) if not isinstance(event, dict) else event.get("delta")
        return str(delta) if delta else None

    # OpenAI Chat Completions streaming chunks: chunk.choices[0].delta.content
    choices = getattr(event, "choices", None) if not isinstance(event, dict) else event.get("choices")
    if not choices:
        return None

    first = choices[0] if isinstance(choices, list) else None
    if first is None:
        return None

    delta = getattr(first, "delta", None) if not isinstance(first, dict) else first.get("delta")
    if delta is None:
        return None

    content = getattr(delta, "content", None) if not isinstance(delta, dict) else delta.get("content")
    return str(content) if content else None


def _stream_foundry(
    adapter: Any,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> Any:
    stream = adapter.stream_chat(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    chunks: list[str] = []
    for event in stream:
        chunk = _extract_stream_chunk(event)
        if chunk:
            print(chunk, end="", flush=True)
            chunks.append(chunk)
    print()

    if not chunks:
        raise RuntimeError("Foundry stream produced no chunks")

    # Explicitly return the streamed text (do not pretend this is a full API response).
    return {
        "model": model,
        "streamed_text": "".join(chunks),
    }


def _stream_openai(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> Any:
    stream = client.responses.stream(
        model=model,
        input={"messages": messages},
        temperature=temperature,
        max_output_tokens=max_tokens,
        max_tokens=max_tokens,
    )
    chunks: list[str] = []
    final_response: Any = None
    with stream as events:
        for event in events:
            chunk = _extract_stream_chunk(event)
            if chunk:
                print(chunk, end="", flush=True)
                chunks.append(chunk)
        if hasattr(events, "get_final_response"):
            final_response = events.get_final_response()
    print()
    if final_response is None:
        if not chunks:
            raise RuntimeError("OpenAI stream produced no chunks")
        final_response = {
            "choices": [
                {
                    "message": {"content": "".join(chunks)},
                }
            ],
            "model": model,
        }
    return final_response


if __name__ == "__main__":
    main()
