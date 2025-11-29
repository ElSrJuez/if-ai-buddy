"""High-level game orchestrator focused solely on the dfrotz engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from module.game_api import GameAPI, TurnOutcome
from module.rest_helper import DfrotzClient, RestError


@dataclass
class TurnResult:
    command: str
    transcript: str | None
    narration: str | None = None
    payload: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    should_exit: bool = False


class GameController:
    """Wraps GameAPI and manages player/session identity prompts."""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        rest_client: DfrotzClient,
        game_name: str | None = None,
        session_label: str | None = None,
    ) -> None:
        self._config = config
        self._default_player = str(config["player_name"])
        self.player_name = self._prompt_player_name()
        self.game_name = game_name or str(config["default_game"])
        self._rest_client = rest_client
        self._session_label = session_label
        label = session_label or self.player_name
        self._api = GameAPI(self._rest_client, game_name=self.game_name, label=label)
        self._bootstrapped = False

    def _prompt_player_name(self) -> str:
        prompt = f"Enter player name [{self._default_player}]: "
        try:
            response = input(prompt)
        except EOFError:
            response = ""
        name = response.strip()
        return name or self._default_player

    async def bootstrap(self) -> str:
        session = await self._api.start()
        self._bootstrapped = True
        return session.intro_text

    async def restart(self, player_name: str) -> str:
        new_name = player_name.strip() or self.player_name
        await self._api.stop()
        self.player_name = new_name
        self._config["player_name"] = new_name
        label = self._session_label or self.player_name
        self._api = GameAPI(self._rest_client, game_name=self.game_name, label=label)
        self._bootstrapped = False
        return await self.bootstrap()

    async def play_turn(self, command: str) -> TurnResult:
        command = command.strip()
        if not command:
            return TurnResult(command=command, transcript=None, error="Empty command")

        if command.lower() in {"quit", "/quit"}:
            await self.shutdown()
            return TurnResult(
                command=command,
                transcript=None,
                narration="Session ended.",
                should_exit=True,
            )

        if not self._bootstrapped:
            await self.bootstrap()

        try:
            outcome = await self._api.send(command)
        except RestError as exc:
            return TurnResult(command=command, transcript=None, error=str(exc))

        diagnostics = {
            "pid": outcome.session.handle.pid,
            "command": command,
        }
        return TurnResult(
            command=command,
            transcript=outcome.transcript,
            diagnostics=diagnostics,
        )

    async def shutdown(self) -> None:
        await self._api.stop()
        await self._rest_client.close()


__all__ = ["GameController", "TurnResult"]
