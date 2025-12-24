"""Minimal streaming test against Foundry Local using gpt-oss-20b-cuda-gpu."""

from __future__ import annotations

import openai
from foundry_local import FoundryLocalManager


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


def main() -> None:
    prompt = "Tell me about Foundry Local in a couple of sentences."  # simple test prompt
    stream_prompt(prompt)


if __name__ == "__main__":
    main()
