"""Constructs narration job specifications from game memory snapshots."""

from __future__ import annotations

from dataclasses import dataclass
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
        self.user_template = config.get(
            "llm_narration_user_prompt_template",
            "{game_log}",
        )
        self.max_scene_lines = int(config.get("narration_context_max_scene_lines", 4))
        self.max_recent_narrations = int(
            config.get("narration_context_recent_narrations", 3)
        )
        self.max_recent_scenes = int(
            config.get("narration_context_recent_scenes", 2)
        )
        self.max_recent_actions = int(
            config.get("narration_context_recent_actions", 3)
        )
        self.max_recent_inventory = int(
            config.get("narration_context_recent_inventory", 6)
        )
        self.max_transcript_chars = int(
            config.get("narration_context_max_transcript_chars", 800)
        )

    def build_job(
        self,
        *,
        memory_context: dict[str, Any],
        trigger: str,
        latest_transcript: str | None,
    ) -> NarrationJobSpec:
        """Create the LLM submission payload for a narration trigger."""
        values = self._build_template_values(memory_context, latest_transcript)
        user_prompt = self.user_template.format(**values)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        metadata = {
            "trigger": trigger,
            "turn_count": memory_context.get("turn_count"),
            "room": memory_context.get("current_room"),
        }

        return NarrationJobSpec(messages=messages, metadata=metadata)

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


__all__ = ["NarrationJobBuilder", "NarrationJobSpec"]
