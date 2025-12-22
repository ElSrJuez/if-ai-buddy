"""Game memory store using TinyDB for persistent episodic and state tracking.

Responsibilities:
  - Initialize and maintain a `Scene` for each unique room.
  - Accumulate non-duplicative description lines, items, NPCs, actions, and narrations.
  - Persist Scene objects to TinyDB with serialization/deserialization.
  - Provide `get_context_for_prompt()` to supply memory context to LLM.
  - Expose `reset()` to clear memory on session restart or player rename.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from tinydb import TinyDB, Query

from module import my_logging
from module.game_engine_heuristics import EngineFacts


def _extract_action_result(description: str | None, command: str, default_room: str) -> str:
    """Extract the outcome of a command from the description.
    
    For movement commands, returns the room name.
    For other commands, returns the first line of description (the direct result).
    """
    if not description:
        return default_room
    
    # Movement verbs typically result in a room name
    movement_verbs = {"go", "walk", "move", "west", "east", "north", "south", "up", "down", "climb", "enter", "leave"}
    cmd_lower = command.lower().split()[0]  # Get first word of command
    
    if cmd_lower in movement_verbs:
        return default_room
    
    # For non-movement, return first non-empty line of description
    for line in description.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:60] + ("..." if len(stripped) > 60 else "")
    
    return "(no result)"


@dataclass
class SceneIntroduction:
    """Metadata tracking how the player entered this scene."""
    previous_room: str | None
    move_number: int
    command: str


@dataclass
class Scene:
    """Persistent state for a single room/scene."""
    room_name: str
    description_lines: list[str] = field(default_factory=list)
    scene_items: list[str] = field(default_factory=list)
    current_items: list[str] = field(default_factory=list)
    scene_actions: list[str] = field(default_factory=list)
    scene_intro_collection: list[SceneIntroduction] = field(default_factory=list)
    npcs: list[str] = field(default_factory=list)
    narrations: list[str] = field(default_factory=list)
    visit_count: int = 0
    first_visit_turn: int | None = None
    last_visit_turn: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for TinyDB storage."""
        return {
            "room_name": self.room_name,
            "description_lines": self.description_lines,
            "scene_items": self.scene_items,
            "current_items": self.current_items,
            "scene_actions": self.scene_actions,
            "scene_intro_collection": [asdict(intro) for intro in self.scene_intro_collection],
            "npcs": self.npcs,
            "narrations": self.narrations,
            "visit_count": self.visit_count,
            "first_visit_turn": self.first_visit_turn,
            "last_visit_turn": self.last_visit_turn,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Scene":
        """Deserialize from TinyDB dict."""
        intro_data = data.get("scene_intro_collection", [])
        intros: list[SceneIntroduction] = []
        for intro in intro_data:
            if isinstance(intro, SceneIntroduction):
                intros.append(intro)
            elif isinstance(intro, dict):
                intros.append(SceneIntroduction(**intro))

        raw_actions = data.get("scene_actions", [])
        normalized_actions: list[str] = []
        for action in raw_actions:
            if isinstance(action, dict):
                normalized_actions.append(action.get("command", ""))
            elif action is not None:
                normalized_actions.append(str(action))

        return Scene(
            room_name=data.get("room_name", ""),
            description_lines=data.get("description_lines", []),
            scene_items=data.get("scene_items", []),
            current_items=data.get("current_items", []),
            scene_actions=normalized_actions,
            scene_intro_collection=intros,
            npcs=data.get("npcs", []),
            narrations=data.get("narrations", []),
            visit_count=data.get("visit_count", 0),
            first_visit_turn=data.get("first_visit_turn"),
            last_visit_turn=data.get("last_visit_turn"),
        )


class GameMemoryStore:
    """TinyDB-backed episodic and persistent memory for a game session.
    
        Maintains a set of Scene objects, one per unique room, and tracks:
            - Description lines (non-duplicative union)
            - Visible/inventory items
            - NPCs encountered
            - Scene actions
            - AI narrations generated
            - Entry metadata (previous room, command, turn number)
    
    Provides serialization to disk and context extraction for prompts.
    """

    def __init__(self, player_name: str, db_path: str | None = None) -> None:
        """Initialize the memory store with optional persistent DB.
        
        Args:
            player_name: Player identifier for logging and context.
            db_path: Path to TinyDB file. If None, uses player-scoped default.
        """
        self.player_name = player_name
        
        if db_path is None:
            db_path = f"log/{player_name}_memory.json"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db = TinyDB(str(self.db_path), indent=2)
        self._scenes: dict[str, Scene] = {}
        self._current_room: str | None = None
        self._turn_count: int = 0
        
        # Load existing scenes from DB
        self._load_scenes()
        
        my_logging.system_info(f"GameMemoryStore initialized for {player_name} at {self.db_path}")

    def _load_scenes(self) -> None:
        """Load all scenes from TinyDB into memory cache."""
        try:
            for record in self.db.all():
                scene = Scene.from_dict(record)
                self._scenes[scene.room_name] = scene
            my_logging.system_debug(f"Loaded {len(self._scenes)} scenes from DB")
        except Exception as exc:
            my_logging.system_warn(f"Failed to load scenes from DB: {exc}")

    def update_from_engine_facts(
        self,
        facts: EngineFacts,
        *,
        command: str | None = None,
        previous_room: str | None = None,
    ) -> None:
        """Update memory based on parsed engine facts from a turn.
        
        Args:
            facts: Parsed `EngineFacts` from `parse_engine_facts()`.
            command: Optional player command that led to this state.
            previous_room: Optional room name before this turn.
        """
        self._turn_count += 1

        turn_envelope = {
            "turn": self._turn_count,
            "command": command,
            "previous_room": previous_room,
            "room": facts.room_name,
            "moves": facts.moves,
            "score": facts.score,
            "gameException": facts.gameException,
            "exceptionMessage": facts.exceptionMessage,
        }
        
        # Skip if engine reported an error
        if facts.gameException:
            my_logging.log_memory_event("turn_recorded", turn_envelope)
            return
        
        if not facts.room_name:
            my_logging.system_warn("Engine facts missing room_name; skipping memory update")
            my_logging.log_memory_event("turn_recorded", turn_envelope)
            return
        
        room_name = facts.room_name
        is_new_room = room_name not in self._scenes
        
        # Get or create scene
        if is_new_room:
            scene = Scene(room_name=room_name, first_visit_turn=self._turn_count)
            self._scenes[room_name] = scene
            my_logging.log_memory_event("new_scene", {
                "room": room_name,
                "turn": self._turn_count,
            })
        else:
            scene = self._scenes[room_name]
        
        # Update visit metadata
        scene.visit_count += 1
        scene.last_visit_turn = self._turn_count
        
        # Track entry if coming from a different room (store only the last predecessor)
        if previous_room and previous_room != room_name:
            entry = SceneIntroduction(
                previous_room=previous_room,
                move_number=facts.moves or self._turn_count,
                command=command or "unknown",
            )
            # Replace the entire intro collection with just this entry (single predecessor)
            scene.scene_intro_collection = [entry]
            my_logging.log_memory_event("scene_intro_updated", {
                "room": room_name,
                "previous_room": previous_room,
                "command": command,
                "move_number": facts.moves or self._turn_count,
            })
        
        # Accumulate description lines (non-duplicative)
        if facts.description:
            for line in facts.description.splitlines():
                line = line.strip()
                if line and line not in scene.description_lines:
                    scene.description_lines.append(line)
                    my_logging.log_memory_event("description_added", {
                        "room": room_name,
                        "line": line[:80],
                    })
        
        # Accumulate visible items (non-duplicative)
        if facts.visible_items:
            for item in facts.visible_items:
                if item and item not in scene.scene_items:
                    scene.scene_items.append(item)
        
        # Update current inventory snapshot
        if facts.inventory is not None:
            old_inventory = set(scene.current_items)
            new_inventory = set(facts.inventory)
            if old_inventory != new_inventory:
                scene.current_items = facts.inventory
                my_logging.log_state_change("inventory", list(old_inventory), facts.inventory)
        
        # Accumulate action (command that led here)
        if command:
            action_summary = f"{command} -> {room_name}"
            if action_summary not in scene.scene_actions:
                scene.scene_actions.append(action_summary)
        
        self._current_room = room_name
        self._persist_scene(scene)

        # Transaction envelope: emitted once per turn so the memory JSONL reads as a timeline.
        my_logging.log_memory_event("turn_recorded", turn_envelope)

    def _persist_scene(self, scene: Scene) -> None:
        """Write scene to TinyDB."""
        try:
            Scene_query = Query()
            self.db.upsert(scene.to_dict(), Scene_query.room_name == scene.room_name)
            my_logging.system_debug(f"Persisted scene: {scene.room_name}")
        except Exception as exc:
            my_logging.system_warn(f"Failed to persist scene {scene.room_name}: {exc}")

    def get_context_for_prompt(self) -> dict[str, Any]:
        """Extract context for LLM prompt from current memory.
        
        Returns a dict with:
          - current_room: name of the current room
          - current_scene: full Scene object for current room
          - recent_history: summary of last few turns
          - relevant_scenes: other nearby/relevant scenes
          - persistent_facts: NPCs, important items, etc.
        """
        if not self._current_room or self._current_room not in self._scenes:
            return {"status": "no_context", "turn_count": self._turn_count}
        
        current_scene = self._scenes[self._current_room]
        
        # Compile persistent facts across all scenes
        all_npcs = list(set().union(*(s.npcs for s in self._scenes.values())))
        all_items = list(set().union(*(s.scene_items for s in self._scenes.values())))
        
        return {
            "turn_count": self._turn_count,
            "current_room": self._current_room,
            "current_scene": {
                "room_name": current_scene.room_name,
                "description": "\n".join(current_scene.description_lines[-3:]),  # Last 3 lines
                "visible_items": current_scene.scene_items,
                "current_inventory": current_scene.current_items,
                "npcs": current_scene.npcs,
                "visit_count": current_scene.visit_count,
                "recent_narrations": current_scene.narrations[-2:],  # Last 2 narrations
            },
            "persistent_facts": {
                "all_known_npcs": all_npcs,
                "all_seen_items": all_items,
                "total_scenes_visited": len(self._scenes),
            },
            "game_progress": {
                "total_turns": self._turn_count,
                "scenes_visited": [s.room_name for s in self._scenes.values()],
            },
        }

    def reset(self) -> None:
        """Clear all memory for session restart or player rename."""
        try:
            self.db.truncate()
            self._scenes.clear()
            self._current_room = None
            self._turn_count = 0
            my_logging.log_memory_event("reset", {"player": self.player_name})
            my_logging.system_info(f"Memory reset for {self.player_name}")
        except Exception as exc:
            my_logging.system_warn(f"Failed to reset memory: {exc}")

    def close(self) -> None:
        """Close the TinyDB connection."""
        try:
            self.db.close()
        except Exception as exc:
            my_logging.system_warn(f"Failed to close DB: {exc}")

    def append_narration(self, room_name: str | None, narration: str | None) -> None:
        """Store generated narration text for a scene."""
        if not room_name or not narration:
            return
        narration = narration.strip()
        if not narration:
            return
        scene = self._scenes.get(room_name)
        if not scene:
            return
        if narration in scene.narrations:
            return
        scene.narrations.append(narration)
        my_logging.log_memory_event("narration_added", {
            "room": room_name,
            "narration": narration[:80],
        })
        self._persist_scene(scene)


__all__ = [
    "Scene",
    "SceneIntroduction",
    "GameMemoryStore",
]
