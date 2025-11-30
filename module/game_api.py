"""Lean wrapper around the dfrotz REST engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module.rest_helper import DfrotzClient, SessionHandle
from module.my_logging import log_gameapi_event
import re


@dataclass
class GameSession:
    handle: SessionHandle
    intro_text: str

@dataclass
class EngineTurn:
    session: GameSession
    command: str
    transcript: str
    room_name: str | None = None
    score: int | None = None
    moves: int | None = None
    inventory: list[str] | None = None
    visible_items: list[str] | None = None
    description: str | None = None
    gameException: bool = False
    exceptionMessage: str | None = None
    # metadata such as pid and HTTP status can be added later

class GameAPI:
    def _parse_engine_data(self, transcript: str) -> dict[str, Any]:
        # initialize exception flags
        gameException = False
        exceptionMessage = None
        # Heuristics parser: extract room, score, moves, inventory, description
        room = None
        header_line = None
        # Identify header line containing room name and score/moves
        for line in transcript.splitlines():
            if 'Score:' in line and 'Moves:' in line:
                header_line = line.strip()
                break
        
        description = None
        if header_line:
            # room name is text before 'Score:'
            room = header_line.split('Score:')[0].strip()
            after = transcript.split(header_line, 1)[1].lstrip()
            desc_lines = []
            for line in after.splitlines():
                if not line.strip():
                    break
                desc_lines.append(line)
            if desc_lines:
                # drop first line if it's identical to the room name
                if desc_lines[0].strip() == room:
                    desc_lines = desc_lines[1:]
                description = '\n'.join(desc_lines)
        else:
            # if no headerline, we will assume it is an exception response.
            gameException = True
            # room name must be null
            room = None
            description = None            
            for line in transcript.splitlines():
                l = line.strip()
                if l and l[0].isupper() and ' ' in l:
                    exceptionMessage = l
                    break
        # Score/moves extraction
        score = None; moves = None
        m = re.search(r"Score:\s*(\d+)", transcript)
        if m: score = int(m.group(1))
        m2 = re.search(r"Moves:\s*(\d+)", transcript)
        if m2: moves = int(m2.group(1))
        # Inventory
        inventory = None
        m3 = re.search(r"You (?:are carrying|have):\s*(.+?)(?:\n\n|$)", transcript, re.DOTALL)
        if m3:
            inventory = [i.strip() for i in re.split(r"[,\n]", m3.group(1)) if i.strip()]
        # Visible items stub
        visible_items = None
        # Description extraction: lines after header until blank line

            
        return {
            'room_name': room,
            'score': score,
            'moves': moves,
            'inventory': inventory,
            'visible_items': visible_items,
            'description': description,
            'gameException': gameException,
            'exceptionMessage': exceptionMessage,
        }

    def __init__(self, rest_client: DfrotzClient, *, game_name: str, label: str) -> None:
        self._client = rest_client
        self._game_name = game_name
        self._label = label
        self._session: GameSession | None = None

    async def start(self) -> GameSession:
        handle, intro = await self._client.start_session(self._game_name, self._label)
        session = GameSession(handle=handle, intro_text=str(intro or "").strip())
        self._session = session
        return session

    async def send(self, command: str) -> EngineTurn:
        # Log GameAPI request with command and session
        session = await self._require_session()
        log_gameapi_event({"stage": "request", "command": command, "pid": session.handle.pid})
        # Send action to engine and obtain raw JSON
        raw = await self._client.submit_action(session.handle.pid, command)
        # Extract transcript
        transcript = raw["data"].strip()
        # Parse heuristics
        parsed = self._parse_engine_data(transcript)
        # Log GameAPI response with parsed metadata - temporary logging checkpoint, to be removed later.
        log_gameapi_event({
            "stage": "response",
            "command": command,
            "pid": session.handle.pid,
            "response": raw,
            "metadata": parsed
        })
        # Log parsed metadata at GameAPI level - canonically log the entire gameapi EngineTurn object.
        log_gameapi_event({"stage": "parsed", "command": command, "pid": session.handle.pid, "metadata": parsed})
        # Build and return enriched turn object
        return EngineTurn(
            session=session,
            command=command,
            transcript=transcript,
            room_name=parsed.get("room_name"),
            score=parsed.get("score"),
            moves=parsed.get("moves"),
            inventory=parsed.get("inventory"),
            visible_items=parsed.get("visible_items"),
            description=parsed.get("description"),
            gameException=parsed.get("gameException", False),
            exceptionMessage=parsed.get("exceptionMessage"),
        )

    async def stop(self) -> None:
        if self._session is None:
            return
        try:
            await self._client.stop_session(self._session.handle.pid)
        finally:
            self._session = None

    async def close(self) -> None:
        await self._client.close()

    async def _require_session(self) -> GameSession:
        if self._session is None:
            return await self.start()
        return self._session


__all__ = ["GameAPI", "GameSession", "EngineTurn"]
