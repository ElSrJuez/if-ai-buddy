"""Textual TUI for IF AI Buddy — two-column layout with game transcript and narration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from module import my_config, my_logging

from textual.app import RenderableType
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import (
    Header,
    Footer,
    Input,
    RichLog,
    Static,
    Button,
)
from textual.reactive import reactive
from .scene_image_popup import SceneImagePopup

# This is essential to disable rich's spammy error handler. This is necessary to host here, because this undesired behavior is triggered by the textual imports.
import sys
sys.excepthook = sys.__excepthook__

class AIStatus(Enum):
    """AI companion status."""

    IDLE = "Idle"
    WORKING = "Working"
    READY = "Ready"
    ERROR = "Error"


class EngineStatus(Enum):
    """Game engine status."""

    IDLE = "Idle"
    BUSY = "Busy"
    READY = "Ready"
    ERROR = "Error"


class SDStatus(Enum):
    """Stable Diffusion engine status."""

    IDLE = "Idle"
    GENERATING = "Generating"
    READY = "Ready"
    ERROR = "Error"


class SDPromptStatus(Enum):
    """SD Prompt Engine status (LLM generating diffusion prompts)."""

    IDLE = "Idle"
    WORKING = "Working"
    READY = "Ready"
    ERROR = "Error"


@dataclass(frozen=True)
class StatusSnapshot:
    """Immutable snapshot of game and AI status."""

    player: str
    game: str
    room: str = "Unknown"
    moves: int = 0
    score: int = 0
    engine_status: EngineStatus = EngineStatus.IDLE
    ai_status: AIStatus = AIStatus.IDLE
    sd_status: SDStatus = SDStatus.IDLE
    sd_prompt_status: SDPromptStatus = SDPromptStatus.IDLE

    @classmethod
    def default(cls, player: str, game: str) -> StatusSnapshot:
        return cls(player=player, game=game)

    def with_updates(
        self,
        player: str | None = None,
        game: str | None = None,
        room: str | None = None,
        moves: int | None = None,
        score: int | None = None,
        engine_status: EngineStatus | None = None,
        ai_status: AIStatus | None = None,
        sd_status: SDStatus | None = None,
        sd_prompt_status: SDPromptStatus | None = None,
    ) -> StatusSnapshot:
        """Return a new snapshot with updated fields."""
        return StatusSnapshot(
            player=player if player is not None else self.player,
            game=game if game is not None else self.game,
            room=room if room is not None else self.room,
            moves=moves if moves is not None else self.moves,
            score=score if score is not None else self.score,
            engine_status=engine_status if engine_status is not None else self.engine_status,
            ai_status=ai_status if ai_status is not None else self.ai_status,
            sd_status=sd_status if sd_status is not None else self.sd_status,
            sd_prompt_status=sd_prompt_status if sd_prompt_status is not None else self.sd_prompt_status,
        )


class TranscriptLog(Static):
    """Left column: scrollable game transcript."""

    DEFAULT_CSS = """
    TranscriptLog {
        height: 1fr;
        border: solid $primary;
        overflow-y: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._log = RichLog(markup=True, highlight=False, wrap=True)

    def compose(self) -> ComposeResult:
        yield self._log

    def add_output(self, text: str) -> None:
        """Add text to the transcript log."""
        self._log.write(text)

    def reset(self) -> None:
        """Clear all transcript content."""
        self._log.clear()
        my_logging.system_debug("Transcript log cleared")


class NarrationPanel(Static):
    """Right column showing narration history and hints."""

    DEFAULT_CSS = """
    NarrationPanel {
        height: 1fr;
        border: solid $secondary;
        overflow-y: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._streaming: bool = False
        self._stream_buffer: str = ""
        self._stream_bg: str | None = None
        self._alternate_bg: bool = False
        self._lines: list[str] = []
        self._narration_log = RichLog(markup=True, highlight=False, wrap=True)

    def _next_bg(self) -> str:
        """Return the next background color for a new narration block."""
        bg = DEFAULT_NARRATION_BG_A if not self._alternate_bg else DEFAULT_NARRATION_BG_B
        self._alternate_bg = not self._alternate_bg
        return bg

    @staticmethod
    def _escape_markup(text: str) -> str:
        """Escape text so it can't be interpreted as Textual markup.

        Textual markup uses square brackets; escape '[' as documented.
        """
        if not text:
            return ""
        # Escape backslashes first so our "\\[" stays intact.
        return text.replace("\\", "\\\\").replace("[", "\\[")

    def _wrap_block(self, *, bg: str, text: str) -> str:
        escaped = self._escape_markup(text)
        # Textual docs: background via [on <color>]...[/]
        return f"[on {bg}]{escaped}[/]"

    def compose(self) -> ComposeResult:
        yield self._narration_log

    def _refresh(self) -> None:
        self._narration_log.clear()
        for line in self._lines:
            self._narration_log.write(line)

    def begin_stream(self) -> None:
        """Signal that streaming is starting."""
        self._streaming = True
        self._stream_buffer = ""
        self._stream_bg = self._next_bg()
        self._lines.append(self._wrap_block(bg=self._stream_bg, text=""))
        self._refresh()

    def append_stream(self, text: str) -> None:
        """Append streamed narration text directly to the history log."""
        if not text:
            return
        self._stream_buffer += text
        bg = self._stream_bg or DEFAULT_NARRATION_BG_A
        if self._lines:
            self._lines[-1] = self._wrap_block(bg=bg, text=self._stream_buffer)
        else:
            self._lines.append(self._wrap_block(bg=bg, text=self._stream_buffer))
        self._refresh()

    def end_stream(self, final_text: str | None = None) -> None:
        """Finalize streaming by recording any leftover narration."""
        bg = self._stream_bg or DEFAULT_NARRATION_BG_A
        if final_text and not self._stream_buffer:
            self._lines.append(self._wrap_block(bg=bg, text=final_text.strip()))
        elif final_text and self._lines:
            self._lines[-1] = self._wrap_block(bg=bg, text=final_text.strip())
        if self._lines and not self._lines[-1].strip():
            self._lines.pop()
        self._streaming = False
        self._stream_buffer = ""
        self._stream_bg = None
        self._refresh()

    def add_narration(self, text: str) -> None:
        """Add narration to the panel."""
        bg = self._next_bg()
        self._lines.append(self._wrap_block(bg=bg, text=text))
        self._refresh()

    def add_hint(self, text: str) -> None:
        """Add a hint or guidance line."""
        # Hints do not affect narration alternation.
        escaped = self._escape_markup(text)
        self._lines.append(f"[dim]{escaped}[/dim]")
        self._refresh()

    def reset(self) -> None:
        """Clear all narration content."""
        self._lines.clear()
        self._stream_buffer = ""
        self._streaming = False
        self._stream_bg = None
        self._alternate_bg = False
        self._refresh()
        my_logging.system_debug("Narration panel cleared")


# Config-driven defaults
DEFAULT_PLAYER = my_config.get_config_value("player_name", "Adventurer")
DEFAULT_GAME = my_config.get_config_value("default_game", "Unknown")
DEFAULT_PLACEHOLDER = my_config.get_config_value("command_input_placeholder", "Enter command...")
DEFAULT_NARRATION_BG_A = my_config.get_config_value("ui_narration_bg_color_a", "#202020")
DEFAULT_NARRATION_BG_B = my_config.get_config_value("ui_narration_bg_color_b", "#1a1a1a")

# Log resolved defaults
my_logging.system_info(
    f"UI defaults resolved player={DEFAULT_PLAYER}, game={DEFAULT_GAME}, placeholder='{DEFAULT_PLACEHOLDER}'"
)

class StatusBar(Static):
    """Footer status bar showing player, game, room, moves, score, and status."""

    DEFAULT_CSS = """
    StatusBar {
        height: auto;
        border-top: solid $primary;
        background: $surface;
        padding: 0 1;
    }
    """

    status: reactive[StatusSnapshot] = reactive(
        StatusSnapshot.default(DEFAULT_PLAYER, DEFAULT_GAME)
    )

    def __init__(self) -> None:
        super().__init__()
        self.on_player_click: Callable[[], None] | None = None

    def render(self) -> RenderableType:
        """Render the status bar with current values."""
        s = self.status
        engine_color = self._status_color(s.engine_status)
        ai_color = self._status_color(s.ai_status)
        sd_color = self._status_color(s.sd_status)
        sd_prompt_color = self._status_color(s.sd_prompt_status)
        return (
            f"[bold]{s.player}[/bold] | "
            f"Game: {s.game} | "
            f"Room: {s.room} | "
            f"Moves: {s.moves} Score: {s.score} | "
            f"[{engine_color}]Engine: {s.engine_status.value}[/{engine_color}] | "
            f"[{ai_color}]AI: {s.ai_status.value}[/{ai_color}] | "
            f"[{sd_color}]SD: {s.sd_status.value}[/{sd_color}] | "
            f"[{sd_prompt_color}]SD Prompt: {s.sd_prompt_status.value}[/{sd_prompt_color}]"
        )

    def _status_color(self, status: EngineStatus | AIStatus | SDStatus | SDPromptStatus) -> str:
        """Return color code for a status enum."""
        my_logging.system_debug(f"Status color chosen for {status}: calculating")
        if isinstance(status, EngineStatus):
            if status == EngineStatus.ERROR:
                return "red"
            elif status == EngineStatus.BUSY:
                return "blue"
            elif status == EngineStatus.READY:
                return "green"
            else:
                return "dim"
        elif isinstance(status, SDStatus):
            if status == SDStatus.ERROR:
                return "red"
            elif status == SDStatus.GENERATING:
                return "blue"
            elif status == SDStatus.READY:
                return "green"
            else:
                return "dim"
        else:  # AIStatus
            if status == AIStatus.ERROR:
                return "red"
            elif status == AIStatus.WORKING:
                return "blue"
            elif status == AIStatus.READY:
                return "green"
            else:
                return "dim"

    def update_status(self, snapshot: StatusSnapshot) -> None:
        """Update the status snapshot and trigger re-render."""
        self.status = snapshot
        my_logging.system_info(
            f"Status updated: player={snapshot.player}, room={snapshot.room}, moves={snapshot.moves}, score={snapshot.score}, engine={snapshot.engine_status.name}, ai={snapshot.ai_status.name}, sd={snapshot.sd_status.name}, sd_prompt={snapshot.sd_prompt_status.name}"
        )


class CommandInput(Static):
    """Footer input field for player commands."""

    DEFAULT_CSS = """
    CommandInput {
        height: auto;
        border-top: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, on_submit: Callable[[str], None]) -> None:
        super().__init__()
        self.on_submit = on_submit
        self._input: Input | None = None

    def compose(self) -> ComposeResult:
        self._input = Input(id="command_input", placeholder=DEFAULT_PLACEHOLDER)
        yield self._input

    def on_mount(self) -> None:
        """Focus the input field on mount."""
        if self._input:
            self._input.focus()
            my_logging.system_debug("Command input focused")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission."""
        command = event.value.strip()
        if command and self._input:
            self.on_submit(command)
            self._input.value = ""
            self._input.focus()


class IFBuddyTUI:
    """Wraps a Textual app instance with game-specific methods."""

    def __init__(
        self,
        app,
        initial_status: StatusSnapshot,
        on_command: Callable[[str], None],
        on_player_rename: Callable[[], None],
        on_restart: Callable[[], None],
        on_show_scene_image: Callable[[], None],
        on_thumbs_down_prompt: Callable[[], None] | None = None,
        on_thumbs_down_image: Callable[[], None] | None = None,
    ) -> None:
        self._app = app
        # status snapshot initialization and updates are delegated to the controller
        self._on_command = on_command
        self._on_player_rename = on_player_rename
        self._on_restart = on_restart
        self._on_show_scene_image = on_show_scene_image
        self._on_thumbs_down_prompt = on_thumbs_down_prompt
        self._on_thumbs_down_image = on_thumbs_down_image

        # External viewer process tracking (singleton)
        self._viewer_proc = None
        self._viewer_temp_path: str | None = None

        # Widgets will be set up by the app
        self.transcript_log: TranscriptLog | None = None
        self.narration_panel: NarrationPanel | None = None
        self.status_bar: StatusBar | None = None
        self.command_input: CommandInput | None = None

    def add_transcript_output(self, text: str) -> None:
        """Add text to the game transcript (left column)."""
        if self.transcript_log:
            self.transcript_log.add_output(text)

    def add_narration(self, text: str) -> None:
        """Add narration to the right panel."""
        if self.narration_panel:
            self.narration_panel.add_narration(text)

    def begin_narration_stream(self) -> None:
        if self.narration_panel:
            self.narration_panel.begin_stream()

    def add_narration_stream_chunk(self, text: str) -> None:
        if self.narration_panel:
            self.narration_panel.append_stream(text)

    def end_narration_stream(self, final_text: str | None = None) -> None:
        if self.narration_panel:
            self.narration_panel.end_stream(final_text)

    def add_hint(self, text: str) -> None:
        """Add a hint/guidance to the narration panel."""
        if self.narration_panel:
            self.narration_panel.add_hint(text)

    def reset_transcript(self) -> None:
        """Clear the game transcript."""
        if self.transcript_log:
            self.transcript_log.reset()

    def reset_narration(self) -> None:
        """Clear the narration panel."""
        if self.narration_panel:
            self.narration_panel.reset()

    def update_status(self, snapshot: StatusSnapshot) -> None:
        """Apply a full status snapshot from controller to the status bar."""
        if self.status_bar:
            self.status_bar.update_status(snapshot)

    def show_scene_image(self, image_path: str | None, prompt_text: str, on_thumbs_down: Callable[[], None], on_regenerate: Callable[[], None], image_data: bytes | None = None, room_name: str | None = None) -> None:
        """Show the scene image using a standalone viewer subprocess.

        This avoids event-loop conflicts and keeps the UI responsive
        by running Tk in its own process.
        """
        from pathlib import Path
        import tempfile
        import subprocess
        import sys as _sys

        # Resolve room name from status bar
        current_room = room_name or "Unknown"
        if not room_name and hasattr(self, '_app') and hasattr(self._app, 'status_bar') and self._app.status_bar:
            current_room = self._app.status_bar.status.room

        # Ensure we have a file path for the image; if only bytes provided, write to temp
        viewer_image_path = image_path
        temp_file: tempfile.NamedTemporaryFile | None = None
        if viewer_image_path is None and image_data is not None:
            try:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                temp_file.write(image_data)
                temp_file.flush()
                temp_file.close()
                viewer_image_path = temp_file.name
                # Track temp so we can clean it later
                self._viewer_temp_path = viewer_image_path
            except Exception as exc:
                my_logging.system_warn(f"Failed to write temp image for viewer: {exc}")

        # Prepare subprocess command
        cmd = [
            _sys.executable,
            "-m",
            "module.scene_image_viewer",
            "--room",
            current_room or "Unknown",
            "--prompt",
            prompt_text or "",
        ]
        if viewer_image_path:
            cmd.extend(["--image-path", viewer_image_path])

        try:
            # If a viewer is already running, terminate it first to avoid duplicates
            try:
                if self._viewer_proc and getattr(self._viewer_proc, "poll", lambda: None)() is None:
                    self._viewer_proc.terminate()
            except Exception:
                pass

            self._viewer_proc = subprocess.Popen(cmd)
            my_logging.system_info(f"Scene image viewer launched: room={current_room}")
            
            # Monitor the process asynchronously to handle thumbs-down actions
            if hasattr(self, "_app") and self._app:
                asyncio.create_task(self._monitor_viewer_exit(on_thumbs_down, on_regenerate))
            
        except Exception as exc:
            my_logging.system_warn(f"Failed to launch scene image viewer: {exc}")
        finally:
            # No need to keep temp file object open; the viewer reads it by path.
            pass

        # Also show in-app controls overlay with prompt and buttons
        try:
            if hasattr(self, "_app") and self._app:
                # Provide prompt text and callbacks via app
                if hasattr(self._app, "show_scene_controls"):
                    self._app.show_scene_controls(prompt_text)
        except Exception as exc:
            my_logging.system_warn(f"Failed to show scene controls overlay: {exc}")

    def hide_scene_image(self) -> None:
        """Hide/close the scene image viewer if running and cleanup temp image."""
        import os
        try:
            if self._viewer_proc and getattr(self._viewer_proc, "poll", lambda: None)() is None:
                self._viewer_proc.terminate()
        except Exception:
            pass
        finally:
            self._viewer_proc = None
            if self._viewer_temp_path:
                try:
                    os.unlink(self._viewer_temp_path)
                except Exception:
                    pass
                self._viewer_temp_path = None

    async def _monitor_viewer_exit(self, on_thumbs_down: Callable[[], None], on_regenerate: Callable[[], None]) -> None:
        """Monitor the viewer subprocess and handle exit codes for thumbs-down actions."""
        if not self._viewer_proc:
            return
        
        try:
            # Wait for process to exit
            exit_code = await asyncio.create_task(
                asyncio.get_event_loop().run_in_executor(None, self._viewer_proc.wait)
            )
            
            my_logging.system_debug(f"Scene viewer exited with code: {exit_code}")
            
            # Handle exit codes
            if exit_code == 1:  # Thumbs down prompt
                my_logging.system_info("Viewer requested prompt regeneration")
                on_thumbs_down()  # This is actually thumbs-down prompt
            elif exit_code == 2:  # Thumbs down image  
                my_logging.system_info("Viewer requested image regeneration")
                on_regenerate()  # This is actually thumbs-down image
            # exit_code == 0 is normal close, no action needed
            
        except Exception as exc:
            my_logging.system_warn(f"Error monitoring viewer exit: {exc}")
        finally:
            self._viewer_proc = None

    # Engine status updates delegated to controller; remove duplication

    # AI status updates delegated to controller; remove duplication

    # Async helpers (`call_later`, `run_worker_async`) and direct `run()` wrapper were removed
    # to keep IFBuddyTUI as a pure widget aggregator. The controller should interact with the
    # underlying Textual `App` via `tui.app` if it needs scheduling.

    @property
    def app(self):
        """Expose the underlying Textual App for the controller."""
        return self._app


class IFBuddyApp(App):
    """Textual App for IF AI Buddy."""

    TITLE = "IF AI Buddy"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("i", "show_scene_image", "Show Scene Image"),
        ("h", "hide_scene_image", "Hide Scene Image"),
        ("p", "thumbs_down_prompt", "👎 Prompt"),
        ("r", "thumbs_down_image", "👎 Image"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #main_container {
        height: 1fr;
    }

    #columns {
        height: 1fr;
        layout: horizontal;
    }

    #left_column {
        width: 1fr;
    }

    #right_column {
        width: 1fr;
    }

    Footer {
        height: auto;
    }

    # Overlay controls styling
    # Simple centered container with padding
    # Uses $panel for background and $primary for borders
    # Adjust as needed for theme integration
    # SceneImageControls will apply this via classes
    .scene-controls-overlay {
        layer: overlay;
        width: 60%;
        height: auto;
        border: solid $primary;
        background: $panel;
        padding: 1 2;
        dock: top;
        offset: 2 0;
    }
    .scene-controls-buttons {
        layout: horizontal;
        height: auto;
        content-align: center middle;
        padding: 1 0;
    }
    .scene-controls-prompt {
        height: auto;
        padding: 1 0;
    }
    """

    def __init__(self, tui: IFBuddyTUI) -> None:
        super().__init__()
        self._tui = tui
        self._scene_controls: Static | None = None
        self._scene_prompt_text: str = ""

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()

        with Container(id="main_container"):
            with Horizontal(id="columns"):
                left = TranscriptLog()
                left.id = "left_column"
                self._tui.transcript_log = left
                yield left

                right = NarrationPanel()
                right.id = "right_column"
                self._tui.narration_panel = right
                yield right

        # Status bar
        status = StatusBar()
        # initial status is applied by controller
        self._tui.status_bar = status
        yield status

        # Command input
        cmd_input = CommandInput(on_submit=self._tui._on_command)
        self._tui.command_input = cmd_input
        yield cmd_input

        yield Footer()

    async def on_mount(self) -> None:
        """Log widget tree once mounted."""
        widget_ids = [w.id for w in self.query("*") if getattr(w, "id", None)]
        my_logging.system_debug(f"Widget tree IDs: {widget_ids}")

    async def action_quit(self) -> None:
        """Quit the app."""
        self.exit()

    async def action_show_scene_image(self) -> None:
        """Trigger showing the cached scene image popup via controller callback."""
        try:
            if hasattr(self._tui, "_on_show_scene_image") and callable(self._tui._on_show_scene_image):
                self._tui._on_show_scene_image()
        except Exception as exc:
            from module import my_logging
            my_logging.system_warn(f"Failed to show scene image: {exc}")

    async def action_hide_scene_image(self) -> None:
        """Hide the scene image viewer if running."""
        try:
            if hasattr(self._tui, "hide_scene_image"):
                self._tui.hide_scene_image()
            # Also hide controls overlay
            self.dismiss_scene_controls()
        except Exception as exc:
            from module import my_logging
            my_logging.system_warn(f"Failed to hide scene image: {exc}")

    async def action_thumbs_down_prompt(self) -> None:
        """Trigger prompt thumbs-down: regenerate prompt then image."""
        try:
            cb = getattr(self._tui, "_on_thumbs_down_prompt", None)
            if callable(cb):
                cb()
            self.dismiss_scene_controls()
        except Exception as exc:
            from module import my_logging
            my_logging.system_warn(f"Failed to queue prompt thumbs-down: {exc}")

    async def action_thumbs_down_image(self) -> None:
        """Trigger image thumbs-down: regenerate image only."""
        try:
            cb = getattr(self._tui, "_on_thumbs_down_image", None)
            if callable(cb):
                cb()
            self.dismiss_scene_controls()
        except Exception as exc:
            from module import my_logging
            my_logging.system_warn(f"Failed to queue image thumbs-down: {exc}")

    # -------- Scene Controls Overlay --------
    def show_scene_controls(self, prompt_text: str) -> None:
        """Show an overlay with prompt text and thumbs-down buttons."""
        try:
            from textual.containers import Vertical, Horizontal
            overlay = Static(classes="scene-controls-overlay")
            # Prompt display
            prompt_display = Static(prompt_text or "", classes="scene-controls-prompt")
            # Buttons row
            buttons = Horizontal(classes="scene-controls-buttons")
            btn_prompt = Button("👎 Prompt", id="btn_thumbs_prompt")
            btn_image = Button("👎 Image", id="btn_thumbs_image")
            btn_hide = Button("Hide", id="btn_hide_controls")
            buttons.mount_all(btn_prompt, btn_image, btn_hide)
            # Build overlay content
            container = Vertical()
            container.mount(prompt_display)
            container.mount(buttons)
            overlay.mount(container)

            # If an existing overlay is present, remove it first
            if self._scene_controls and not self._scene_controls.is_unmounted:
                try:
                    self._scene_controls.remove()
                except Exception:
                    pass

            self._scene_controls = overlay
            self._scene_prompt_text = prompt_text or ""
            self.mount(overlay)
        except Exception as exc:
            from module import my_logging
            my_logging.system_warn(f"Failed to show scene controls: {exc}")

    def dismiss_scene_controls(self) -> None:
        """Hide the scene controls overlay if visible."""
        try:
            if self._scene_controls and not self._scene_controls.is_unmounted:
                self._scene_controls.remove()
            self._scene_controls = None
            self._scene_prompt_text = ""
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle scene controls button presses."""
        try:
            if event.button.id == "btn_thumbs_prompt":
                await self.action_thumbs_down_prompt()
            elif event.button.id == "btn_thumbs_image":
                await self.action_thumbs_down_image()
            elif event.button.id == "btn_hide_controls":
                self.dismiss_scene_controls()
        except Exception as exc:
            from module import my_logging
            my_logging.system_warn(f"Scene controls handler error: {exc}")


__all__ = [
    "AIStatus",
    "EngineStatus", 
    "SDStatus",
    "StatusSnapshot",
    "IFBuddyTUI",
    "IFBuddyApp",
]