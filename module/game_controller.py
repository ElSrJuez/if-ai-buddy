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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from module import my_logging
from module.llm_narration_helper import CompletionsHelper
from module.narration_job_builder import NarrationJobBuilder, NarrationJobSpec
from module.game_api import GameAPI
from module.rest_helper import DfrotzClient
from module.game_engine_heuristics import parse_engine_facts
from module.config_registry import resolve_template_path
from module.game_memory import GameMemoryStore
from module.scene_image_service import SceneImageService
from module.ui_helper import (
    AIStatus,
    EngineStatus,
    SDStatus,
    SDPromptStatus,
    IFBuddyTUI,
    IFBuddyApp,
    StatusSnapshot,
)


class AITask(ABC):
    """Abstract base class for all AI tasks."""
    
    @abstractmethod
    async def execute(self) -> None:
        """Execute the AI task."""
        pass
    
    @abstractmethod
    def get_status_type(self) -> str:
        """Return status type: 'ai', 'sd_prompt', or 'sd'"""
        pass


class NarrationTask(AITask):
    """AI task for generating narration text."""
    
    def __init__(self, controller: 'GameController', job_spec: NarrationJobSpec, room: str):
        self.controller = controller
        self.job_spec = job_spec
        self.room = room
    
    async def execute(self) -> None:
        """Execute narration generation."""
        await self.controller._run_narration_job(self.job_spec, self.room)
    
    def get_status_type(self) -> str:
        return "ai"


class SceneImageTask(AITask):
    """AI task for generating scene images."""
    
    def __init__(self, controller: 'GameController', memory_context: dict[str, Any]):
        self.controller = controller
        self.memory_context = memory_context
    
    async def execute(self) -> None:
        """Execute scene image generation."""
        await self.controller._generate_and_show_scene_image(self.memory_context)
    
    def get_status_type(self) -> str:
        return "sd"


@dataclass(frozen=True)
class ControllerSettings:
    player_name: str
    default_game: str
    dfrotz_base_url: str
    ai_schema_path: str
    memory_db_path_template: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ControllerSettings":
        missing = [
            key
            for key in (
                "player_name",
                "default_game",
                "dfrotz_base_url",
                "memory_db_path_template",
            )
            if key not in config
        ]
        if missing:
            raise ValueError(f"Missing config keys: {', '.join(missing)}")

        # Load AI schema path (new key) with backward-compatible fallback
        schema_path = (
            config.get("ai_engine_schema_path")
            or config.get("response_schema_path")
            or "config/response_schema.json"
        )

        return cls(
            player_name=str(config["player_name"] or "Adventurer"),
            default_game=str(config["default_game"] or ""),
            dfrotz_base_url=str(config["dfrotz_base_url"]),
            ai_schema_path=str(schema_path),
            memory_db_path_template=str(config["memory_db_path_template"]),
        )





