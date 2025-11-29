"""Game memory management with episodic and state-based tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from module import my_logging


@dataclass
class EpisodicEvent:
    """Single episodic memory entry: one turn in the game."""

    turn: int
    command: str
    transcript: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GameRoom:
    """A single room in the game world."""

    name: str
    description: str = ""
    items: list[str] = field(default_factory=list)
    visited_at_turn: int | None = None


@dataclass
class GameState:
    """Current in-game world state."""

    rooms: dict[str, GameRoom] = field(default_factory=dict)
    inventory: list[str] = field(default_factory=list)
    npcs: dict[str, str] = field(default_factory=dict)  # name -> location
    objectives: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)


class GameMemoryStore:
    """
    Manages episodic and in-game state memory.
    
    Episodic memory: FIFO ring of recent turns (volatile, max ~10 turns).
    Game state: Current world facts (stable but updated per turn).
    """

    def __init__(self, player_name: str, max_episodic: int = 10) -> None:
        self.player_name = player_name
        self.max_episodic = max_episodic
        self._episodic: list[EpisodicEvent] = []
        self._game_state = GameState()
        self._turn_counter = 0

    def add_turn(self, command: str, transcript: str) -> None:
        """Record a new turn in episodic memory."""
        self._turn_counter += 1
        event = EpisodicEvent(
            turn=self._turn_counter,
            command=command,
            transcript=transcript,
        )
        self._episodic.append(event)

        # Keep episodic memory bounded
        if len(self._episodic) > self.max_episodic:
            self._episodic.pop(0)

        # Log the episodic event
        if my_logging.is_debug_enabled():
            my_logging.log_player_output(
                f"Turn {self._turn_counter}: {command} -> {transcript[:100]}",
                pid=None,
            )

    def extract_and_promote_state(self, transcript: str) -> None:
        """
        Parse transcript to extract and promote stable facts to game state.
        
        Heuristics:
        - Room names: capitalized lines at start of transcript
        - Inventory: "You are carrying:" patterns
        - Items in room: lines with verbs like "taken", "see", "here"
        """
        # Extract room name (first non-empty line, typically capitalized)
        room_match = self._extract_room_name(transcript)
        if room_match:
            if room_match not in self._game_state.rooms:
                self._game_state.rooms[room_match] = GameRoom(
                    name=room_match,
                    visited_at_turn=self._turn_counter,
                )
            else:
                # Update description if not set
                if not self._game_state.rooms[room_match].description:
                    self._game_state.rooms[room_match].description = transcript[:200]

        # Extract inventory
        inventory_match = self._extract_inventory(transcript)
        if inventory_match is not None:
            if inventory_match != self._game_state.inventory:
                my_logging.system_debug(
                    f"Inventory conflict: old {self._game_state.inventory}, new {inventory_match}"
                )
            self._game_state.inventory = inventory_match

        # Extract world changes (items taken, dropped, etc.)
        changes = self._extract_changes(transcript)
        for change in changes:
            if change not in self._game_state.recent_changes:
                self._game_state.recent_changes.append(change)

        # Log state update
        if my_logging.is_debug_enabled():
            my_logging.system_debug(
                f"State updated at turn {self._turn_counter}: "
                f"room={room_match}, inv={len(self._game_state.inventory)}, "
                f"rooms_visited={len(self._game_state.rooms)}"
            )

    def get_context_for_prompt(self) -> dict[str, Any]:
        """Build context dict for LLM prompt."""
        return {
            "episodic_turns": [
                {
                    "turn": e.turn,
                    "command": e.command,
                    "transcript": e.transcript,
                }
                for e in self._episodic
            ],
            "game_state": {
                "current_rooms": list(self._game_state.rooms.keys())[-3:],  # last 3
                "inventory": self._game_state.inventory,
                "recent_changes": self._game_state.recent_changes[-5:],  # last 5
            },
            "current_turn": self._turn_counter,
        }

    def reset(self) -> None:
        """Clear all memory (e.g., on player rename or new session)."""
        self._episodic.clear()
        self._game_state = GameState()
        self._turn_counter = 0
        my_logging.system_info(f"Memory reset for player {self.player_name}")

    # -------- Private helpers --------

    def _extract_room_name(self, transcript: str) -> str | None:
        """Extract room name from transcript (first capitalized line)."""
        for line in transcript.split("\n"):
            line = line.strip()
            if line and len(line) > 2 and line[0].isupper():
                # Heuristic: room names are often all caps or Title Case
                if line.isupper() or (line[0].isupper() and " " in line):
                    return line
        return None

    def _extract_inventory(self, transcript: str) -> list[str] | None:
        """Extract inventory from transcript (heuristic: "You are carrying:" patterns)."""
        # Look for "You are carrying:" or "You have:"
        match = re.search(
            r"(?:You are carrying|You have):\s*(.+?)(?:\n\n|$)",
            transcript,
            re.DOTALL,
        )
        if match:
            items_str = match.group(1).strip()
            # Split by common delimiters
            items = [i.strip() for i in re.split(r"[,\n]", items_str) if i.strip()]
            return items if items else None
        return None

    def _extract_changes(self, transcript: str) -> list[str]:
        """Extract world changes (items taken, dropped, events)."""
        changes = []
        # Look for patterns like "You take X", "You drop X", "X is destroyed"
        patterns = [
            r"You take the (.+?)(?:[.,\n]|$)",
            r"You drop the (.+?)(?:[.,\n]|$)",
            r"(.+?) is destroyed(?:[.,\n]|$)",
            r"You examine the (.+?)(?:[.,\n]|$)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, transcript, re.IGNORECASE):
                change = match.group(1).strip()
                if change:
                    changes.append(change)
        return changes


__all__ = [
    "EpisodicEvent",
    "GameRoom",
    "GameState",
    "GameMemoryStore",
]
