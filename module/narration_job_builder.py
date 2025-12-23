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

    def build_job(
        self,
        *,
        memory_context: dict[str, Any],
        trigger: str,
        latest_transcript: str | None,
    ) -> NarrationJobSpec:
        """Create the LLM submission payload for a narration trigger."""
        sections: list[str] = []

        if latest_transcript:
            sections.append(
                "Latest engine response:\n" + latest_transcript.strip()
            )

        current_scene_section = self._format_current_scene(memory_context)
        if current_scene_section:
            sections.append(current_scene_section)

        history_section = self._format_recent_history(memory_context)
        if history_section:
            sections.append(history_section)

        inventory_section = self._format_inventory(memory_context)
        if inventory_section:
            sections.append(inventory_section)

        narrations_section = self._format_previous_narrations(memory_context)
        if narrations_section:
            sections.append(narrations_section)

        game_log = "\n\n".join(section for section in sections if section)
        user_prompt = self.user_template.replace("{game_log}", game_log)

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

    def _format_current_scene(self, context: dict[str, Any]) -> str:
        scene = (context.get("current_scene") or {})
        room_name = scene.get("room_name")
        if not room_name:
            return ""

        lines = scene.get("description_lines") or []
        description = self._join_lines(lines[-self.max_scene_lines :])
        items = scene.get("scene_items") or []
        current_items = scene.get("current_items") or []
        npcs = scene.get("npcs") or []
        actions = scene.get("action_records") or []

        parts: list[str] = [f"Current scene: {room_name}"]
        if description:
            parts.append(description)
        if items:
            parts.append("Visible items: " + ", ".join(items[: self.max_recent_inventory]))
        if current_items:
            parts.append(
                "Nearby objects: " + ", ".join(current_items[: self.max_recent_inventory])
            )
        if npcs:
            parts.append("NPCs present: " + ", ".join(npcs))
        if actions:
            formatted_actions = self._format_actions(actions)
            if formatted_actions:
                parts.append("Recent actions:\n" + formatted_actions)
        return "\n".join(parts)

    def _format_recent_history(self, context: dict[str, Any]) -> str:
        summaries = context.get("recent_scene_summaries") or []
        if not summaries:
            return ""
        trimmed = summaries[: self.max_recent_scenes]
        sections: list[str] = []
        for summary in trimmed:
            name = summary.get("room_name", "Unknown")
            desc = self._join_lines(
                (summary.get("description_lines") or [])[-self.max_scene_lines :]
            )
            visit = summary.get("visit_count")
            line = f"Scene {name} (visits: {visit or 0})"
            if desc:
                line += f"\n{desc}"
            sections.append(line)
        if not sections:
            return ""
        return "Recent locations:\n" + "\n\n".join(sections)

    def _format_previous_narrations(self, context: dict[str, Any]) -> str:
        scene = context.get("current_scene") or {}
        narrations = scene.get("narrations") or []
        if not narrations:
            return ""
        trimmed = narrations[-self.max_recent_narrations :]
        return "Prior narrator lines:\n" + "\n".join(trimmed)

    def _format_inventory(self, context: dict[str, Any]) -> str:
        state = context.get("player_state") or {}
        inventory = state.get("inventory") or []
        if not inventory:
            return ""
        trimmed = inventory[: self.max_recent_inventory]
        return "Inventory highlights: " + ", ".join(trimmed)

    def _format_actions(self, action_records: Iterable[Any]) -> str:
        formatted: list[str] = []
        for record in list(action_records)[-self.max_recent_actions :]:
            if isinstance(record, dict):
                command = record.get("command")
                result = record.get("result")
            else:
                command = getattr(record, "command", None)
                result = getattr(record, "result", None)
            if not command:
                continue
            if result:
                formatted.append(f"- {command}: {result}")
            else:
                formatted.append(f"- {command}")
        return "\n".join(formatted)

    @staticmethod
    def _join_lines(lines: Iterable[str]) -> str:
        merged = [line.strip() for line in lines if line]
        return "\n".join(merged)


__all__ = ["NarrationJobBuilder", "NarrationJobSpec"]
