"""Schema-driven heuristics for parsing game engine transcripts."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineMetadata:
    pid: int | None = None
    status_code: int | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class PlayerStateSnapshot:
    inventory: list[str] | None = None
    score: int | None = None
    moves: int | None = None

    def to_dict(self) -> dict[str, list[str] | int | None]:
        return {
            "inventory": self.inventory,
            "score": self.score,
            "moves": self.moves,
        }


@dataclass(frozen=True)
class EngineFacts:
    room_name: str | None
    player_state: PlayerStateSnapshot
    visible_items: list[str] | None
    description: str | None
    gameException: bool
    exceptionMessage: str | None

    @property
    def score(self) -> int | None:  # Back-compat for legacy callers
        return self.player_state.score

    @property
    def moves(self) -> int | None:
        return self.player_state.moves

    @property
    def inventory(self) -> list[str] | None:
        return self.player_state.inventory


def parse_engine_facts(transcript: str) -> EngineFacts:
    """Return the canonical heuristics output for the supplied transcript."""
    normalized = transcript or ""
    header_line = _find_header_line(normalized)

    game_exception = False
    exception_message = None
    description = None
    room_name = None

    if header_line:
        room_name = _extract_room_name(header_line)
        description = _extract_description(normalized, header_line, room_name)
    else:
        game_exception = True
        exception_message = _extract_exception_message(normalized)

    score, moves = _extract_score_and_moves(normalized)
    inventory = _extract_inventory(normalized)
    visible_items = _extract_visible_items(normalized)

    player_state = PlayerStateSnapshot(
        inventory=inventory,
        score=score,
        moves=moves,
    )

    return EngineFacts(
        room_name=room_name,
        player_state=player_state,
        visible_items=visible_items,
        description=description,
        gameException=game_exception,
        exceptionMessage=exception_message,
    )


def _find_header_line(transcript: str) -> str | None:
    for line in transcript.splitlines():
        if "Score:" in line and "Moves:" in line:
            return line.strip()
    return None


def _extract_room_name(header_line: str) -> str | None:
    if not header_line:
        return None
    if "Score:" in header_line:
        return header_line.split("Score:", 1)[0].strip()
    return header_line.strip()


def _extract_description(
    transcript: str, header_line: str, room_name: str | None
) -> str | None:
    split_parts = transcript.split(header_line, 1)
    if len(split_parts) < 2:
        return None
    remainder = split_parts[1]

    # Heuristic: capture the full body after the header line.
    # Many IF engines (including Zork) include blank lines inside legitimate
    # action feedback (e.g., reading a leaflet/book), so stopping at the first
    # blank line truncates important content.
    lines = remainder.splitlines()

    # Trim leading blank lines.
    while lines and not lines[0].strip():
        lines.pop(0)

    # Some transcripts repeat the room name as the first line of the body.
    if lines and room_name and lines[0].strip() == room_name:
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    # Trim trailing blank lines.
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return None
    return "\n".join(lines)


def _extract_score_and_moves(transcript: str) -> tuple[int | None, int | None]:
    score = None
    moves = None
    match = re.search(r"Score:\s*(\d+).*?Moves:\s*(\d+)", transcript, re.DOTALL)
    if match:
        score = int(match.group(1))
        moves = int(match.group(2))
    return score, moves


def _extract_inventory(transcript: str) -> list[str] | None:
    match = re.search(r"You (?:are carrying|have):\s*(.+?)(?:\n\n|$)", transcript, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    raw_inventory = match.group(1)
    items = [item.strip() for item in re.split(r"[,\n]", raw_inventory) if item.strip()]
    return items or None


def _extract_visible_items(transcript: str) -> list[str] | None:
    patterns = [r"There (?:is|are) (.+?)(?:\.|$)", r"You (?:can )?see (.+?)(?:\.|$)"]
    collected: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, transcript, re.IGNORECASE | re.DOTALL):
            fragments = re.split(r",| and |\band\b", match)
            for fragment in fragments:
                candidate = fragment.strip()
                if not candidate or candidate.lower().startswith("no "):
                    continue
                collected.append(candidate)
    if not collected:
        return None
    return collected


def _extract_exception_message(transcript: str) -> str | None:
    for line in transcript.splitlines():
        stripped = line.strip()
        if stripped and stripped[0].isupper() and " " in stripped:
            return stripped
    return None


def as_dict(facts: EngineFacts) -> dict[str, object | None]:
    return {
        "room_name": facts.room_name,
        "player_state": facts.player_state.to_dict(),
        "visible_items": facts.visible_items,
        "description": facts.description,
        "gameException": facts.gameException,
        "exceptionMessage": facts.exceptionMessage,
    }


__all__ = [
    "EngineMetadata",
    "PlayerStateSnapshot",
    "EngineFacts",
    "parse_engine_facts",
    "as_dict",
]
