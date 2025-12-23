"""Lean wrapper around the dfrotz REST engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module.game_engine_heuristics import (
    EngineMetadata,
    PlayerStateSnapshot,
    as_dict as facts_as_dict,
    parse_engine_facts,
)
from module.rest_helper import DfrotzClient, RestResult, SessionHandle
from module.my_logging import log_gameapi_event


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
    metadata: EngineMetadata | None = None
    player_state: PlayerStateSnapshot | None = None
    # metadata such as pid and HTTP status can be added later

class GameAPI:

    def __init__(self, rest_client: DfrotzClient, *, game_name: str, label: str) -> None:
        self._client = rest_client
        self._game_name = game_name
        self._label = label
        self._session: GameSession | None = None

    async def start(self) -> GameSession:
        handle, intro = await self._client.start_session(self._game_name, self._label)
        session = GameSession(handle=handle, intro_text=str(intro or "").strip())
        self._session = session
        parsed = parse_engine_facts(session.intro_text)
        log_gameapi_event({
            "stage": "parsed",
            "command": "<init>",
            "pid": session.handle.pid,
            "metadata": facts_as_dict(parsed),
        })

        return session

    async def send(self, command: str) -> EngineTurn:
        session = await self._require_session()
        rest_result = await self._client.submit_action(session.handle.pid, command)
        payload = rest_result.response
        transcript = str(payload.get("data", "")).strip()
        facts = parse_engine_facts(transcript)
        pid = None
        pid_value = payload.get("pid")
        if isinstance(pid_value, int):
            pid = pid_value
        elif isinstance(pid_value, str) and pid_value.isdigit():
            pid = int(pid_value)
        metadata = EngineMetadata(
            pid=pid,
            status_code=rest_result.status_code,
            timestamp=rest_result.timestamp,
        )
        log_gameapi_event({
            "stage": "parsed",
            "command": command,
            "pid": metadata.pid,
            "status_code": metadata.status_code,
            "timestamp": metadata.timestamp,
            "metadata": facts_as_dict(facts),
        })
        return EngineTurn(
            session=session,
            command=command,
            transcript=transcript,
            room_name=facts.room_name,
            score=facts.score,
            moves=facts.moves,
            inventory=facts.inventory,
            visible_items=facts.visible_items,
            description=facts.description,
            gameException=facts.gameException,
            exceptionMessage=facts.exceptionMessage,
            metadata=metadata,
            player_state=facts.player_state,
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
