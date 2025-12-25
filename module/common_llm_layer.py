"""Common LLM streaming utilities.

Goals
- One canonical place to extract text from streaming chunks/events.
- Handle non-text chunks gracefully (ignore for UI, count/log for debugging).
- Emit a dedicated JSONL trace at end-of-stream:
  - DEBUG: full request + full response/chunks (best-effort serialization)
  - non-DEBUG: minimal record (streamed_text only)

This module intentionally does not hide failures or fabricate API responses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from module import my_logging


@dataclass(frozen=True)
class StreamSummary:
    model: str
    streamed_text: str
    chunk_count: int
    text_chunk_count: int
    ignored_chunk_count: int
    stream_format: str | None = None
    final_channel_seen: bool | None = None


def extract_stream_text(part: Any) -> str | None:
    """Extract user-visible text from a streaming object.

    Supports two shapes used by the OpenAI Python SDK:
    1) Chat Completions stream chunks: chunk.choices[0].delta.content
    2) Chat Completions stream helper events: event.type == 'content.delta' with event.content

    Returns None for non-text deltas (role/tool calls/etc.).
    """

    if part is None:
        return None

    # Responses API event stream: event.type == 'response.output_text.delta'
    # (the canonical textual delta for Responses streaming)
    event_type = getattr(part, "type", None)
    if event_type == "response.output_text.delta":
        delta = getattr(part, "delta", None)
        return _to_plain_text(delta)

    # Event-style chat.completions.stream helper (helpers.md): event.type == 'content.delta'
    event_type = getattr(part, "type", None)
    if event_type == "content.delta":
        content = getattr(part, "content", None)
        return _to_plain_text(content)

    # Chunk-style chat.completions.create(..., stream=True)
    choices = getattr(part, "choices", None)
    if choices:
        try:
            choice0 = choices[0]
            delta = getattr(choice0, "delta", None)
            if delta is None:
                return None
            content = getattr(delta, "content", None)
            return _to_plain_text(content)
        except Exception:
            return None

    # Dict fallbacks (only for logs/defensive parsing)
    if isinstance(part, Mapping):
        if part.get("type") == "response.output_text.delta":
            delta_text = part.get("delta")
            return _to_plain_text(delta_text)
        if part.get("type") == "content.delta":
            delta_text = part.get("content")
            return _to_plain_text(delta_text)
        choices = part.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta") if isinstance(choices[0], Mapping) else None
            if isinstance(delta, Mapping):
                content = delta.get("content")
                return _to_plain_text(content)

    return None


# -----------------------------------------------------------------------------
# Harmony filtering (stateful)
# -----------------------------------------------------------------------------

# OpenAI Harmony message format (docs/format.md):
# <|start|>{header}<|message|>{content}<|end|>
# Example output:
# <|start|>assistant<|channel|>analysis<|message|>...<|end|>
# <|start|>assistant<|channel|>final<|message|>...<|return|>

_H_START = "<|start|>"
_H_END = "<|end|>"
_H_MESSAGE = "<|message|>"
_H_CHANNEL = "<|channel|>"
_H_RETURN = "<|return|>"
_H_CALL = "<|call|>"

_H_FINAL_HEADER = "<|start|>assistant<|channel|>final<|message|>"


class HarmonyFinalOnlyFilter:
    """Emit only the assistant's `final` channel content.

    This is intentionally strict: analysis/commentary are never surfaced.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_final = False

    @property
    def final_channel_seen(self) -> bool:
        return self._in_final

    def feed(self, text: str) -> str | None:
        if not text:
            return None
        self._buffer += text

        if not self._in_final:
            idx = self._buffer.find(_H_FINAL_HEADER)
            if idx == -1:
                # Keep buffer bounded: if it grows too large without final, trim oldest.
                if len(self._buffer) > 16_384:
                    self._buffer = self._buffer[-8_192:]
                return None
            # Jump to final content
            self._buffer = self._buffer[idx + len(_H_FINAL_HEADER) :]
            self._in_final = True

        # In final: emit whatever new content is present up to a stop token
        stop_at = self._find_first_stop(self._buffer)
        if stop_at is None:
            out = self._buffer
            self._buffer = ""
            return out or None

        out = self._buffer[:stop_at]
        # Consume everything through the stop token
        self._buffer = self._buffer[stop_at:]
        # After a stop token, we are done; prevent any further output.
        self._buffer = ""
        return out or None

    def _find_first_stop(self, text: str) -> int | None:
        stops = [
            text.find(_H_RETURN),
            text.find(_H_END),
            text.find(_H_CALL),
        ]
        stops = [i for i in stops if i != -1]
        return min(stops) if stops else None


def _should_use_harmony_filter(sample: str) -> bool:
    # Cheap detection: Harmony special tokens.
    if not sample:
        return False
    return _H_START in sample or _H_CHANNEL in sample


def _to_plain_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        parts = [_to_plain_text(v) for v in value]
        parts = [p for p in parts if p]
        return "".join(parts) if parts else None
    if isinstance(value, Mapping):
        for key in ("text", "content", "value"):
            if key in value:
                text = _to_plain_text(value[key])
                if text:
                    return text
        return str(value)
    if hasattr(value, "text"):
        return _to_plain_text(getattr(value, "text"))
    if hasattr(value, "content"):
        return _to_plain_text(getattr(value, "content"))
    return str(value)


