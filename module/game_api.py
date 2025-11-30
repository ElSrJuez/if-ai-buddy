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
    # metadata such as pid and HTTP status can be added later

class GameAPI:
    def _parse_engine_data(self, transcript: str) -> dict[str, Any]:
        # Simple heuristics parser (to be expanded/refined)
        room = None
        for line in transcript.splitlines():
            l=line.strip()
            if l and l[0].isupper() and (l.isupper() or ' ' in l):
                room = l
                break
        # Score/moves extraction
        score = None; moves = None
        import re
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
        description = None
        return {
            'room_name': room,
            'score': score,
            'moves': moves,
            'inventory': inventory,
            'visible_items': visible_items,
            'description': description,
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
        # Log GameAPI response with parsed metadata
        log_gameapi_event({
            "stage": "response",
            "command": command,
            "pid": session.handle.pid,
            "response": raw,
            "metadata": parsed
        })
        # Log parsed metadata at GameAPI level
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
