"""Thin game controller that wires configuration, logging, and the TUI.

The controller orchestrates:
  - REST client + GameAPI for dfrotz interaction
  - GameMemoryStore for episodic and state tracking
  - CompletionsHelper for AI narration
  - IFBuddyTUI for Textual UI integration
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from module import my_logging
from module.completions_helper import CompletionsHelper
from module.game_api import GameAPI
from module.rest_helper import DfrotzClient
from module.ui_helper import (
    AIStatus,
    EngineStatus,
    IFBuddyTUI,
    IFBuddyApp,
    StatusSnapshot,
)


@dataclass(frozen=True)
class ControllerSettings:
    player_name: str
    default_game: str
    dfrotz_base_url: str
    response_schema_path: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ControllerSettings":
        missing = [
            key
            for key in ("player_name", "default_game", "dfrotz_base_url")
            if key not in config
        ]
        if missing:
            raise ValueError(f"Missing config keys: {', '.join(missing)}")

        # Load response schema
        schema_path = config.get("response_schema_path", "config/response_schema.json")

        return cls(
            player_name=str(config["player_name"] or "Adventurer"),
            default_game=str(config["default_game"] or ""),
            dfrotz_base_url=str(config["dfrotz_base_url"]),
            response_schema_path=schema_path,
        )


class GameController:
    """Owns session state and mediates between the TUI and game helpers."""

    def __init__(self, config: dict[str, Any], llm_client: Any) -> None:
        self.config = config
        self.settings = ControllerSettings.from_config(config)
        self._llm_client = llm_client

        # Initialize async helpers
        self._rest_client: DfrotzClient | None = None
        self._game_api: GameAPI | None = None

        # Initialize memory
        # placeholder
        
        # Initialize completions helper with injected LLM client
        schema_path = Path(self.settings.response_schema_path)
        if not schema_path.is_absolute():
            schema_path = Path(__file__).parent.parent / schema_path
        
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            my_logging.system_warn(f"Response schema not found at {schema_path}, using minimal schema")
            schema = {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "game_intent": {"type": "string"},
                    "game_meta_intent": {"type": "string"},
                    "hidden_next_command": {"type": "string"},
                    "hidden_next_command_confidence": {"type": "integer"},
                },
                "required": ["narration"],
            }

        self._completions = CompletionsHelper(self.config, schema, self._llm_client)

        # Status tracking
        self._moves = 0
        self._score = 0
        self._room = "Unknown"
        self._status = StatusSnapshot.default(
            player=self.settings.player_name, game=self.settings.default_game
        )

        # Create TUI and underlying Textual App
        self._app = IFBuddyTUI(
            app=None,
            initial_status=self._status,
            on_command=self._handle_command,
            on_player_rename=self._handle_player_rename,
            on_restart=self._handle_restart,
        )
        self._textual_app = IFBuddyApp(self._app)
        self._app._app = self._textual_app

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the Textual app."""
        self._queue_bootstrap_messages()
        my_logging.system_info("IF AI Buddy TUI starting")
        try:
            self._app.app.run()
        finally:
            self._cleanup()
        my_logging.system_info("IF AI Buddy TUI exited")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        """Clean up resources."""
        # Async cleanup is handled by game_api context managers
        # No need for asyncio.run() here since the event loop is already shutting down
        if self._game_api:
            try:
                my_logging.system_debug("Game API cleanup skipped (async)")
            except Exception as exc:
                my_logging.system_debug(f"Cleanup error: {exc}")

    def _queue_bootstrap_messages(self) -> None:
        """Queue initial intro messages."""
        def _render_intro() -> None:
            self._app.add_transcript_output(
                "Welcome to IF AI Buddy!\n\n"
                "Initializing game engine..."
            )
            self._app.add_narration(
                "Connecting to the game world..."
            )
            # Initialize session
            self._app.app.call_later(self._initialize_session)

        try:
            self._app.app.call_later(_render_intro)
        except AttributeError:
            _render_intro()

    def _initialize_session(self) -> None:
        """Schedule async session initialization."""
        try:
            self._app.app.call_later(lambda: asyncio.create_task(self._async_init_session()))
        except Exception as exc:
            my_logging.system_debug(f"Session init error: {exc}")
            self._app.add_transcript_output(f"Error initializing: {exc}")
            self._set_engine_status(EngineStatus.ERROR)

    async def _async_init_session(self) -> None:
        """Async initialization of game session."""
        try:
            self._rest_client = DfrotzClient(self.settings.dfrotz_base_url)
            self._game_api = GameAPI(
                self._rest_client,
                game_name=self.settings.default_game,
                label=self.settings.player_name,
            )
            session = await self._game_api.start()
            
            # Add intro text to transcript
            if session.intro_text:
                self._app.add_transcript_output(session.intro_text)
            
            # Extract initial state
            # placeholder
            
            # Extract room
            self._room = self._extract_room(session.intro_text)
            self._update_status(room=self._room)
            
            # Add narration
            self._app.add_narration("Let's begin your adventure...")
            
            self._set_engine_status(EngineStatus.READY)
            self._set_ai_status(AIStatus.IDLE)
        except Exception as exc:
            my_logging.system_debug(f"Async init error: {exc}")
            self._app.add_transcript_output(f"Error initializing: {exc}")
            self._set_engine_status(EngineStatus.ERROR)

    def _handle_command(self, command: str) -> None:
        """Handle a player command."""
        my_logging.log_player_input(command)
        self._set_engine_status(EngineStatus.BUSY)
        self._app.app.call_later(lambda: asyncio.create_task(self._async_play_turn(command)))

    async def _async_play_turn(self, command: str) -> None:
        """Async execution of a turn: send command, get response, generate narration."""
        try:
            # Send action to game
            outcome = await self._game_api.send(command)
            transcript = outcome.transcript
            
            # Log transcript
            my_logging.log_player_output(transcript)
            
            # Add to transcript
            self._app.add_transcript_output(transcript)
            
            # Update memory
            # placeholder for calling memory module
            
            # Update metrics and room from parsed EngineTurn
            if outcome.moves is not None:
                self._moves = outcome.moves
            if outcome.score is not None:
                self._score = outcome.score
            if outcome.room_name:
                self._room = outcome.room_name

            # Update status
            self._update_status(
                moves=self._moves,
                score=self._score,
                room=self._room,
            )            # Generate narration
            self._set_ai_status(AIStatus.WORKING)
            try:
                context = self._memory.get_context_for_prompt()
                result = self._completions.run(transcript, context)
                
                payload = result.get("payload", {})
                if isinstance(payload, dict):
                    narration = payload.get("narration", "...")
                    self._app.add_narration(narration)
                
                self._set_ai_status(AIStatus.READY)
            except Exception as narr_exc:
                my_logging.system_debug(f"Narration error: {narr_exc}")
                self._app.add_narration(f"(Narration unavailable)")
                self._set_ai_status(AIStatus.ERROR)
            
            self._set_engine_status(EngineStatus.READY)

        except Exception as exc:
            my_logging.system_debug(f"Turn error: {exc}")
            self._app.add_transcript_output(f"Error: {exc}")
            self._set_engine_status(EngineStatus.ERROR)
            self._set_ai_status(AIStatus.ERROR)


    def _handle_player_rename(self) -> None:
        """Handle player rename request."""
        my_logging.system_info("Player rename requested (not yet implemented)")
        self._app.add_hint(
            "Player rename will be available in a future iteration."
        )

    def _handle_restart(self) -> None:
        """Handle game restart request."""
        my_logging.system_info("Game restart requested")
        self._moves = 0
        self._score = 0
        self._room = "Unknown"
        self._memory.reset()
        self._app.reset_transcript()
        self._app.reset_narration()
        self._update_status(moves=0, score=0, room="Unknown")
        self._initialize_session()

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _update_status(self, **kwargs) -> None:
        """Update cached status snapshot and push to UI."""
        self._status = self._status.with_updates(**kwargs)
        self._app.update_status(self._status)

    def _set_engine_status(self, status: EngineStatus) -> None:
        """Set engine status in UI."""
        self._update_status(engine_status=status)

    def _set_ai_status(self, status: AIStatus) -> None:
        """Set AI status in UI."""
        self._update_status(ai_status=status)

    def _parse_game_metrics(self, transcript: str) -> tuple[int | None, int | None]:
        """Extract moves and score from transcript."""
        moves = None
        score = None
        
        # Pattern: "Score: 100 Moves: 42" or "Score: 100\nMoves: 42"
        match = re.search(r"Score:\s*(\d+).*?Moves:\s*(\d+)", transcript, re.DOTALL)
        if match:
            score = int(match.group(1))
            moves = int(match.group(2))
        
        return moves, score

    def _extract_room(self, transcript: str) -> str | None:
        """Extract room name from transcript."""
        for line in transcript.split("\n"):
            line = line.strip()
            if line and len(line) > 2 and line[0].isupper():
                # Heuristic: room names are capitalized
                if line.isupper() or (line[0].isupper() and " " in line):
                    return line
        return None


__all__ = ["GameController"]