def stream_text_from_iterable(
    stream: Iterable[Any],
    *,
    on_text: Callable[[str], None] | None = None,
) -> tuple[str, StreamSummary, list[Any]]:
    """Consume a stream, emitting only text deltas.

    Returns (full_text, summary, raw_parts).
    raw_parts are retained only for optional debug logging.
    """

    raw_parts: list[Any] = []
    chunks: list[str] = []

    chunk_count = 0
    text_chunk_count = 0

    harmony_filter: HarmonyFinalOnlyFilter | None = None

    for part in stream:
        raw_parts.append(part)
        chunk_count += 1

        raw_text = extract_stream_text(part)
        if not raw_text:
            continue

        if harmony_filter is None and _should_use_harmony_filter(raw_text):
            harmony_filter = HarmonyFinalOnlyFilter()

        out_text = harmony_filter.feed(raw_text) if harmony_filter else raw_text
        if out_text:
            text_chunk_count += 1
            chunks.append(out_text)
            if on_text:
                on_text(out_text)

    full_text = "".join(chunks)
    ignored = chunk_count - text_chunk_count

    stream_format: str | None = "harmony" if harmony_filter is not None else None
    final_seen: bool | None = harmony_filter.final_channel_seen if harmony_filter is not None else None

    # model is unknown at this layer unless caller provides; fill with placeholder.
    summary = StreamSummary(
        model="unknown",
        streamed_text=full_text,
        chunk_count=chunk_count,
        text_chunk_count=text_chunk_count,
        ignored_chunk_count=ignored,
        stream_format=stream_format,
        final_channel_seen=final_seen,
    )
    return full_text, summary, raw_parts


def log_stream_finished(
    *,
    request: Mapping[str, Any],
    streamed_text: str,
    response: Any = None,
    raw_parts: list[Any] | None = None,
    summary: StreamSummary | None = None,
) -> None:
    """Write a single JSONL entry describing the completed stream.

    - DEBUG: includes request, response, raw_parts (best-effort serialization)
    - non-DEBUG: includes minimal keys + streamed_text
    """

    logger = my_logging.get_common_llm_logger()

    model = str(request.get("model", "unknown"))
    entry: dict[str, Any] = {
        "timestamp": _timestamp(),
        "model": model,
        "streamed_text": streamed_text,
    }

    if summary is not None:
        entry["stream"] = {
            "chunk_count": summary.chunk_count,
            "text_chunk_count": summary.text_chunk_count,
            "ignored_chunk_count": summary.ignored_chunk_count,
        }

    if my_logging.is_debug_enabled():
        entry["_debug_full_event"] = True
        entry["request"] = to_jsonable(request)
        entry["response"] = to_jsonable(response)
        if raw_parts is not None:
            # Debug objective: prove what the stream contained.
            # Keep the full extracted raw text deltas (pre-filter) and a small preview of raw events.
            extracted = [extract_stream_text(part) for part in raw_parts]
            entry["raw_text_deltas"] = extracted
            entry["raw_parts_preview"] = {
                "count": len(raw_parts),
                "first": to_jsonable(raw_parts[0]) if raw_parts else None,
                "last": to_jsonable(raw_parts[-1]) if raw_parts else None,
            }

    logger.info(json.dumps(entry, ensure_ascii=False))
    for handler in logger.handlers:
        handler.flush()


# -----------------------------------------------------------------------------
# Simple interaction history (compact, query-friendly)
# -----------------------------------------------------------------------------


def log_simple_interaction_history(
    *,
    request: Mapping[str, Any],
    messages: list[Mapping[str, Any]] | None,
    response_text: str | None,
    job_metadata: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Write a plain-text prompt/response record for later analysis.

    Objective: capture what we actually send to the LLM engine (messages) and the
    resulting text (as received/streamed) without adding any JSON structure.
    """

    logger = my_logging.get_common_llm_simple_interaction_logger()

    model = str(request.get("model", "unknown"))
    provider = str(request.get("provider", "unknown"))

    lines: list[str] = []
    lines.append("----- LLM SIMPLE INTERACTION -----")
    lines.append(f"timestamp: {_timestamp()}")
    lines.append(f"provider: {provider}")
    lines.append(f"model: {model}")

    if job_metadata:
        lines.append("job_metadata:")
        for k, v in job_metadata.items():
            lines.append(f"  {k}: {v}")

    if error:
        lines.append(f"error: {error}")

    lines.append("")
    lines.append("PROMPT (exact messages):")
    if not messages:
        lines.append("(no messages)")
    else:
        for idx, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            lines.append(f"[message {idx}] role={role}")
            # Intentionally do not serialize/pretty-print; keep raw text.
            lines.append(str(content) if content is not None else "")
            lines.append("")

    lines.append("RESPONSE (exact text):")
    if response_text is None:
        lines.append("(no response_text)")
    else:
        lines.append(response_text)
    lines.append("----- END -----")
    lines.append("")

    logger.info("\n".join(lines))
    for handler in logger.handlers:
        handler.flush()


def to_jsonable(obj: Any) -> Any:
    """Best-effort conversion to JSON-serializable types for logging."""

    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]

    # openai-python models generally expose model_dump
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return to_jsonable(obj.model_dump())
        except Exception:
            pass
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            return to_jsonable(obj.dict())
        except Exception:
            pass
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        try:
            return to_jsonable(obj.to_dict())
        except Exception:
            pass

    if hasattr(obj, "__dict__"):
        try:
            return to_jsonable(vars(obj))
        except Exception:
            pass

    try:
        return str(obj)
    except Exception:
        return repr(obj)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