class GameController:
    """Owns session state and mediates between the TUI and game helpers."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.settings = ControllerSettings.from_config(config)
        self._player_name = self.settings.player_name
        self._project_root = Path(self.config.get("_project_root", Path(__file__).resolve().parents[1]))

        # Initialize async helpers
        self._rest_client: DfrotzClient | None = None
        self._game_api: GameAPI | None = None

        # Initialize memory store (persisted to disk)
        memory_db_path = self._resolve_memory_db_path(self._player_name)
        self._memory = GameMemoryStore(self._player_name, memory_db_path)
        
        # Initialize completions helper with injected LLM client
        schema_path = Path(self.settings.ai_schema_path)
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

        self._completions = CompletionsHelper(self.config, schema)
        self._narration_builder = NarrationJobBuilder(self.config)
        self._narration_tasks: set[asyncio.Task[Any]] = set()
        
        # AI task queue system
        self._ai_queue: asyncio.Queue[AITask] = asyncio.Queue()
        self._ai_worker_task: asyncio.Task[None] | None = None
        self._current_ai_status: str | None = None

        # Initialize scene image service
        self._scene_image_service = SceneImageService(self.config)
        self._current_room_for_images: str | None = None

        # Status tracking
        self._moves = 0
        self._score = 0
        self._room = "Unknown"
        self._status = StatusSnapshot.default(
            player=self._player_name, game=self.settings.default_game
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
        # Cancel AI worker
        if self._ai_worker_task and not self._ai_worker_task.done():
            self._ai_worker_task.cancel()
        
        # Async cleanup is handled by game_api context managers
        # No need for asyncio.run() here since the event loop is already shutting down
        if self._game_api:
            try:
                my_logging.system_debug("Game API cleanup skipped (async)")
            except Exception as exc:
                my_logging.system_debug(f"Cleanup error: {exc}")
        self._cancel_pending_narrations()

    def _queue_bootstrap_messages(self) -> None:
        """Queue initial intro messages."""
        def _render_intro() -> None:
            self._app.add_transcript_output(
                "Welcome to IF AI Buddy!\n\n"
                "Initializing game engine..."
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
                label=self._player_name,
            )
            session = await self._game_api.start()
            
            # Start AI worker
            self._ai_worker_task = asyncio.create_task(self._ai_worker())
            
            # Log the initial game intro as a transcript event (transaction zero)
            my_logging.log_player_output(session.intro_text)

            # Extract initial state (canonical heuristics output)
            facts = parse_engine_facts(session.intro_text)
            if facts.room_name:
                self._room = facts.room_name
            if facts.moves is not None:
                self._moves = facts.moves
            if facts.score is not None:
                self._score = facts.score

            # Render structured view (avoid dumping raw transcript/status header lines)
            self._render_engine_view_to_transcript(
                command=None,
                room_name=facts.room_name,
                description=facts.description,
                previous_room=None,
                fallback_transcript=session.intro_text,
                is_exception=facts.gameException,
                exception_message=facts.exceptionMessage,
            )

            # Turn 0: record intro facts before any narration/prompting.
            self._memory.update_from_engine_facts(
                facts,
                command="__start__",
                previous_room=None,
                transcript=session.intro_text,
            )
            self._update_status(moves=self._moves, score=self._score, room=self._room)

            narration_started = False
            if session.intro_text:
                context = self._memory.get_context_for_prompt()
                job_spec = self._narration_builder.build_job(
                    memory_context=context,
                    trigger="init",
                    latest_transcript=session.intro_text,
                )
                self._schedule_narration_job(job_spec, self._room)
                narration_started = True

            self._set_engine_status(EngineStatus.READY)
            if not narration_started:
                self._set_ai_status(AIStatus.IDLE)
        except Exception as exc:
            my_logging.system_debug(f"Async init error: {exc}")
            self._app.add_transcript_output(f"Error initializing: {exc}")
            self._set_engine_status(EngineStatus.ERROR)

    async def _ai_worker(self) -> None:
        """Single AI worker coroutine that processes all AI tasks sequentially."""
        my_logging.system_debug("AI worker started")
        
        try:
            while True:
                try:
                    # Get next task from queue
                    task = await self._ai_queue.get()
                    
                    # Update status based on task type
                    status_type = task.get_status_type()
                    self._current_ai_status = status_type
                    
                    if status_type == "ai":
                        self._set_ai_status(AIStatus.WORKING)
                    elif status_type == "sd_prompt":
                        self._set_sd_prompt_status(SDPromptStatus.WORKING)
                    elif status_type == "sd":
                        self._set_sd_status(SDStatus.GENERATING)
                    
                    # Execute the task
                    await task.execute()
                    
                    # Reset status to idle
                    if status_type == "ai":
                        self._set_ai_status(AIStatus.IDLE)
                    elif status_type == "sd_prompt":
                        self._set_sd_prompt_status(SDPromptStatus.IDLE)
                    elif status_type == "sd":
                        self._set_sd_status(SDStatus.IDLE)
                    
                    # Mark task as done
                    self._ai_queue.task_done()
                    self._current_ai_status = None
                    
                except asyncio.CancelledError:
                    my_logging.system_debug("AI worker cancelled")
                    break
                except Exception as exc:
                    # Reset status on error
                    if self._current_ai_status == "ai":
                        self._set_ai_status(AIStatus.ERROR)
                    elif self._current_ai_status == "sd_prompt":
                        self._set_sd_prompt_status(SDPromptStatus.ERROR)
                    elif self._current_ai_status == "sd":
                        self._set_sd_status(SDStatus.ERROR)
                    
                    my_logging.system_warn(f"AI worker task error: {exc}")
                    # Mark task as done even on error
                    self._ai_queue.task_done()
                    self._current_ai_status = None
                    
        except asyncio.CancelledError:
            my_logging.system_debug("AI worker shutdown")
        except Exception as exc:
            my_logging.system_warn(f"AI worker error: {exc}")

    def _handle_command(self, command: str) -> None:
        """Handle a player command."""
        command = command.strip()
        if not command:
            return
        if self._handle_local_command(command):
            return
        my_logging.log_player_input(command)
        self._set_engine_status(EngineStatus.BUSY)
        self._app.app.call_later(lambda: asyncio.create_task(self._async_play_turn(command)))

    def _handle_local_command(self, command: str) -> bool:
        """Handle controller-local commands (e.g., /player rename)."""
        lowered = command.lower()
        if lowered.startswith("/player "):
            new_name = command.split(" ", 1)[1].strip()
            if not new_name:
                self._app.add_hint("Usage: /player <new name>")
            else:
                self._apply_player_name_change(new_name)
            return True
        return False

    async def _async_play_turn(self, command: str) -> None:
        """Async execution of a turn: send command, get response, generate narration."""
        try:
            # Send action to game
            outcome = await self._game_api.send(command)
            transcript = outcome.transcript
            
            # Log transcript
            my_logging.log_player_output(transcript)

            previous_room = self._room

            # Render structured view (use already-parsed EngineTurn fields)
            self._render_engine_view_to_transcript(
                command=command,
                room_name=outcome.room_name,
                description=outcome.description,
                previous_room=previous_room,
                fallback_transcript=transcript,
                is_exception=outcome.gameException,
                exception_message=outcome.exceptionMessage,
            )

            # Memory uses canonical heuristics output
            facts = parse_engine_facts(transcript)
            if outcome.moves is not None:
                self._moves = outcome.moves
            if outcome.score is not None:
                self._score = outcome.score
            if outcome.room_name:
                self._room = outcome.room_name
                # Track room change for scene image generation (but don't trigger yet)
                room_changed = self._room != self._current_room_for_images
                if room_changed:
                    self._current_room_for_images = self._room

            self._memory.update_from_engine_facts(
                facts,
                command=command,
                previous_room=previous_room,
                transcript=transcript,
            )

            self._update_status(
                moves=self._moves,
                score=self._score,
                room=self._room,
            )

            context = self._memory.get_context_for_prompt()
            job_spec = self._narration_builder.build_job(
                memory_context=context,
                trigger="turn",
                latest_transcript=transcript,
            )
            self._schedule_narration_job(job_spec, self._room)
            
            # Trigger scene image generation AFTER narration is scheduled
            if room_changed:
                self._schedule_scene_image_generation()

            self._set_engine_status(EngineStatus.READY)

        except Exception as exc:
            my_logging.system_debug(f"Turn error: {exc}")
            self._app.add_transcript_output(f"Error: {exc}")
            self._set_engine_status(EngineStatus.ERROR)
            self._set_ai_status(AIStatus.ERROR)


    def _render_engine_view_to_transcript(
        self,
        *,
        command: str | None,
        room_name: str | None,
        description: str | None,
        previous_room: str | None,
        fallback_transcript: str,
        is_exception: bool,
        exception_message: str | None,
    ) -> None:
        """Render a clean, structured engine view in the transcript pane.

        This avoids duplicating UI-held fields (room/score/moves) that appear in raw
        engine transcripts while still showing the meaningful narrative text.
        """

        if command:
            self._app.add_transcript_output(
                f"[dim]{self._escape_markup(f'> {command}')}[/dim]"
            )

        if is_exception:
            msg = exception_message or "Engine error"
            self._app.add_transcript_output(f"[red]{self._escape_markup(msg)}[/red]")
            raw = (fallback_transcript or "").strip()
            if raw and raw != msg:
                self._app.add_transcript_output(self._escape_markup(raw))
            self._app.add_transcript_output("")
            return

        show_room = bool(room_name) and (previous_room is None or room_name != previous_room)
        if show_room and room_name:
            self._app.add_transcript_output(f"[bold]{self._escape_markup(room_name)}[/bold]")

        body = (description or "").strip()
        if body:
            self._app.add_transcript_output(self._escape_markup(body))
        else:
            # If heuristics produced no description, show the raw transcript rather than
            # silently dropping engine output.
            raw = (fallback_transcript or "").strip()
            if raw:
                self._app.add_transcript_output(self._escape_markup(raw))

        self._app.add_transcript_output("")

    @staticmethod
    def _escape_markup(text: str) -> str:
        """Escape content so it can't be interpreted as Textual markup."""
        if not text:
            return ""
        return text.replace("\\", "\\\\").replace("[", "\\[")


    def _handle_player_rename(self) -> None:
        """Handle player rename request."""
        self._app.add_hint(
            "Player rename: type /player <new name> in the command box to update logs and status."
        )
        my_logging.system_info("Player rename prompt displayed")

    def _handle_restart(self) -> None:
        """Handle game restart request: reset session and memory."""
        my_logging.system_info("Game restart requested")
        self._moves = 0
        self._score = 0
        self._room = "Unknown"
        self._cancel_pending_narrations()
        self._memory.reset()
        self._app.reset_transcript()
        self._app.reset_narration()
        self._update_status(moves=0, score=0, room="Unknown")
        self._initialize_session()

    def _apply_player_name_change(self, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            self._app.add_hint("Player name cannot be empty.")
            return
        if new_name == self._player_name:
            self._app.add_hint(f"Player already named {new_name}.")
            return

        old_name = self._player_name
        self._player_name = new_name
        my_logging.system_info(f"Renaming player from '{old_name}' to '{new_name}'")
        
        # Close old memory and create new player-scoped memory
        try:
            self._memory.close()
            memory_db_path = self._resolve_memory_db_path(new_name)
            self._memory = GameMemoryStore(new_name, memory_db_path)
        except Exception as exc:
            self._player_name = old_name
            my_logging.system_warn(f"Failed to reset memory for new player: {exc}")
            self._app.add_hint("Unable to initialize memory for new player; see system log.")
            return
        
        try:
            my_logging.update_player_logs(new_name)
        except Exception as exc:
            self._player_name = old_name
            my_logging.system_warn(f"Failed to update player logs: {exc}")
            self._app.add_hint("Unable to update logs for new player; see system log.")
            return

        # Reset game state and restart session
        self._moves = 0
        self._score = 0
        self._room = "Unknown"
        self._app.reset_transcript()
        self._app.reset_narration()
        self._status = self._status.with_updates(player=new_name)
        self._app.update_status(self._status)
        self._app.add_hint(f"Player renamed to {new_name}. Restarting session...")
        self._initialize_session()

    def _resolve_memory_db_path(self, player_name: str) -> Path:
        return resolve_template_path(
            self.config,
            "memory_db_path_template",
            {"player": player_name},
            project_root=self._project_root,
        )

    def _cancel_pending_narrations(self) -> None:
        if not self._narration_tasks:
            return
        for task in list(self._narration_tasks):
            task.cancel()
        self._narration_tasks.clear()
        self._active_narration_jobs = 0

    def _schedule_scene_image_generation(self) -> None:
        """Submit scene image generation task to AI queue."""
        memory_context = self._memory.get_context_for_prompt()
        task = SceneImageTask(self, memory_context)
        
        # Submit to queue (will run sequentially after any pending AI tasks)
        try:
            self._ai_queue.put_nowait(task)
            my_logging.system_debug("Scene image generation task queued")
        except asyncio.QueueFull:
            my_logging.system_warn("AI task queue is full, skipping scene image generation")

    async def _generate_and_show_scene_image(self, memory_context: dict[str, Any]) -> None:
        """Generate scene image and display in popup."""
        try:
            # Set up callbacks for SD prompt generation phases
            self._scene_image_service._on_sd_prompt_start = lambda: self._set_sd_prompt_status(SDPromptStatus.WORKING)
            self._scene_image_service._on_sd_prompt_end = lambda: self._set_sd_prompt_status(SDPromptStatus.IDLE)
            
            result = await self._scene_image_service.generate_scene_image(
                room_name=self._room,
                memory_context=memory_context
            )
            
            # result is (image_data, metadata_dict)
            image_data, metadata = result
            self._app.show_scene_image(
                image_path=metadata.get("image_path"),
                prompt_text=metadata.get("prompt", "No prompt available"),
                on_thumbs_down=self._on_image_thumbs_down,
                on_regenerate=self._on_image_regenerate
            )
            
        except Exception as exc:
            my_logging.system_warn(f"Scene image generation failed: {exc}")
            # Show popup with no image but with regenerate option
            self._app.show_scene_image(
                image_path=None,
                prompt_text=f"Image generation failed: {exc}",
                on_thumbs_down=self._on_image_thumbs_down,
                on_regenerate=self._on_image_regenerate
            )
            # Re-raise exception so AI worker can handle status
            raise

    def _on_image_thumbs_down(self) -> None:
        """Handle thumbs down feedback on scene image."""
        my_logging.system_info("User provided thumbs down feedback on scene image")
        # TODO: Implement feedback collection/storage

    def _on_image_regenerate(self) -> None:
        """Handle regenerate request for scene image."""
        my_logging.system_info("User requested scene image regeneration")
        self._schedule_scene_image_generation()

    def _schedule_narration_job(
        self,
        job_spec: NarrationJobSpec,
        room_snapshot: str,
    ) -> None:
        """Submit narration task to AI queue."""
        task = NarrationTask(self, job_spec, room_snapshot)
        
        # Submit to queue (will run sequentially)
        try:
            self._ai_queue.put_nowait(task)
            my_logging.system_debug("Narration task queued")
        except asyncio.QueueFull:
            my_logging.system_warn("AI task queue is full, skipping narration")

    async def _run_narration_job(
        self,
        job_spec: NarrationJobSpec,
        room_snapshot: str,
    ) -> dict[str, Any]:
        self._app.begin_narration_stream()
        result = await self._completions.stream_narration(
            job_spec,
            on_chunk=self._app.add_narration_stream_chunk,
        )
        payload = result.get("payload", {})
        narration = payload.get("narration")
        self._app.end_narration_stream(narration)
        if narration:
            self._memory.append_narration(room_snapshot, narration)
        return result

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

    def _set_sd_status(self, status: SDStatus) -> None:
        """Set SD engine status in UI."""
        self._update_status(sd_status=status)

    def _set_sd_prompt_status(self, status: SDPromptStatus) -> None:
        """Set SD Prompt Engine status in UI."""
        self._update_status(sd_prompt_status=status)



__all__ = ["GameController"]
