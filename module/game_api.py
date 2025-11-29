"""Lean wrapper around the dfrotz REST engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module.rest_helper import DfrotzClient, SessionHandle


@dataclass
class GameSession:
    handle: SessionHandle
    intro_text: str


@dataclass
class TurnOutcome:
    session: GameSession
    command: str
    transcript: str
    raw_response: dict[str, Any]


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
        return session

    async def send(self, command: str) -> TurnOutcome:
        session = await self._require_session()
        raw = await self._client.submit_action(session.handle.pid, command)
        transcript = str(raw.get("data", "") or "").strip()
        return TurnOutcome(session=session, command=command, transcript=transcript, raw_response=raw)

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


__all__ = ["GameAPI", "GameSession", "TurnOutcome"]
