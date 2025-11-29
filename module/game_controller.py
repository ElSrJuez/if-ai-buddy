"""Thin game controller that wires configuration, logging, and the TUI.

The controller currently simulates turn responses until the REST helper and AI
buddy layers are reconnected. Keeping this file focused on orchestration makes it
simple to evolve toward the full design incrementally without entangling UI code
or API specifics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module import my_logging
from module.ui_helper import (
    AIStatus,
    EngineStatus,
    IFBuddyTUI,
    StatusSnapshot,
    create_app,
)


@dataclass(frozen=True)
class ControllerSettings:
    player_name: str
    default_game: str
    dfrotz_base_url: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ControllerSettings":
        missing = [
            key
            for key in ("player_name", "default_game", "dfrotz_base_url")
            if key not in config
        ]
        if missing:
            raise ValueError(f"Missing config keys: {', '.join(missing)}")
        return cls(
            player_name=str(config["player_name"] or "Adventurer"),
            default_game=str(config["default_game"] or ""),
            dfrotz_base_url=str(config["dfrotz_base_url"]),
        )


class GameController:
    """Owns session state and mediates between the TUI and game helpers."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.settings = ControllerSettings.from_config(config)
        self._moves = 0
        self._score = 0
        self._room = "Unknown"

        status = StatusSnapshot.default(
            player=self.settings.player_name, game=self.settings.default_game
        )
        self._app: IFBuddyTUI = create_app(
            initial_status=status,
            on_command=self._handle_command,
            on_player_rename=self._handle_player_rename,
            on_restart=self._handle_restart,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the Textual app."""
        self._queue_bootstrap_messages()
        my_logging.system_info("IF AI Buddy TUI starting")
        self._app.run()
        my_logging.system_info("IF AI Buddy TUI exited")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _queue_bootstrap_messages(self) -> None:
        def _render_intro() -> None:
            self._app.add_transcript_output(
                "Welcome! REST + AI helpers are still coming online, so you will see "
                "simulated responses for now."
            )
            self._app.add_narration(
                "Your buddy is awake and ready to narrate once the engine wiring is complete."
            )

        try:
            self._app.call_later(_render_intro)
        except AttributeError:
            _render_intro()

    def _handle_command(self, command: str) -> None:
        my_logging.log_player_input(command)
        self._set_engine_status(EngineStatus.BUSY)
        self._app.call_later(lambda: self._complete_fake_turn(command))

    def _complete_fake_turn(self, command: str) -> None:
        self._moves += 1
        self._app.add_transcript_output(
            f"(demo) The engine echoes: '{command}'. Real dfrotz plumbing arrives shortly."
        )
        self._app.add_narration(
            "For now, treat this as a smoke test of the UI. Actual narration will stream once the AI helper is wired."
        )
        self._app.update_status(moves=self._moves)
        self._set_engine_status(EngineStatus.READY)
        self._set_ai_status(AIStatus.READY)

    def _handle_player_rename(self) -> None:
        my_logging.system_info("Player rename requested (stub)")
        self._app.add_hint(
            "Player rename flow will prompt inside the TUI in a later iteration."
        )

    def _handle_restart(self) -> None:
        my_logging.system_info("Game restart requested")
        self._moves = 0
        self._score = 0
        self._app.reset_transcript()
        self._app.reset_narration()
        self._app.update_status(moves=0, score=0, room="Unknown")

    def _set_engine_status(self, status: EngineStatus) -> None:
        self._app.set_engine_status(status)

    def _set_ai_status(self, status: AIStatus) -> None:
        self._app.set_ai_status(status)


__all__ = ["GameController"]
