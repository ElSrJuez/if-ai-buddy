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


@dataclass
class SceneIntroduction:
    """Metadata tracking how the player entered this scene."""
    previous_room: str | None
    move_number: int
    command: str


@dataclass(frozen=True)
class ActionRecord:
    """Structured record of a player action and its inferred effects."""
    turn: int
    command: str
    result: str
    category: str
    verb: str
    target_item: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "command": self.command,
            "result": self.result,
            "category": self.category,
            "verb": self.verb,
            "target_item": self.target_item,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ActionRecord":
        return ActionRecord(
            turn=int(data.get("turn", 0)),
            command=str(data.get("command", "")),
            result=str(data.get("result", "")),
            category=str(data.get("category", "interaction")),
            verb=str(data.get("verb", "")),
            target_item=data.get("target_item"),
        )


@dataclass
class Scene:
    """Persistent state for a single room/scene."""
    room_name: str
    description_lines: list[str] = field(default_factory=list)
    scene_items: list[str] = field(default_factory=list)
    current_items: list[str] = field(default_factory=list)
    scene_actions: list[str] = field(default_factory=list)
    action_records: list[ActionRecord] = field(default_factory=list)
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
            "action_records": [record.to_dict() for record in self.action_records],
            "scene_intro_collection": [asdict(intro) for intro in self.scene_intro_collection],
            "npcs": self.npcs,
            "narrations": self.narrations,
            "visit_count": self.visit_count,
            "first_visit_turn": self.first_visit_turn,
            "last_visit_turn": self.last_visit_turn,
        }

    def to_scene_envelope(self) -> dict[str, Any]:
        description = "\n".join(self.description_lines) if self.description_lines else None
        intros = [
            {
                "previous_room": intro.previous_room,
                "move_number": intro.move_number,
                "command": intro.command,
            }
            for intro in self.scene_intro_collection
        ]
        return {
            "room_name": self.room_name,
            "description": description,
            "scene_items": self.scene_items,
            "current_items": self.current_items,
            "scene_actions": self.scene_actions,
            "action_records": [record.to_dict() for record in self.action_records],
            "scene_intro_collection": intros,
            "npcs": self.npcs,
            "narrations": self.narrations,
            "visit_count": self.visit_count,
            "first_visit_turn": self.first_visit_turn,
            "last_visit_turn": self.last_visit_turn,
            "visible_items": self.current_items,
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

        raw_records = data.get("action_records", [])
        action_records: list[ActionRecord] = []
        for record in raw_records:
            if isinstance(record, ActionRecord):
                action_records.append(record)
            elif isinstance(record, dict):
                action_records.append(ActionRecord.from_dict(record))

        return Scene(
            room_name=data.get("room_name", ""),
            description_lines=data.get("description_lines", []),
            scene_items=data.get("scene_items", []),
            current_items=data.get("current_items", []),
            scene_actions=normalized_actions,
            action_records=action_records,
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

    _ITEM_ACQUIRE_VERBS: set[str] = {"take", "get", "grab", "pick"}
    _ITEM_DROP_VERBS: set[str] = {"drop", "leave", "put", "place", "remove"}
    _ITEM_VERBS: set[str] = _ITEM_ACQUIRE_VERBS | _ITEM_DROP_VERBS
    _WORLD_OBJECT_VERBS: set[str] = {
        "open",
        "close",
        "read",
        "look",
        "examine",
        "inspect",
        "search",
    }

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
        self._player_state_table = self.db.table("_player_state")
        self._scenes: dict[str, Scene] = {}
        self._current_room: str | None = None
        self._turn_count: int = 0
        self._player_inventory: list[str] = []
        self._player_moves: int | None = None
        self._player_score: int | None = None
        
        # Load existing scenes from DB
        self._load_scenes()
        self._load_player_state()
        
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

    def _load_player_state(self) -> None:
        """Load persisted player state snapshot if available."""
        try:
            PlayerStateQuery = Query()
            record = self._player_state_table.get(PlayerStateQuery.key == "player_state")
            if not record:
                return
            inventory = record.get("inventory") or []
            if isinstance(inventory, list):
                self._player_inventory = list(inventory)
            self._player_moves = record.get("moves")
            self._player_score = record.get("score")
        except Exception as exc:
            my_logging.system_warn(f"Failed to load player state: {exc}")

    def _persist_player_state(self) -> None:
        """Persist current player state snapshot."""
        try:
            snapshot = {
                "key": "player_state",
                "inventory": self._player_inventory,
                "moves": self._player_moves,
                "score": self._player_score,
                "last_updated_turn": self._turn_count,
            }
            PlayerStateQuery = Query()
            self._player_state_table.upsert(snapshot, PlayerStateQuery.key == "player_state")
        except Exception as exc:
            my_logging.system_warn(f"Failed to persist player state: {exc}")

    def _sync_player_state(self, facts: EngineFacts) -> None:
        snapshot = facts.player_state
        if not snapshot:
            return
        inventory_changed = False
        moves_changed = False
        score_changed = False
        if snapshot.inventory is not None:
            normalized_inventory = list(snapshot.inventory)
            if normalized_inventory != self._player_inventory:
                my_logging.log_state_change("player_inventory", self._player_inventory, normalized_inventory)
                self._player_inventory = normalized_inventory
                inventory_changed = True
        if snapshot.moves is not None and snapshot.moves != self._player_moves:
            self._player_moves = snapshot.moves
            moves_changed = True
        if snapshot.score is not None and snapshot.score != self._player_score:
            self._player_score = snapshot.score
            score_changed = True
        if inventory_changed or moves_changed or score_changed:
            self._persist_player_state()

    @staticmethod
    def _normalize_label(label: str | None) -> str:
        if not label:
            return ""
        return " ".join(label.lower().split())

    @staticmethod
    def _format_action_entry(action: ActionRecord) -> str:
        return f"T{action.turn:04d}: {action.command} -> {action.result}"

    def _labels_match(self, a: str, b: str) -> bool:
        normalized_a = self._normalize_label(a)
        normalized_b = self._normalize_label(b)
        if not normalized_a or not normalized_b:
            return False
        return normalized_a == normalized_b or normalized_a in normalized_b or normalized_b in normalized_a

    def _find_label(self, collection: list[str], label: str | None) -> str | None:
        if not label:
            return None
        for existing in collection:
            if self._labels_match(existing, label):
                return existing
        return None

    def _ensure_label(self, collection: list[str], label: str) -> str:
        existing = self._find_label(collection, label)
        if existing:
            return existing
        collection.append(label)
        return label

    def _remove_label(self, collection: list[str], label: str) -> bool:
        existing = self._find_label(collection, label)
        if not existing:
            return False
        collection.remove(existing)
        return True

    def _log_current_items_change(self, before: list[str], after: list[str]) -> None:
        if before != after:
            my_logging.log_state_change("current_items", before, after)

    @staticmethod
    def _split_paragraphs(text: str | None) -> list[str]:
        if not text:
            return []
        segments: list[str] = []
        buffer: list[str] = []

        def flush() -> None:
            if not buffer:
                return
            segments.append(GameMemoryStore._merge_wrapped_lines(buffer))
            buffer.clear()

        for raw in text.splitlines():
            if not raw.strip():
                flush()
                continue
            buffer.append(raw.rstrip())
        flush()
        return [segment for segment in segments if segment]

    @staticmethod
    def _merge_wrapped_lines(lines: list[str]) -> str:
        if not lines:
            return ""
        merged = lines[0].strip()
        for raw in lines[1:]:
            if raw.startswith(" "):
                merged += "\n" + raw.rstrip()
            else:
                separator = " " if merged and not merged.endswith((" ", "-", "—")) else ""
                merged += f"{separator}{raw.strip()}"
        return merged.strip()

    @staticmethod
    def _extract_transcript_body(transcript: str | None) -> str | None:
        if not transcript:
            return None
        lines = transcript.splitlines()
        body_lines: list[str] = []
        header_found = False
        for line in lines:
            if not header_found:
                if "Score:" in line and "Moves:" in line:
                    header_found = True
                continue
            body_lines.append(line)
        body = "\n".join(body_lines).strip()
        return body or None

    @staticmethod
    def _summarize_action_result(
        *,
        room_name: str | None,
        previous_room: str | None,
        description: str | None,
        transcript: str | None,
    ) -> str:
        if room_name and previous_room and room_name != previous_room:
            return room_name
        paragraphs = GameMemoryStore._split_paragraphs(description)
        if not paragraphs:
            transcript_body = GameMemoryStore._extract_transcript_body(transcript)
            paragraphs = GameMemoryStore._split_paragraphs(transcript_body)
        if paragraphs:
            return "\n\n".join(paragraphs)
        return "..."

    @staticmethod
    def _extract_action_target(command: str) -> tuple[str, str | None]:
        raw = command.strip()
        lowered = raw.lower()
        if not lowered:
            return "", None

        patterns: list[tuple[str, str]] = [
            ("take ", "take"),
            ("get ", "take"),
            ("grab ", "take"),
            ("pick up ", "take"),
            ("pick ", "take"),
            ("drop ", "drop"),
            ("leave ", "drop"),
            ("put ", "drop"),
            ("place ", "drop"),
            ("remove ", "drop"),
        ]

        for prefix, normalized in patterns:
            if lowered.startswith(prefix):
                tail = raw[len(prefix):].strip()
                target = GameMemoryStore._extract_primary_target(tail)
                return normalized, target

        parts = raw.split()
        verb = parts[0].lower()
        target = " ".join(parts[1:]).strip() or None
        return verb, target

    @staticmethod
    def _extract_primary_target(phrase: str) -> str | None:
        candidate = phrase.strip()
        if not candidate:
            return None
        lowered = candidate.lower()
        separators = [
            " into ",
            " in ",
            " inside ",
            " within ",
            " on ",
            " onto ",
            " to ",
            " from ",
        ]
        for sep in separators:
            idx = lowered.find(sep)
            if idx != -1:
                return candidate[:idx].strip() or None
        return candidate or None

    def _build_action_record(
        self,
        *,
        command: str,
        result: str,
        room_name: str | None,
        previous_room: str | None,
    ) -> ActionRecord:
        verb, target = self._extract_action_target(command)
        room_changed = bool(room_name and previous_room and room_name != previous_room)
        category = self._categorize_action(
            verb=verb,
            has_target=bool(target),
            room_changed=room_changed,
        )
        return ActionRecord(
            turn=self._turn_count,
            command=command,
            result=result,
            category=category,
            verb=verb,
            target_item=target,
        )

    def _categorize_action(self, *, verb: str, has_target: bool, room_changed: bool) -> str:
        if room_changed:
            return "movement"
        if verb in self._ITEM_VERBS or (has_target and verb in self._ITEM_ACQUIRE_VERBS):
            return "item_interaction"
        if verb in self._WORLD_OBJECT_VERBS:
            return "world_object_interaction"
        return "generic_interaction"

    @staticmethod
    def _action_succeeded(action: ActionRecord, *, keywords: tuple[str, ...]) -> bool:
        text = action.result.lower()
        return any(keyword in text for keyword in keywords)

    def _apply_world_item_effects(
        self,
        *,
        scene: Scene,
        action: ActionRecord,
        inventory_snapshot_present: bool,
    ) -> None:
        if action.category != "item_interaction" or not action.target_item:
            return
        label = self._ensure_label(scene.scene_items, action.target_item)
        before = list(scene.current_items)
        if action.verb in self._ITEM_ACQUIRE_VERBS and self._action_succeeded(
            action,
            keywords=("taken", "already have", "take", "got", "in your possession"),
        ):
            removed = self._remove_label(scene.current_items, label)
            if removed:
                self._log_current_items_change(before, scene.current_items)
            if not inventory_snapshot_present:
                self._update_inventory_from_action(label, add=True)
        elif action.verb in self._ITEM_DROP_VERBS and self._action_succeeded(
            action,
            keywords=("dropped", "placed", "left", "put", "done"),
        ):
            if not self._find_label(scene.current_items, label):
                scene.current_items.append(label)
            self._log_current_items_change(before, scene.current_items)
            if not inventory_snapshot_present:
                self._update_inventory_from_action(label, add=False)

    def _update_inventory_from_action(self, label: str, *, add: bool) -> None:
        before = list(self._player_inventory)
        if add:
            if not self._find_label(self._player_inventory, label):
                self._player_inventory.append(label)
        else:
            self._remove_label(self._player_inventory, label)
        if before != self._player_inventory:
            my_logging.log_state_change("player_inventory", before, list(self._player_inventory))
            self._persist_player_state()

    def _build_scene_envelope(
        self,
        *,
        scene: Scene,
        facts: EngineFacts,
        command: str | None,
        transcript: str | None,
    ) -> dict[str, Any]:
        return {
            "scene": scene.to_scene_envelope(),
            "engine_turn": {
                "command": command or "unknown",
                "transcript": transcript or "",
                "room_name": facts.room_name,
                "description": facts.description,
                "visible_items": facts.visible_items,
                "player_state": facts.player_state.to_dict(),
                "gameException": facts.gameException,
                "exceptionMessage": facts.exceptionMessage,
            },
        }

    def update_from_engine_facts(
        self,
        facts: EngineFacts,
        *,
        command: str | None = None,
        previous_room: str | None = None,
        transcript: str | None = None,
    ) -> None:
        """Update memory based on parsed engine facts from a turn.
        
        Args:
            facts: Parsed `EngineFacts` from `parse_engine_facts()`.
            command: Optional player command that led to this state.
            previous_room: Optional room name before this turn.
            transcript: Raw engine transcript for envelope persistence.
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
        
        # Track entry if coming from a different room (store only immediate predecessor)
        if previous_room and previous_room != room_name:
            entry = SceneIntroduction(
                previous_room=previous_room,
                move_number=facts.moves if facts.moves is not None else self._turn_count,
                command=command or "unknown",
            )
            scene.scene_intro_collection = [entry]
            my_logging.log_memory_event("scene_intro_updated", {
                "room": room_name,
                "from": previous_room,
                "move_number": entry.move_number,
                "command": command,
            })
        
        # Synchronize global player state snapshot
        self._sync_player_state(facts)

        # Accumulate description lines (non-duplicative)
        for paragraph in self._split_paragraphs(facts.description):
            if paragraph and paragraph not in scene.description_lines:
                scene.description_lines.append(paragraph)
                my_logging.log_memory_event("description_added", {
                    "room": room_name,
                    "line": paragraph[:80],
                })
        
        # Accumulate visible items (non-duplicative)
        if facts.visible_items:
            for item in facts.visible_items:
                if item and item not in scene.scene_items:
                    scene.scene_items.append(item)
        
        # Update current items from visible room objects
        inventory_snapshot_present = facts.player_state.inventory is not None

        if facts.visible_items is not None:
            old_items = set(scene.current_items)
            new_items = set(facts.visible_items)
            if old_items != new_items:
                scene.current_items = facts.visible_items
                my_logging.log_state_change("current_items", list(old_items), facts.visible_items)
        
        # Accumulate action (command and result)
        action_record: ActionRecord | None = None
        if command:
            result_summary = self._summarize_action_result(
                room_name=room_name,
                previous_room=previous_room,
                description=facts.description,
                transcript=transcript,
            )
            action_record = self._build_action_record(
                command=command,
                result=result_summary,
                room_name=room_name,
                previous_room=previous_room,
            )
            entry = self._format_action_entry(action_record)
            if entry not in scene.scene_actions:
                scene.scene_actions.append(entry)
                my_logging.log_memory_event("scene_action_added", {
                    "room": room_name,
                    "command": command,
                    "result": result_summary[:80],
                    "turn": self._turn_count,
                })
            has_record = any(r.turn == action_record.turn and r.command == action_record.command for r in scene.action_records)
            if not has_record:
                scene.action_records.append(action_record)

        if action_record and facts.visible_items is None:
            self._apply_world_item_effects(
                scene=scene,
                action=action_record,
                inventory_snapshot_present=inventory_snapshot_present,
            )
        
        self._current_room = room_name
        self._persist_scene(scene)

        if transcript:
            envelope = self._build_scene_envelope(
                scene=scene,
                facts=facts,
                command=command,
                transcript=transcript,
            )
            my_logging.log_memory_event("scene_envelope", envelope)

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
                "current_items": current_scene.current_items,
                "npcs": current_scene.npcs,
                "visit_count": current_scene.visit_count,
                "recent_narrations": current_scene.narrations[-2:],  # Last 2 narrations
            },
            "player_state": {
                "inventory": self._player_inventory,
                "score": self._player_score,
                "moves": self._player_moves,
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
            self._player_state_table.truncate()
            self._scenes.clear()
            self._current_room = None
            self._turn_count = 0
            self._player_inventory = []
            self._player_moves = None
            self._player_score = None
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
    "ActionRecord",
    "GameMemoryStore",
]
