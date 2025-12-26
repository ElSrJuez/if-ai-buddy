"""Constructs narration job specifications from game memory snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class NarrationJobSpec:
    """Bundle of LLM-ready messages plus metadata for diagnostics."""

    messages: list[dict[str, str]]
    metadata: dict[str, Any]


class NarrationJobBuilder:
    """Formats structured game memory into rich narration prompts."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.system_prompt = config.get("llm_narration_system_prompt", "")
        # Legacy context window knobs (kept for backward compatibility with helper methods).
        self.max_scene_lines = int(config.get("narration_context_max_scene_lines", 4))
        self.max_recent_narrations = int(config.get("narration_context_recent_narrations", 3))
        self.max_recent_scenes = int(config.get("narration_context_recent_scenes", 2))
        self.max_recent_actions = int(config.get("narration_context_recent_actions", 3))
        self.max_recent_inventory = int(config.get("narration_context_recent_inventory", 6))
        self.max_transcript_chars = int(config.get("narration_context_max_transcript_chars", 800))
        self._prompt_spec = self._load_prompt_spec(config)

    def build_job(
        self,
        *,
        memory_context: dict[str, Any],
        trigger: str,
        latest_transcript: str | None,
    ) -> NarrationJobSpec:
        """Create the LLM submission payload for a narration trigger."""
        # Memory-driven prompting: the user prompt is rendered from the configured JSON spec.
        # `latest_transcript` is intentionally not used here.
        user_prompt = self._render_from_spec(self._prompt_spec, memory_context)

        system_prompt = self._format_system_prompt(self.system_prompt, memory_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        metadata = {
            "trigger": trigger,
            "turn_count": memory_context.get("turn_count"),
            "room": memory_context.get("current_room"),
        }

        return NarrationJobSpec(messages=messages, metadata=metadata)

    def _format_system_prompt(self, template: str, memory_context: dict[str, Any]) -> str:
        """Format the system prompt with known safe placeholders.

        This is where we clarify roles without bloating the user prompt.
        Expected placeholders in config may include `{playername}`.
        """
        player = str(memory_context.get("player_name") or "").strip()
        if not player:
            # Keep fail-fast semantics: system prompt placeholders should not depend
            # on missing player context.
            return template
        try:
            return template.format_map(
                _SafeFormatMap(
                    {
                        "playername": player,
                        "player_name": player,
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Failed to format llm_narration_system_prompt: {exc}")

    # ------------------------------------------------------------------
    # JSON prompt spec loader + renderer (memory-driven)
    # ------------------------------------------------------------------

    def _load_prompt_spec(self, config: dict[str, Any]) -> dict[str, Any]:
        if "llm_narration_user_prompt_template_spec_path" not in config:
            raise KeyError(
                "Missing config key 'llm_narration_user_prompt_template_spec_path'"
            )

        root = Path(str(config.get("_project_root") or Path(__file__).resolve().parents[1]))
        raw_path = Path(str(config["llm_narration_user_prompt_template_spec_path"]))
        spec_path = raw_path if raw_path.is_absolute() else (root / raw_path)
        if not spec_path.exists():
            raise FileNotFoundError(f"Narration prompt spec not found: {spec_path}")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            raise ValueError("Narration prompt spec must be a JSON object")
        if spec.get("spec_version") != "1.0":
            raise ValueError(
                "Unsupported narration prompt spec_version "
                f"'{spec.get('spec_version')}'."
            )
        return spec

    def _render_from_spec(self, spec: dict[str, Any], memory_context: dict[str, Any]) -> str:
        # Spec provides default limits, but the effective limits are configuration-driven.
        # This avoids having two competing sources of truth (config.json vs prompt spec).
        limits = self._effective_limits(spec.get("limits") or {})
        value_sources = spec.get("value_sources") or {}
        blocks = spec.get("blocks") or []

        raw_values: dict[str, Any] = {}
        rendered_values: dict[str, str] = {}

        for name, source in value_sources.items():
            if name.startswith("__comment"):
                continue
            raw, rendered = self._extract_value(
                source=source,
                context=memory_context,
                limits=limits,
            )
            raw_values[name] = raw
            rendered_values[name] = rendered

        # Derived lines are evaluated per-block so blocks can remain independent.
        out_lines: list[str] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_lines = list(block.get("lines") or [])
            derived = block.get("derived_lines") or {}

            # Compute derived placeholders into rendered_values.
            derived_values: dict[str, str] = {}
            for placeholder, rule in derived.items():
                derived_values[placeholder] = self._eval_derived_line(
                    rule=rule,
                    raw_values=raw_values,
                    rendered_values={**rendered_values, **derived_values},
                )

            formatted = self._format_block_lines(
                block_lines,
                values={**rendered_values, **derived_values},
            )

            # Decide whether the block is empty (ignoring pure whitespace lines).
            meaningful = [line for line in formatted if line.strip()]
            if not meaningful:
                if block.get("required"):
                    # Keep required blocks, but do not add noise.
                    continue
                continue

            out_lines.extend(formatted)

            # Ensure a single blank line between blocks (compact but readable).
            if out_lines and out_lines[-1].strip() != "":
                out_lines.append("")

        # Trim trailing blanks.
        while out_lines and not out_lines[-1].strip():
            out_lines.pop()

        # Collapse multiple blank lines.
        collapsed: list[str] = []
        for line in out_lines:
            if line.strip() == "" and collapsed and collapsed[-1].strip() == "":
                continue
            collapsed.append(line.rstrip())

        return "\n".join(collapsed).strip() + "\n"

    def _effective_limits(self, spec_limits: dict[str, Any]) -> dict[str, Any]:
        """Return the limits dict used by the prompt renderer.

        The JSON spec can carry sensible defaults, but the canonical knobs live in
        config.json under narration_context_*.
        """
        limits = dict(spec_limits or {})
        # Map config-driven windows onto spec limit keys.
        limits["scene_description_max_lines"] = int(self.max_scene_lines)
        limits["recent_actions_max"] = int(self.max_recent_actions)
        limits["narration_history_max"] = int(self.max_recent_narrations)
        limits["recent_locations_max"] = int(self.max_recent_scenes)
        limits["inventory_max"] = int(self.max_recent_inventory)
        limits["latest_transcript_max_chars"] = int(self.max_transcript_chars)
        return limits

    def _extract_value(
        self,
        *,
        source: dict[str, Any],
        context: dict[str, Any],
        limits: dict[str, Any],
    ) -> tuple[Any, str]:
        kind = str(source.get("kind") or "scalar")
        path = source.get("path")
        raw = self._get_by_path(context, str(path)) if path else None

        if kind == "scalar":
            text = "" if raw is None else str(raw)
            text = text.strip("\n")
            truncate_ref = source.get("truncate_chars")
            if truncate_ref:
                limit = int(self._resolve_ref(truncate_ref, limits))
                text = self._truncate_text(text, limit)
            return raw, text.strip()

        if kind == "list":
            items = raw if isinstance(raw, list) else ([] if raw is None else [raw])
            normalized = self._unique([str(item).strip() for item in items if str(item).strip()])
            take_first = source.get("take_first")
            take_last = source.get("take_last")
            drop_first = source.get("drop_first")
            drop_last = source.get("drop_last")
            if drop_first is not None:
                n = int(self._resolve_ref(drop_first, limits))
                if n > 0:
                    normalized = normalized[n:]
            if drop_last is not None:
                n = int(self._resolve_ref(drop_last, limits))
                if n > 0:
                    normalized = normalized[:-n] if len(normalized) > n else []
            # Apply windowing after drops so "exclude most recent" does not shrink the configured window.
            if take_first is not None:
                n = int(self._resolve_ref(take_first, limits))
                normalized = normalized[:n]
            if take_last is not None:
                n = int(self._resolve_ref(take_last, limits))
                normalized = normalized[-n:] if n > 0 else []

            item_template = source.get("item_template")
            rendered_items: list[str]
            if item_template:
                template = str(item_template)
                rendered_items = [
                    template.format_map(_SafeFormatMap({"item": item})).rstrip()
                    for item in normalized
                ]
                rendered_items = [item for item in rendered_items if item.strip()]
            else:
                rendered_items = list(normalized)

            joiner = str(source.get("join") or "\n")
            return normalized, joiner.join(rendered_items)

        if kind == "list_of_objects":
            records = raw if isinstance(raw, list) else ([] if raw is None else [raw])
            objects: list[dict[str, Any]] = [
                rec for rec in records
                if isinstance(rec, dict)
            ]
            take_first = source.get("take_first")
            take_last = source.get("take_last")
            drop_first = source.get("drop_first")
            drop_last = source.get("drop_last")
            if drop_first is not None:
                n = int(self._resolve_ref(drop_first, limits))
                if n > 0:
                    objects = objects[n:]
            if drop_last is not None:
                n = int(self._resolve_ref(drop_last, limits))
                if n > 0:
                    objects = objects[:-n] if len(objects) > n else []
            # Apply windowing after drops so "exclude most recent" does not shrink the configured window.
            if take_first is not None:
                n = int(self._resolve_ref(take_first, limits))
                objects = objects[:n]
            if take_last is not None:
                n = int(self._resolve_ref(take_last, limits))
                objects = objects[-n:] if n > 0 else []
            template = str(source.get("item_template") or "{item}")
            multiline_indent = str(source.get("multiline_indent") or "")
            rendered_items: list[str] = []
            for obj in objects:
                try:
                    rendered = template.format(**obj).strip()
                except KeyError as exc:
                    raise KeyError(
                        f"Prompt template item_template missing field {exc} in {obj}"
                    )
                if rendered and multiline_indent:
                    rendered = self._indent_multiline(rendered, multiline_indent)
                if rendered:
                    rendered_items.append(rendered)
            rendered_items = self._unique([item for item in rendered_items if item])
            joiner = str(source.get("join") or "\n")
            return objects, joiner.join(rendered_items)

        raise ValueError(f"Unsupported value_sources kind '{kind}'")

    def _eval_derived_line(
        self,
        *,
        rule: dict[str, Any],
        raw_values: dict[str, Any],
        rendered_values: dict[str, str],
    ) -> str:
        # Two equivalent forms are supported:
        # - { "template": "...", "when_present": "x" }
        # - { "cases": [ {when_present...}, {when_empty...} ] }
        cases = rule.get("cases")
        if cases is None:
            cases = [rule]
        if not isinstance(cases, list):
            raise ValueError("derived_lines.cases must be a list")

        for case in cases:
            if not isinstance(case, dict):
                continue
            if self._case_matches(case, raw_values):
                template = str(case.get("template") or "")
                if not template:
                    return ""
                return template.format_map(_SafeFormatMap(rendered_values)).strip("\n")
        return ""

    def _case_matches(self, case: dict[str, Any], raw_values: dict[str, Any]) -> bool:
        if "when_all_present" in case:
            keys = case.get("when_all_present") or []
            return all(self._is_present(raw_values.get(str(k))) for k in keys)
        if "when_present" in case:
            key = str(case.get("when_present"))
            return self._is_present(raw_values.get(key))
        if "when_empty" in case:
            key = str(case.get("when_empty"))
            return not self._is_present(raw_values.get(key))
        # No predicate means unconditional.
        return True

    @staticmethod
    def _is_present(raw: Any) -> bool:
        if raw is None:
            return False
        if isinstance(raw, str):
            return bool(raw.strip())
        if isinstance(raw, list):
            filtered = [item for item in raw if item is not None and str(item).strip()]
            return len(filtered) > 0
        if isinstance(raw, dict):
            return True
        return True

    def _format_block_lines(self, lines: list[str], values: dict[str, str]) -> list[str]:
        formatted: list[str] = []
        for raw_line in lines:
            line = str(raw_line)
            try:
                rendered = line.format(**values)
            except KeyError as exc:
                raise KeyError(f"Prompt block line missing placeholder {exc}: {line}")
            rendered = rendered.rstrip()
            if rendered == "":
                formatted.append("")
            else:
                formatted.append(rendered)
        return formatted

    @staticmethod
    def _get_by_path(obj: Any, path: str) -> Any:
        current: Any = obj
        for token in path.split("."):
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(token)
                continue
            if isinstance(current, list):
                try:
                    idx = int(token)
                except Exception:
                    return None
                if idx < 0 or idx >= len(current):
                    return None
                current = current[idx]
                continue
            # Fallback for objects
            if hasattr(current, token):
                current = getattr(current, token)
            else:
                return None
        return current

    @staticmethod
    def _resolve_ref(ref: Any, limits: dict[str, Any]) -> Any:
        if isinstance(ref, (int, float)):
            return ref
        if isinstance(ref, str):
            text = ref.strip()
            if text.startswith("limits."):
                key = text.split(".", 1)[1]
                return limits.get(key)
            return text
        return ref

    def _build_template_values(
        self,
        context: dict[str, Any],
        latest_transcript: str | None,
    ) -> dict[str, str]:
        scene = context.get("current_scene") or {}
        recent_summaries = context.get("recent_scene_summaries") or []
        state = context.get("player_state") or {}

        latest_text = self._truncate_text(latest_transcript.strip(), self.max_transcript_chars) if latest_transcript else "(no recent transcript)"
        scene_summary = self._describe_scene(scene)
        delta_highlights = self._format_delta(scene, latest_transcript)
        narration_history = self._format_history(
            self._unique(scene.get("narrations") or []),
            self.max_recent_narrations,
        )
        inventory_summary = self._format_labeled_list(
            "Inventory",
            self._unique(state.get("inventory") or []),
            self.max_recent_inventory,
        )
        recent_locations = self._format_recent_locations(recent_summaries)

        return {
            "latest_transcript": latest_text,
            "scene_summary": scene_summary,
            "delta_highlights": delta_highlights,
            "narration_history": narration_history,
            "inventory_summary": inventory_summary,
            "recent_locations": recent_locations,
        }

    def _describe_scene(self, scene: dict[str, Any]) -> str:
        room_name = scene.get("room_name") or "Unknown"
        desc_lines = scene.get("description_lines") or []
        description = self._join_lines(desc_lines[-self.max_scene_lines :])
        visit_count = scene.get("visit_count")
        visit_text = f" (visits: {visit_count})" if visit_count else ""
        parts = [f"{room_name}{visit_text}"]
        if description:
            parts.append(description)
        return "\n".join(parts)

    def _format_delta(self, scene: dict[str, Any], latest_transcript: str | None) -> str:
        highlights: list[str] = []
        transcript_delta = self._extract_transcript_delta(latest_transcript)
        if transcript_delta:
            highlights.append("Transcript delta: " + transcript_delta)

        items = self._format_labeled_list(
            "Visible",
            self._unique(scene.get("scene_items") or []),
            self.max_recent_inventory,
        )
        if items:
            highlights.append(items)

        nearby = self._format_nearby_delta(scene)
        if nearby:
            highlights.append(nearby)

        npcs = self._format_labeled_list(
            "NPCs",
            self._unique(scene.get("npcs") or []),
        )
        if npcs:
            highlights.append(npcs)

        actions = self._format_actions(scene.get("action_records") or [])
        if actions:
            highlights.append("Recent actions:\n" + actions)

        return "\n".join(highlights)

    def _format_nearby_delta(self, scene: dict[str, Any]) -> str:
        visibles = set(self._unique(scene.get("scene_items") or []))
        current = self._unique(scene.get("current_items") or [])
        extras = [item for item in current if item not in visibles]
        if not extras:
            return ""
        return "Nearby: " + ", ".join(extras[: self.max_recent_inventory])

    def _extract_transcript_delta(self, transcript: str | None) -> str:
        if not transcript:
            return ""
        body = transcript.strip().splitlines()
        body = [line for line in body if line.strip()]
        trimmed = " ".join(body[-4:])
        return self._truncate_text(trimmed, self.max_transcript_chars // 2)

    def _format_actions(self, action_records: Iterable[Any]) -> str:
        deduped: list[str] = []
        seen: set[tuple[str, str | None]] = set()
        for record in list(action_records)[-self.max_recent_actions :]:
            if isinstance(record, dict):
                command = record.get("command")
                result = record.get("result")
            else:
                command = getattr(record, "command", None)
                result = getattr(record, "result", None)
            if not command:
                continue
            key = (command, result)
            if key in seen:
                continue
            seen.add(key)
            if result:
                deduped.append(f"- {command}: {result}")
            else:
                deduped.append(f"- {command}")
        return "\n".join(deduped)

    def _format_history(self, narrations: list[str], limit: int) -> str:
        if not narrations:
            return ""
        trimmed = narrations[-limit:]
        return "\n".join(trimmed)

    def _format_recent_locations(self, summaries: list[dict[str, Any]]) -> str:
        if not summaries:
            return ""
        trimmed = summaries[: self.max_recent_scenes]
        lines: list[str] = []
        for summary in trimmed:
            name = summary.get("room_name", "Unknown")
            visit = summary.get("visit_count")
            desc = self._join_lines((summary.get("description_lines") or [])[-self.max_scene_lines :])
            segment = f"- {name}"
            if visit:
                segment += f" (visits: {visit})"
            if desc:
                segment += f": {desc}"
            lines.append(segment)
        return "\n".join(lines)

    def _format_labeled_list(
        self,
        label: str,
        items: list[str],
        limit: int | None = None,
    ) -> str:
        if not items:
            return ""
        subset = items if limit is None else items[:limit]
        return f"{label}: " + ", ".join(subset)

    @staticmethod
    def _unique(items: Iterable[Any]) -> list[Any]:
        seen: set[Any] = set()
        ordered: list[Any] = []
        for item in items:
            if not item:
                continue
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    @staticmethod
    def _join_lines(lines: Iterable[str]) -> str:
        merged = [line.strip() for line in lines if line]
        return "\n".join(merged)

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _indent_multiline(text: str, indent: str) -> str:
        """Indent all lines after the first with the provided prefix."""
        if not text or "\n" not in text:
            return text
        lines = text.splitlines()
        if not lines:
            return text
        out = [lines[0]]
        for line in lines[1:]:
            out.append(indent + line)
        return "\n".join(out)


class _SafeFormatMap(dict):
    """A formatting map that returns empty string for missing keys.

    This prevents accidental '{missing}' placeholders from crashing derived lines
    when the relevant block is otherwise empty, while block-level placeholders
    still fail fast via explicit KeyError handling in _format_block_lines.
    """

    def __missing__(self, key: str) -> str:
        return ""


__all__ = ["NarrationJobBuilder", "NarrationJobSpec"]
