"""Quick smoke test for the configured LLM provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
        response = llm.chat(**request_kwargs)
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


if __name__ == "__main__":
    main()
