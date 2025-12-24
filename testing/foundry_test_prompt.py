"""Minimal streaming test against Foundry Local using gpt-oss-20b-cuda-gpu."""

from __future__ import annotations

import argparse

import openai
from foundry_local import FoundryLocalManager

from module import my_config, my_logging


def stream_prompt(prompt: str, alias: str = "gpt-oss-20b-cuda-gpu") -> None:
    """Stream responses from the local Foundry model specified by alias."""

    manager = FoundryLocalManager(alias)
    client = openai.OpenAI(base_url=manager.endpoint, api_key=manager.api_key)
    model_id = manager.get_model_info(alias).id

    stream = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )

    print("Streaming response:")
    for chunk in stream:
        content = _extract_chunk_text(chunk)
        if content:
            print(content, end="", flush=True)


def _extract_chunk_text(chunk: openai.openai_object.OpenAIObject) -> str | None:
    """Safely pull text out of a streaming response chunk."""

    for choice in getattr(chunk, "choices", []):
        delta = getattr(choice, "delta", None)
        if delta is None:
            continue
        content = getattr(delta, "content", None)
        if content:
            return content
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Foundry Local streaming test")
    parser.add_argument(
        "--debug",
        "--DEBUG",
        dest="debug",
        action="store_true",
        help="Enable DEBUG-tier logging (writes full request/response JSONL traces)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model alias from config (or defaults to gpt-oss-20b-cuda-gpu)",
    )
    parser.add_argument(
        "--prompt",
        default="Tell me about Foundry Local in a couple of sentences.",
        help="Prompt to send",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = my_config.load_config()
    if args.debug:
        my_logging.init(player_name=str(config.get("player_name", "Adventurer")), config=config)

    alias = args.model or str(config.get("llm_model_alias", "gpt-oss-20b-cuda-gpu"))
    stream_prompt(args.prompt, alias=alias)


if __name__ == "__main__":
    main()
